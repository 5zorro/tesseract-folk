"""A long nursery's learning curve (5zorro, 2026-11-06: "4D needs 700k ticks based
on a rough extrapolation, how about we use that as the baseline and take
snapshots as it reaches it?").

Trains fixed-rules nurseries (as the ladder's) for each arm in one long run,
saving snapshots at checkpoints, then starts play worlds from every checkpoint
and scores them with the ladder's goals. Each nursery runs in its own process
(one world, so the 4D world step stays in cache) and always trains from tick
0; keyed randomness makes a rerun identical.

    python scripts/long_nursery.py                        # 4D, base and both senses at 32
    python scripts/long_nursery.py --checkpoints 50000 100000 --arms base
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
from sim.simulation import Batch  # noqa: E402
from sim.snapshot import save_snapshot  # noqa: E402
from ladder import MIN_DIET, MIN_NUTRIENT, MIN_TYPES, NURSERY_RULES, NURSERY_SEEDS, WORLD_SETS, world  # noqa: E402
from sweep import run_batch  # noqa: E402

ARMS = {"base": (16, {}), "both32": (32, {"craving_sense": True, "mate_sense": True})}
CHECKPOINTS = (50_000, 100_000, 200_000, 350_000, 500_000, 700_000)


def shape(dims: int, arm: str) -> tuple:
    hidden, rules = ARMS[arm]
    return (dims, *WORLD_SETS["time"][dims], hidden, tuple(sorted(rules.items())))


def folder(out: Path, dims: int, arm: str, nseed: int, tick: int) -> Path:
    return out / f"d{dims}-{arm}-n{nseed}-t{tick}"


def train(job: tuple) -> str:
    dims, arm, nseed, checkpoints, out = job
    sim = Simulation(Config(**{**world(shape(dims, arm)), **NURSERY_RULES, "seed": nseed}), log_every=1000)
    done = 0
    for tick in checkpoints:
        sim.run(tick - done)
        done = tick
        save_snapshot(sim, folder(out, dims, arm, nseed, tick))
    return f"trained d{dims} {arm} n{nseed} to {done:,}"


def play(job: tuple) -> list[dict]:
    dims, arm, tick, seeds, ticks, out = job
    base = world(shape(dims, arm))
    nseeds = NURSERY_SEEDS if tick else (None,)
    runs = [({**base, **({"brains_from": str(folder(out, dims, arm, n, tick))} if n is not None else {})},
             seed, ticks, 0.5, 250) for n in nseeds for seed in range(seeds)]
    return [{"dims": dims, "arm": arm, "nursery_ticks": tick, **row} for row in run_batch(runs)]


def report(rows: list[dict]) -> None:
    print(f"\n{'arm':>7} {'ticks':>8} {'clpse':>6} {'nutr':>5} {'diet':>5} {'types':>5}  goals (nutrient "
          f"{MIN_NUTRIENT}, diet {MIN_DIET}, types {MIN_TYPES})")
    for arm in sorted({r["arm"] for r in rows}):
        for t in sorted({int(r["nursery_ticks"]) for r in rows if r["arm"] == arm}):
            rs = [r for r in rows if r["arm"] == arm and int(r["nursery_ticks"]) == t]
            m = {k: float(np.nanmean([r[k] for r in rs]))
                 for k in ("collapse_rate", "min_nutrient", "diet_diversity", "zone_types_per_life")}
            marks = " ".join("Y" if ok else "." for ok in (m["min_nutrient"] >= MIN_NUTRIENT,
                             m["diet_diversity"] >= MIN_DIET, m["zone_types_per_life"] >= MIN_TYPES))
            print(f"{arm:>7} {t:>8,} {m['collapse_rate']:6.2f} {m['min_nutrient']:5.2f} "
                  f"{m['diet_diversity']:5.2f} {m['zone_types_per_life']:5.2f}  {marks}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, default=4)
    ap.add_argument("--arms", nargs="+", default=list(ARMS))
    ap.add_argument("--checkpoints", type=int, nargs="+", default=list(CHECKPOINTS))
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--ticks", type=int, default=10_000)
    ap.add_argument("--out", default="snapshots/long")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    csv_path = Path(args.csv or f"runs/long-nursery-{args.dims}d.csv")
    out, cps = Path(args.out), sorted(args.checkpoints)
    if not args.report_only:
        jobs = [(args.dims, a, n, cps, out) for a in args.arms for n in NURSERY_SEEDS]
        with ProcessPoolExecutor(len(jobs)) as pool:
            for fut in as_completed([pool.submit(train, j) for j in jobs]):
                print("  ", fut.result(), flush=True)
        plays = [(args.dims, a, t, args.seeds, args.ticks, out) for a in args.arms for t in [0] + cps]
        rows = []
        with ProcessPoolExecutor(min(os.cpu_count() or 1, len(plays))) as pool:
            for fut in as_completed([pool.submit(play, j) for j in plays]):
                rows.extend(fut.result())
                print(f"  play {len(rows)}", flush=True)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    rows = []
    with csv_path.open() as f:
        for r in csv.DictReader(f):
            rows.append({k: (v if k == "arm" else float(v) if v not in ("", "nan") else math.nan)
                         for k, v in r.items()})
    report(rows)


if __name__ == "__main__":
    main()
