"""The dimensions ladder (M2 slice 3d): the smallest brain that meets the goals
in each dimension.

For every (dims, hidden_units) pair it trains nurseries under harsh rules, then
starts play worlds from each nursery and from scratch, and checks the M1/M2
goals. Worlds are matched across dimensions: ~1,000 cells, and a patch radius
that lets 45% of cells hold a bite of each food, as in 2D
(docs/plan-m2-diet-travel.md, slice 3d).

    python scripts/ladder.py                      # everything, ~45-60 min on 16 cores
    python scripts/ladder.py --dims 3 --hidden 8 16
    python scripts/ladder.py --report-only        # re-read the CSV and print the verdicts
    python scripts/ladder.py --worlds time --hidden 8 16   # slice 3e: worlds matched on trip time
    python scripts/ladder.py --worlds time --hidden 8 --set scent_min_food=0.2   # with new rules

Nurseries are saved under --out and reused if present, so an interrupted run
picks up where it stopped (play runs are always redone).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim import Config, Simulation  # noqa: E402
from sim.config import parse_overrides  # noqa: E402
from sim.snapshot import FORMAT, LEGACY, save_snapshot  # noqa: E402
from sweep import run_one  # noqa: E402

# dims -> (size, food_patch_radius), per way of matching worlds across dimensions:
# "coverage" (slice 3d): ~1,000 cells, 45% bite coverage per food type.
# "time" (slice 3e): 2D's total food (~1,600) and 2D's trip between foods
# (~5.7 ticks, scripts/travel_time.py).
WORLD_SETS = {
    "coverage": {1: (1024, 55.0), 2: (32, 4.0), 3: (10, 1.84), 4: (6, 1.35)},
    "time": {2: (32, 4.0), 3: (14, 1.88), 4: (10, 1.23)},
}
HIDDEN = (4, 8, 16, 32)
NURSERY_SEEDS = (100, 101)
NURSERY_RULES = {"collapse_age_penalty": 600}
LATE_FROM, LOG_EVERY = 0.5, 250

# The M1/M2 goals each nursery-started world is checked against.
MIN_NUTRIENT, MIN_DIET, MIN_TYPES = 0.4, 0.9, 2.5


# A "shape" is (dims, size, food_patch_radius, hidden_units, rules), where rules
# are extra Config overrides as sorted (key, value) pairs. Jobs carry it whole,
# since worker processes re-import this module and wouldn't see the chosen set.
def world(shape: tuple) -> dict:
    dims, size, radius, hidden, rules = shape
    return {"dims": dims, "size": size, "food_patch_radius": radius, "hidden_units": hidden,
            **dict(rules)}


def rules_text(rules: tuple) -> str:
    return ",".join(f"{k}={v}" for k, v in rules)


def nursery_path(out: Path, shape: tuple, nseed: int) -> Path:
    dims, size, radius, hidden, rules = shape   # named by world, so identical worlds share nurseries
    extra = "".join(f"-{k}{v}" for k, v in rules)
    return out / f"d{dims}-s{size}-r{radius:g}-h{hidden}{extra}-n{nseed}"


def nursery_config(shape: tuple, nseed: int) -> dict:
    return {**world(shape), **NURSERY_RULES, "seed": nseed}


def reusable(path: Path, shape: tuple, nseed: int, ticks: int) -> bool:
    """An existing nursery is reused only if it was trained exactly as asked now;
    a folder with the same name but other settings is an error, not a silent reuse."""
    if not (path / "state.json").exists():
        return False
    state = json.loads((path / "state.json").read_text())
    if state.get("format", 1) != FORMAT:
        raise ValueError(f"{path} was saved in snapshot format {state.get('format', 1)}, "
                         f"not {FORMAT} (other tick rules). Delete it or use another --out.")
    # Every setting, not just the ones passed: a default that changed since the
    # nursery was trained (e.g. the mutation rule) counts. Missing fields are read
    # the way load_snapshot reads them.
    saved = Config.from_dict({**LEGACY, **state.get("config", {})}).to_dict()
    wanted = Config(**nursery_config(shape, nseed)).to_dict()
    differ = sorted(k for k, v in wanted.items() if saved.get(k) != v)
    if differ or state.get("tick") != ticks:
        raise ValueError(f"{path} was trained with other settings ({', '.join(differ) or 'ticks'}"
                         f"; tick {state.get('tick')} vs {ticks}). Delete it or use another --out.")
    return True


def train(job: tuple) -> str:
    shape, nseed, ticks, out = job
    path = nursery_path(out, shape, nseed)
    if reusable(path, shape, nseed, ticks):
        return f"kept {path.name}"
    sim = Simulation(Config(**nursery_config(shape, nseed)), log_every=1000)
    sim.run(ticks)
    save_snapshot(sim, path)
    return f"trained {path.name}"


def play(job: tuple) -> dict:
    shape, brains, seed, ticks, out = job
    overrides = world(shape)
    if brains != "scratch":
        overrides["brains_from"] = str(nursery_path(out, shape, int(brains[1:])))
    row = run_one(overrides, seed, ticks, LATE_FROM, LOG_EVERY)
    dims, size, radius, hidden, rules = shape
    return {"dims": dims, "size": size, "radius": radius, "hidden": hidden,
            "rules": rules_text(rules), "brains": brains, **row}


def run_pool(fn, jobs: list, workers: int, label: str) -> list:
    results = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fn, job) for job in jobs]
        for i, fut in enumerate(as_completed(futures), 1):
            results.append(fut.result())
            print(f"  {label} {i}/{len(jobs)}", flush=True)
    return results


# ================================================================ report
def verdicts(rows: list[dict]) -> list[dict]:
    """One line per (dims, hidden): nursery means, scratch means, and the goals."""
    out = []
    for dims in sorted({r["dims"] for r in rows}):
        for hidden in sorted({r["hidden"] for r in rows if r["dims"] == dims}):
            cell = [r for r in rows if r["dims"] == dims and r["hidden"] == hidden]
            scratch = {r["seed"]: r for r in cell if r["brains"] == "scratch"}
            nursery = [r for r in cell if r["brains"] != "scratch"]
            if not scratch or not nursery:
                continue

            def mean(rs, key):
                vals = [r[key] for r in rs if not math.isnan(r[key])]
                return float(np.mean(vals)) if vals else math.nan

            paired = [r["approach_excess"] - scratch[r["seed"]]["approach_excess"]
                      for r in nursery if r["seed"] in scratch]
            paired = [p for p in paired if not math.isnan(p)]
            line = {
                "dims": dims, "hidden": hidden,
                "collapses": mean(nursery, "collapse_rate"),
                "scratch_collapses": mean(scratch.values(), "collapse_rate"),
                "min_nutrient": mean(nursery, "min_nutrient"),
                "diet": mean(nursery, "diet_diversity"),
                "types": mean(nursery, "zone_types_per_life"),
                "excess": mean(nursery, "approach_excess"),
                "scratch_excess": mean(scratch.values(), "approach_excess"),
                "excess_vs_scratch": float(np.mean(paired)) if paired else math.nan,
                "excess_positive": sum(r["approach_excess"] > 0 for r in nursery),
                "runs": len(nursery),
            }
            line["goals"] = {
                "collapses": line["collapses"] < line["scratch_collapses"],
                "nutrient": line["min_nutrient"] >= MIN_NUTRIENT,
                "diet": line["diet"] >= MIN_DIET,
                "types": line["types"] >= MIN_TYPES,
                "seeks diet": line["excess_positive"] == line["runs"] and line["excess_vs_scratch"] > 0,
            }
            out.append(line)
    return out


def report(rows: list[dict]) -> None:
    lines = verdicts(rows)
    goal_names = list(lines[0]["goals"]) if lines else []
    print("\nNursery-started worlds vs scratch (means over nurseries x seeds)")
    print(f"{'dims':>4} {'hid':>3} {'clpse':>5} {'scr':>5} {'nutr':>5} {'diet':>5} {'types':>5} "
          f"{'excess':>7} {'scr':>7} {'vs scr':>7} {'>0':>5}  goals ({', '.join(goal_names)})")
    for l in lines:
        marks = " ".join("Y" if ok else "." for ok in l["goals"].values())
        print(f"{l['dims']:>4} {l['hidden']:>3} {l['collapses']:5.2f} {l['scratch_collapses']:5.2f} "
              f"{l['min_nutrient']:5.2f} {l['diet']:5.2f} {l['types']:5.2f} {l['excess']:7.3f} "
              f"{l['scratch_excess']:7.3f} {l['excess_vs_scratch']:+7.3f} "
              f"{l['excess_positive']:>2}/{l['runs']:<2}  {marks}")
    print("\nSmallest brain meeting every goal:")
    for dims in sorted({l["dims"] for l in lines}):
        passing = [l["hidden"] for l in lines if l["dims"] == dims and all(l["goals"].values())]
        print(f"  {dims}D: {min(passing) if passing else 'none of the sizes tried'}")


def read_csv(path: Path) -> list[dict]:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            if k in ("brains", "rules"):
                continue
            try:
                r[k] = float(v) if v not in ("", "nan") else math.nan
            except ValueError:
                pass
        r["dims"], r["hidden"], r["seed"] = int(r["dims"]), int(r["hidden"]), int(r["seed"])
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worlds", choices=sorted(WORLD_SETS), default="coverage",
                    help="how worlds are matched across dimensions (see WORLD_SETS)")
    ap.add_argument("--dims", type=int, nargs="+", default=None, help="default: every dims in the set")
    ap.add_argument("--hidden", type=int, nargs="+", default=list(HIDDEN))
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE[,...]",
                    help="rule overrides for nurseries and play worlds alike (repeatable)")
    ap.add_argument("--nursery-ticks", type=int, default=20_000)
    ap.add_argument("--ticks", type=int, default=10_000)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--nursery-seeds", type=int, nargs="+", default=list(NURSERY_SEEDS),
                    help="nursery seeds (more nurseries = less nursery-to-nursery noise)")
    ap.add_argument("--out", type=str, default="snapshots/ladder")
    ap.add_argument("--csv", type=str, default="runs/ladder.csv")
    ap.add_argument("--jobs", type=int, default=None)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    worlds = WORLD_SETS[args.worlds]
    try:
        rules = {}
        for spec in args.set:
            rules.update(parse_overrides(spec))
    except ValueError as e:
        ap.error(str(e))
    rules = tuple(sorted(rules.items()))
    args.dims = args.dims or sorted(worlds)
    if any(d not in worlds for d in args.dims):
        ap.error(f"--dims must be among {sorted(worlds)} for --worlds {args.worlds}")

    csv_path = Path(args.csv)
    if args.report_only:
        report(read_csv(csv_path))
        return

    out = Path(args.out)
    workers = args.jobs or os.cpu_count() or 1
    shapes = [(d, *worlds[d], h, rules) for d in args.dims for h in args.hidden]
    # Biggest jobs first, so the pool doesn't finish on one long straggler.
    shapes.sort(key=lambda s: -(s[1] ** s[0]) * s[3])
    nursery_jobs = [(s, n, args.nursery_ticks, out) for s in shapes for n in args.nursery_seeds]
    print(f"Training {len(nursery_jobs)} nurseries ({args.nursery_ticks} ticks) on {workers} processes.",
          flush=True)
    for msg in run_pool(train, nursery_jobs, workers, "nursery"):
        print(f"    {msg}")

    brains = ["scratch"] + [f"n{n}" for n in args.nursery_seeds]
    play_jobs = [(s, b, seed, args.ticks, out) for s in shapes for b in brains for seed in range(args.seeds)]
    print(f"Running {len(play_jobs)} play worlds ({args.ticks} ticks).", flush=True)
    rows = run_pool(play, play_jobs, workers, "play")
    rows.sort(key=lambda r: (r["dims"], r["hidden"], r["brains"], r["seed"]))

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} runs to {csv_path}")
    report(read_csv(csv_path))


if __name__ == "__main__":
    main()
