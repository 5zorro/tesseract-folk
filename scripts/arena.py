"""The arena (5zorro, 2026-11-07): de-noise the hall of fame so top-ups copy
objectively good brains, not lucky ones.

One life is a noisy score (plan-m2 R3, R10, R13). Here a nursery fills its hall
of fame as usual, then every entry is raced on *shared scenarios*:

- **Common random numbers:** a scenario is a short test world with a fixed seed.
  Every brain plays the same scenarios, as a clonal world (all its NPCs carry
  that exact brain), so map and draw luck is the same for every brain and
  cancels when they are compared.
- **Successive halving** (racing; Jamieson & Talwalkar 2016, F-Race, Birattari
  2002, cited from memory): all entries play the first `--stages` scenarios,
  the better half plays the next ones, and so on. Clear losers stop early;
  tests go to telling the contenders apart.
- **Tested harsher than bred:** scenarios use their own rules (`--test`, e.g. 1x
  hunger) while the nursery breeds under `--breed` (e.g. 4D's 0.36x, where births
  happen but nothing collapses, R13). Scenario founders don't age from collapses
  (`collapse_age_penalty=0`) and the test is shorter than old age, so no founder
  dies and no bad record goes missing.
- **Score:** founders' collapses per 1,000 ticks, as an excess over the field
  (a scenario's mean, corrected for how much better than the field that
  scenario's players already proved; lower is better).
- **Write-back:** the hall of fame keeps the top `--keep` entries (stage reached,
  then mean excess), their track record set to the arena's (lives = scenarios
  played, excess_sum = summed excess), so top-ups pick them by that merit. The
  rest are dropped. The nursery then runs on and refills; the next race
  re-tests everyone on new scenarios.

Arms: `arena` (race after every round) and `plain` (same nursery seeds, no race).
Each round's checkpoint is scored on fresh play worlds (`--play` rules, the M2
goals), and each arm's curve is fitted to y = y_inf + (y0 - y_inf) exp(-t / tau)
to project the time to equilibrium (~3 tau).

    python scripts/arena.py --dims 4 --breed nutrient_decay=0.00108,metabolism_rate=0.0036 \
        --play nutrient_decay=0.00108,metabolism_rate=0.0036
    python scripts/arena.py --dims 4 --report-only

It lives outside `sim/` and changes no rule, so both engines stay as they are.
"""
from __future__ import annotations

import argparse
import csv
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
from sim.simulation import Batch  # noqa: E402
from sim.snapshot import save_snapshot  # noqa: E402
from ladder import LATE_FROM, LOG_EVERY, NURSERY_RULES, WORLD_SETS, verdicts, world  # noqa: E402
from sweep import run_batch  # noqa: E402

ARMS = ("plain", "arena")
TEST_RULES = {"collapse_age_penalty": 0, "initial_npcs": 30}
METRICS = ("collapse_rate", "min_nutrient", "diet_diversity", "zone_types_per_life", "approach_excess")


# ================================================================ the race
def scenario_seed(nseed: int, rnd: int, index: int) -> int:
    """Shared by every brain in one race (common random numbers)."""
    return 50_000_000 + 100_000 * nseed + 1_000 * rnd + index


def play_scenarios(brains: list, base: dict, seeds: list[int], ticks: int) -> np.ndarray:
    """Founders' collapses per 1,000 ticks, one row per brain, one column per seed."""
    sims = []
    for brain in brains:
        for seed in seeds:
            sim = Simulation(Config(**{**base, "seed": seed}), log_every=max(ticks, 1))
            for npc in sim.npcs:                 # a clonal world: every founder is this brain
                npc.brain = brain
                npc.source = -1
            sims.append(sim)
    Batch(sims).run(ticks)
    rates = np.empty(len(sims))
    for i, sim in enumerate(sims):
        founders = [n for n in sim.npcs if n.origin == ""]
        if len(founders) != sim.cfg.initial_npcs:
            raise RuntimeError(f"a scenario lost founders ({len(founders)} of {sim.cfg.initial_npcs}); "
                               "shorten --test-ticks below old_age")
        rates[i] = 1000.0 * sum(n.collapses for n in founders) / max(sum(n.lifetime for n in founders), 1)
    return rates.reshape(len(brains), len(seeds))


def race(entries: list[dict], base: dict, stages: list[int], ticks: int, nseed: int, rnd: int) -> list[dict]:
    """Successive halving on shared scenarios. Returns one record per entry:
    {"stage", "excess": [per scenario]}, in the entries' order."""
    records = [{"stage": 0, "excess": []} for _ in entries]
    alive = list(range(len(entries)))
    index = 0
    for stage, count in enumerate(stages, 1):
        if not alive:
            break
        seeds = [scenario_seed(nseed, rnd, index + k) for k in range(count)]
        index += count
        raw = play_scenarios([entries[i]["brain"] for i in alive], base, seeds, ticks)
        # The field's mean on a later scenario is estimated from its players'
        # mean, corrected by how much better than the field they already proved.
        proved = np.array([np.mean(records[i]["excess"]) if records[i]["excess"] else 0.0 for i in alive])
        baseline = raw.mean(axis=0) - proved.mean()
        for row, i in enumerate(alive):
            records[i]["excess"].extend((raw[row] - baseline).tolist())
            records[i]["stage"] = stage
        if stage < len(stages):
            alive.sort(key=lambda i: np.mean(records[i]["excess"]))
            alive = alive[:max(1, len(alive) // 2)]
    return records


def ranked(records: list[dict]) -> list[int]:
    """Entries by stage reached (higher first), then mean excess (lower first)."""
    return sorted(range(len(records)), key=lambda i: (-records[i]["stage"], np.mean(records[i]["excess"])))


def write_back(sim, records: list[dict], keep: int) -> dict:
    order = ranked(records)[:keep]
    kept = []
    for i in order:
        entry = dict(sim.hall_of_fame[i])
        entry["lives"] = float(len(records[i]["excess"]))
        entry["excess_sum"] = float(np.sum(records[i]["excess"]))
        kept.append(entry)
    before = len(sim.hall_of_fame)
    sim.hall_of_fame = kept
    return {"raced": before, "kept": len(kept),
            "best_excess": float(np.mean(records[order[0]]["excess"])) if order else math.nan}


# ============================================================== nurseries
def shape_of(dims: int, hidden: int) -> tuple:
    return (dims, *WORLD_SETS["time"][dims], hidden, ())


def checkpoint(out: Path, arm: str, nseed: int, rnd: int) -> Path:
    return out / f"{arm}-n{nseed}-r{rnd}"


def nursery(job: tuple) -> list[str]:
    arm, nseed, args = job
    shape = shape_of(args["dims"], args["hidden"])
    base = world(shape)
    sim = Simulation(Config(**{**base, **NURSERY_RULES, **args["breed"], "seed": nseed}), log_every=1000)
    test = {**base, **args["test"], **TEST_RULES}
    msgs = []
    for rnd in range(1, args["rounds"] + 1):
        sim.run(args["round_ticks"])
        note = ""
        if arm == "arena" and sim.hall_of_fame:
            info = write_back(sim, race(sim.hall_of_fame, test, args["stages"], args["test_ticks"], nseed, rnd),
                              args["keep"])
            note = f" (raced {info['raced']}, kept {info['kept']}, best excess {info['best_excess']:+.2f})"
        save_snapshot(sim, checkpoint(Path(args["out"]), arm, nseed, rnd))
        msgs.append(f"{arm} n{nseed} round {rnd} at {sim.tick:,}{note}")
    return msgs


# ================================================================== play
def play(job: tuple) -> list[dict]:
    arm, nseed, rnd, args = job
    shape = shape_of(args["dims"], args["hidden"])
    overrides = {**world(shape), **args["play"]}
    if arm != "scratch":
        overrides["brains_from"] = str(checkpoint(Path(args["out"]), arm, nseed, rnd))
    runs = [(dict(overrides), s, args["play_ticks"], LATE_FROM, LOG_EVERY) for s in range(args["play_seeds"])]
    rows = []
    for s, row in enumerate(run_batch(runs)):
        rows.append({"arm": arm, "nursery": nseed, "round": rnd, "ticks": rnd * args["round_ticks"],
                     "seed": s, **row})
    return rows


# ================================================================ report
def fit(t: np.ndarray, y: np.ndarray) -> dict:
    """y = a + b exp(-t / tau): least squares on a grid of tau. Returns y_inf (a),
    tau, and whether tau sits on the grid's edge (no clear equilibrium)."""
    best = None
    span = float(t.max() - t.min()) or 1.0
    for tau in np.geomspace(span / 50, span * 20, 400):
        X = np.column_stack([np.ones_like(t), np.exp(-t / tau)])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        err = float(np.sum((X @ coef - y) ** 2))
        if best is None or err < best[0]:
            best = (err, tau, coef)
    _, tau, (a, b) = best
    edge = tau <= span / 49 or tau >= span * 19
    return {"y_inf": float(a), "tau": float(tau), "t95": float(3 * tau), "edge": edge}


def report(rows: list[dict], args: dict) -> None:
    scratch = {r["seed"]: r for r in rows if r["arm"] == "scratch"}
    print(f"\n{args['dims']}D arena vs plain nursery: play worlds from each round's checkpoint "
          f"(means over nurseries x seeds; scratch collapses "
          f"{np.mean([r['collapse_rate'] for r in scratch.values()]):.2f})")
    print(f"{'arm':>6} {'round':>5} {'ticks':>8} {'clpse':>5} {'nutr':>5} {'diet':>5} {'types':>11} "
          f"{'excess':>7}  goals (collapses, nutrient, diet, types, seeks diet)")
    curves = {}
    for arm in [a for a in ARMS if any(r["arm"] == a for r in rows)]:
        for rnd in sorted({r["round"] for r in rows if r["arm"] == arm}):
            cell = [r for r in rows if r["arm"] == arm and r["round"] == rnd]
            m = {k: float(np.nanmean([r[k] for r in cell])) for k in METRICS}
            types = [r["zone_types_per_life"] for r in cell]
            se = float(np.nanstd(types) / math.sqrt(max(len(types), 1)))
            ladder_rows = ([{**r, "dims": args["dims"], "hidden": args["hidden"], "brains": f"n{r['nursery']}"}
                            for r in cell] +
                           [{**r, "dims": args["dims"], "hidden": args["hidden"], "brains": "scratch"}
                            for r in scratch.values()])
            v = verdicts(ladder_rows)
            marks = " ".join("Y" if ok else "." for ok in v[0]["goals"].values()) if v else "-"
            print(f"{arm:>6} {rnd:>5} {cell[0]['ticks']:>8,} {m['collapse_rate']:5.2f} {m['min_nutrient']:5.2f} "
                  f"{m['diet_diversity']:5.2f} {m['zone_types_per_life']:5.2f}+-{se:4.2f} "
                  f"{m['approach_excess']:7.3f}  {marks}")
            curves.setdefault(arm, []).append((cell[0]["ticks"], m))
    print("\nEquilibrium projection, y = y_inf + (y0 - y_inf) exp(-t / tau); ~95% there at 3 tau:")
    for arm, points in curves.items():
        if len(points) < 3:
            print(f"  {arm}: needs 3+ rounds")
            continue
        t = np.array([p[0] for p in points], dtype=float)
        for key, label in (("zone_types_per_life", "types"), ("collapse_rate", "collapses"),
                           ("diet_diversity", "diet")):
            y = np.array([p[1][key] for p in points])
            f = fit(t, y)
            peak = int(np.argmax(y) if key != "collapse_rate" else np.argmin(y))
            shape = "" if peak == len(y) - 1 else f"; best at round {peak + 1}, then worse"
            where = "no clear equilibrium (tau at the fit's edge)" if f["edge"] else \
                f"-> {f['y_inf']:.2f}, tau {f['tau']:,.0f} ticks, 95% by ~{f['t95']:,.0f}"
            print(f"  {arm:>6} {label:>9}: {where}{shape}")


def write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def read(path: Path) -> list[dict]:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            if k != "arm":
                try:
                    r[k] = float(v) if v not in ("", "nan") else math.nan
                except ValueError:
                    pass
        for k in ("nursery", "round", "ticks", "seed"):
            r[k] = int(r[k])
    return rows


def rules(spec: str) -> dict:
    return parse_overrides(spec) if spec else {}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, default=4, choices=sorted(WORLD_SETS["time"]))
    ap.add_argument("--hidden", type=int, default=16)
    ap.add_argument("--breed", default="", help="nursery rules (KEY=VALUE,...), on top of the nursery's own")
    ap.add_argument("--test", default="", help="scenario rules (default: today's defaults, 1x hunger)")
    ap.add_argument("--play", default="", help="play-world rules for scoring checkpoints")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--round-ticks", type=int, default=20_000)
    ap.add_argument("--nursery-seeds", type=int, nargs="+", default=[100, 101, 102, 103])
    ap.add_argument("--stages", type=int, nargs="+", default=[2, 2, 4],
                    help="scenarios per stage; the field halves after each but the last")
    ap.add_argument("--keep", type=int, default=10, help="entries kept after a race")
    ap.add_argument("--test-ticks", type=int, default=1200, help="scenario length (below old_age)")
    ap.add_argument("--play-seeds", type=int, default=3)
    ap.add_argument("--play-ticks", type=int, default=10_000)
    ap.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    ap.add_argument("--out", default="snapshots/arena")
    ap.add_argument("--csv", default=None, help="default runs/arena-{dims}d.csv")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()
    if a.rounds < 1 or a.round_ticks < 1 or a.keep < 1 or not a.stages or min(a.stages) < 1:
        ap.error("--rounds, --round-ticks, --keep and --stages must be positive")
    if a.test_ticks >= Config().old_age:
        ap.error("--test-ticks must be below old_age, or founders die and their records go missing")
    try:
        args = {"dims": a.dims, "hidden": a.hidden, "breed": rules(a.breed), "test": rules(a.test),
                "play": rules(a.play), "rounds": a.rounds, "round_ticks": a.round_ticks, "stages": a.stages,
                "keep": a.keep, "test_ticks": a.test_ticks, "play_seeds": a.play_seeds,
                "play_ticks": a.play_ticks, "out": a.out}
    except ValueError as e:
        ap.error(str(e))
    path = Path(a.csv or f"runs/arena-{a.dims}d.csv")
    if not a.report_only:
        jobs = [(arm, n, args) for arm in a.arms for n in a.nursery_seeds]
        jobs.sort(key=lambda j: j[0] != "arena")          # the slower arm first
        with ProcessPoolExecutor(min(a.jobs, len(jobs))) as pool:
            for fut in as_completed([pool.submit(nursery, j) for j in jobs]):
                for msg in fut.result():
                    print("  ", msg, flush=True)
        plays = [(arm, n, r, args) for arm in a.arms for n in a.nursery_seeds for r in range(1, a.rounds + 1)]
        plays.append(("scratch", -1, 0, args))
        rows = []
        with ProcessPoolExecutor(min(a.jobs, len(plays))) as pool:
            for fut in as_completed([pool.submit(play, j) for j in plays]):
                rows.extend(fut.result())
                print(f"  play {len(rows)}/{len(plays) * a.play_seeds}", flush=True)
        rows.sort(key=lambda r: (r["arm"], r["nursery"], r["round"], r["seed"]))
        write(path, rows)
    report(read(path), args)


if __name__ == "__main__":
    main()
