"""Run several seeds (and config variants) and summarize them side by side.

One seed is an anecdote (see gotchas.md), so every M1 tuning claim should come
from here. Examples:
    python scripts/sweep.py --seeds 5 --ticks 10000
    python scripts/sweep.py --variant metabolism_rate=0.008 --variant nutrient_decay=0.003
    python scripts/sweep.py --variant controller=scripted
    python scripts/sweep.py --set dims=4 --set size=10 --ticks 2000
    python scripts/sweep.py --variant smiting=true,smite_damage=0.1 --csv runs/smite.csv

Each --variant is a comma-separated list of Config overrides, compared against
a baseline that has only the --set overrides. The pseudo-key
controller=scripted runs every NPC, including newborns and top-ups, on
ScriptedController (the "instinct" benchmark) instead of its brain, and
brains_from=<snapshot folder> starts each world from that snapshot's best
brains (the nursery, sim/nursery.py):
    python scripts/sweep.py --variant brains_from=snapshots/nursery-2
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim import Config, Simulation  # noqa: E402
from sim.config import parse_overrides as config_overrides  # noqa: E402
from sim.controllers import ScriptedController  # noqa: E402
from sim.nursery import load_brain_pool, seed_brains  # noqa: E402
from sim.stats import CAUSES  # noqa: E402
from sim.world import wrapped_delta  # noqa: E402

# Generation buckets for collapse rates: (label, first generation, last generation).
BUCKETS = [("g0", 0, 0), ("g1-2", 1, 2), ("g3-5", 3, 5), ("g6-10", 6, 10), ("g11+", 11, 10**9)]
MIN_BUCKET_LIFETIME = 500     # NPC-ticks; below this a bucket's rate is too noisy to report
NUTRIENT_WINDOW = 0.75        # mean lowest nutrient is measured after this fraction of the run
DISTANCE_EVERY = 100          # ticks; "how far from where it was this long ago" (M2)
CONTROLLERS = ("brain", "scripted")
SHOWN_CAUSES = [("smite", "smite"), ("nutrient_starve", "nutr"), ("body_starve", "body"),
                ("stink", "stink"), ("elder", "elder")]


# ================================================================ parsing
def parse_overrides(spec: str) -> dict:
    """Config overrides (typed by sim.config.parse_overrides) plus the sweep's
    pseudo-keys: controller=brain|scripted, and brains_from=<snapshot folder>
    to start each world from that snapshot's best brains (sim/nursery.py)."""
    out, rest = {}, []
    for item in filter(None, (s.strip() for s in spec.split(","))):
        key, _, raw = (part.strip() for part in item.partition("="))
        if key == "controller":
            if raw not in CONTROLLERS:
                raise ValueError(f"controller must be one of {CONTROLLERS}, got {raw!r}")
            out[key] = raw
        elif key == "brains_from":
            if not raw:
                raise ValueError("brains_from needs a snapshot folder")
            out[key] = raw
        else:
            rest.append(item)
    out.update(config_overrides(",".join(rest)))
    return out


# ================================================================ one run
def cover_with(sim: Simulation, controller) -> None:
    """Point every living NPC at `controller`. Overrides are keyed by NPC id,
    so this has to be redone each tick to cover newborns and top-ups."""
    sim.overrides = {n.id: controller for n in sim.npcs}


def distances(before: dict, sim: Simulation) -> list[float]:
    """Straight-line distance each NPC moved since `before` ({id: (pos, collapses)}).
    NPCs that collapsed in between are skipped: waking up elsewhere isn't travel."""
    out = []
    for npc in sim.npcs:
        then = before.get(npc.id)
        if then is not None and then[1] == npc.collapses:
            out.append(float(np.linalg.norm(wrapped_delta(then[0], npc.pos, sim.cfg.size))))
    return out


def where_now(sim: Simulation) -> dict:
    return {npc.id: (npc.pos, npc.collapses) for npc in sim.npcs}


def bucket_rates(lifetime: dict, collapses: dict) -> dict:
    """Collapses per 1,000 NPC-ticks for each generation bucket (nan if too little data)."""
    out = {}
    for label, lo, hi in BUCKETS:
        life = sum(t for g, t in lifetime.items() if lo <= g <= hi)
        hits = sum(c for g, c in collapses.items() if lo <= g <= hi)
        out[label] = hits * 1000 / life if life >= MIN_BUCKET_LIFETIME else math.nan
    return out


def run_one(overrides: dict, seed: int, ticks: int, late_from: float, log_every: int) -> dict:
    """Run one seed and return its summary metrics (all plain numbers)."""
    overrides = dict(overrides)
    controller = overrides.pop("controller", "brain")
    brains_from = overrides.pop("brains_from", None)
    sim = Simulation(Config(**{**overrides, "seed": seed}), log_every=log_every)
    if brains_from:
        seed_brains(sim, load_brain_pool(brains_from))
    scripted = ScriptedController() if controller == "scripted" else None
    nutrient_from = int(ticks * NUTRIENT_WINDOW)
    late_start = int(ticks * late_from)
    min_nutrients, moved = [], []
    last_seen: dict = {}

    def advance(steps: int) -> None:
        nonlocal last_seen
        for _ in range(steps):
            if scripted is not None:
                cover_with(sim, scripted)
            sim.step()
            if sim.tick > nutrient_from and sim.tick % log_every == 0 and sim.npcs:
                min_nutrients.append(float(np.mean([npc.nutrients.min() for npc in sim.npcs])))
            if sim.tick >= late_start and sim.tick % DISTANCE_EVERY == 0:
                moved.extend(distances(last_seen, sim))
                last_seen = where_now(sim)

    advance(late_start)
    stats = sim.stats
    life_before = dict(stats.generation_lifetime)
    collapses_before = dict(stats.generation_collapses)
    advance(ticks - late_start)

    rows = stats.history + [dict(stats.window)]
    def total(key: str) -> int:
        return sum(r.get(key, 0) for r in rows)

    collapses = total("collapses")
    lifetime = sum(stats.generation_lifetime.values())
    late_life = {g: t - life_before.get(g, 0) for g, t in stats.generation_lifetime.items()}
    late_collapses = {g: c - collapses_before.get(g, 0) for g, c in stats.generation_collapses.items()}

    out = {"seed": seed,
           "collapse_rate": collapses * 1000 / lifetime if lifetime else math.nan}
    for label, rate in bucket_rates(stats.generation_lifetime, stats.generation_collapses).items():
        out[f"rate_{label}"] = rate
    for label, rate in bucket_rates(late_life, late_collapses).items():
        out[f"late_{label}"] = rate
    for cause in CAUSES:
        out[f"cause_{cause}"] = total(f"collapse_{cause}") / collapses if collapses else math.nan
    out["min_nutrient"] = float(np.mean(min_nutrients)) if min_nutrients else math.nan
    diets = [r["diet_diversity"] for r in rows if r.get("tick", 0) > nutrient_from and "diet_diversity" in r]
    out["diet_diversity"] = float(np.mean(diets)) if diets else math.nan
    travel = stats.travel_summary(since_tick=late_start)
    out["lives"] = travel["lives"]
    out["zones_per_life"] = travel["zones"]
    out["zone_types_per_life"] = travel["zone_types"]
    out["zone_switch_rate"] = travel["switch_rate"]
    out["directed"] = travel["directed"]
    out["directed_chance"] = travel["chance"]
    out["directed_lift"] = travel["directed"] - travel["chance"]
    out["distance"] = float(np.mean(moved)) if moved else math.nan
    out["births"] = total("births")
    out["spawns"] = total("spawns")
    out["max_generation"] = max((n.generation for n in sim.npcs), default=0)
    out["population"] = len(sim.npcs)
    out["stable"] = float(sim.is_stable())
    return out


def _run_job(job: tuple) -> dict:
    return run_one(*job)


# ================================================================ output
def mean_sd(values: list[float], pct: bool = False, digits: int = 1) -> str:
    vals = [v for v in values if not math.isnan(v)]
    if not vals:
        return "-"
    scale = 100 if pct else 1
    text = f"{np.mean(vals) * scale:.{digits}f}"
    if len(vals) > 1:
        text += f"+-{np.std(vals, ddof=1) * scale:.{digits}f}"
    if len(vals) < len(values):
        text += f" (n={len(vals)})"
    return text


def print_table(title: str, columns: list[tuple[str, str, dict]], results: dict) -> None:
    """columns: (header, metric key, mean_sd kwargs). results: label -> list of run dicts."""
    print(f"\n{title}")
    cells = [[mean_sd([r[key] for r in runs], **kw) for _, key, kw in columns]
             for runs in results.values()]
    widths = [max(len(h), *(len(row[i]) for row in cells)) for i, (h, _, _) in enumerate(columns)]
    print("  var  " + "  ".join(h.rjust(w) for (h, _, _), w in zip(columns, widths)))
    for code, row in zip(codes(len(results)), cells):
        print(f"  {code:<4} " + "  ".join(c.rjust(w) for c, w in zip(row, widths)))


def codes(n: int) -> list[str]:
    return [chr(ord("A") + i) if i < 26 else f"V{i}" for i in range(n)]


def summarize(results: dict, ticks: int, late_from: float, seeds: list[int]) -> None:
    print(f"\n{len(seeds)} seeds ({seeds[0]}..{seeds[-1]}) x {ticks} ticks, mean +- sd across seeds.")
    for code, label in zip(codes(len(results)), results):
        print(f"  {code}: {label}")
    buckets = [label for label, _, _ in BUCKETS]
    print_table("Collapses per 1,000 NPC-ticks, whole run",
                [("all", "collapse_rate", {})] + [(b, f"rate_{b}", {}) for b in buckets], results)
    late_start = int(ticks * late_from)
    print_table(f"Same, late window only (ticks {late_start}-{ticks}); compare generations here",
                [(b, f"late_{b}", {}) for b in buckets], results)
    print_table("Collapse causes (% of collapses) and survival",
                [(h, f"cause_{c}", {"pct": True, "digits": 0}) for c, h in SHOWN_CAUSES]
                + [("min-nutr", "min_nutrient", {"digits": 2}), ("births", "births", {}),
                   ("spawns", "spawns", {}), ("max-gen", "max_generation", {}),
                   ("pop", "population", {}), ("stable%", "stable", {"pct": True, "digits": 0})],
                results)
    print_table(f"Diet and travel (M2): diet over the last quarter; travel over lives "
                f"ending after tick {late_start} that lasted 500+ ticks",
                [("diet", "diet_diversity", {"digits": 2}), ("lives", "lives", {"digits": 0}),
                 ("zones/life", "zones_per_life", {}), ("types/life", "zone_types_per_life", {}),
                 ("switches/1k", "zone_switch_rate", {}),
                 (f"dist/{DISTANCE_EVERY}t", "distance", {}),
                 ("directed", "directed", {"digits": 2}), ("chance", "directed_chance", {"digits": 2}),
                 ("lift", "directed_lift", {"digits": 2})],
                results)


def write_csv(path: Path, results: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"variant": label, **run} for label, runs in results.items() for run in runs]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} runs to {path}")


# ================================================================ main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=5, help="number of seeds per variant")
    ap.add_argument("--seed-start", type=int, default=0)
    ap.add_argument("--ticks", type=int, default=10_000)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE[,...]",
                    help="override applied to every variant (repeatable)")
    ap.add_argument("--variant", action="append", default=[], metavar="KEY=VALUE[,...]",
                    help="a config to compare against the baseline (repeatable)")
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument("--late-from", type=float, default=0.5,
                    help="the late window starts at this fraction of the run")
    ap.add_argument("--log-every", type=int, default=250)
    ap.add_argument("--jobs", type=int, default=None, help="parallel processes (default: one per run, up to CPU count)")
    ap.add_argument("--csv", type=str, default=None, help="also write per-run rows here (e.g. runs/x.csv)")
    args = ap.parse_args()

    try:
        shared = {}
        for spec in args.set:
            shared.update(parse_overrides(spec))
        variants = {} if args.no_baseline else {"baseline": shared}
        for spec in args.variant:
            variants[spec] = {**shared, **parse_overrides(spec)}
    except ValueError as e:
        ap.error(str(e))
    if not variants:
        ap.error("nothing to run: --no-baseline needs at least one --variant")

    seeds = list(range(args.seed_start, args.seed_start + args.seeds))
    jobs = [(overrides, seed, args.ticks, args.late_from, args.log_every)
            for overrides in variants.values() for seed in seeds]
    workers = args.jobs or min(os.cpu_count() or 1, len(jobs))
    shared_text = ", ".join(f"{k}={v}" for k, v in shared.items()) or "defaults"
    print(f"Running {len(jobs)} runs ({len(variants)} variants x {len(seeds)} seeds) "
          f"on {workers} process(es). Shared config: {shared_text}.", flush=True)

    if workers == 1:
        flat = [_run_job(job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            flat = list(pool.map(_run_job, jobs))

    results = {label: flat[i * len(seeds):(i + 1) * len(seeds)] for i, label in enumerate(variants)}
    summarize(results, args.ticks, args.late_from, seeds)
    if args.csv:
        write_csv(Path(args.csv), results)


if __name__ == "__main__":
    main()
