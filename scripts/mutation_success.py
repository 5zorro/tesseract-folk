"""Measure (research slice R3): how often does a mutated copy beat its parent,
by how many weights were mutated?

Runs harsh nurseries (as in scripts/ladder.py) where every child, top-up and
seeded copy gets a *random* number of mutated weights, log-uniform between
--low and --high. Same population, same time, only the count differs, so the
counts can be compared fairly. Each finished life is scored by collapses per
1,000 ticks lived, against its parents' rate when it was made.

Reported per mutation-count bin: lives, the share that beat the parent (fewer
collapses per tick), tied, and did worse; the mean gain (parent rate - own
rate); then, for lives ending in the second half, the parents' and children's
mean rate, the share of parents that never collapsed, and the parent-child
correlation.

Reading (2026-11-04, plan-m2 slice R3): most chosen parents never collapsed,
and their near-clones are barely better than average, so a parent's score is
mostly luck and "beat the parent" can't drive Rechenberg's 1/5 rule. The
children's own rate by mutation count shows what mutating costs.

    python scripts/mutation_success.py                # 2D and 3D, 8 and 16 hidden units
    python scripts/mutation_success.py --dims 3 --hidden 16 --seeds 100 101 102 103
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim import Config, Simulation  # noqa: E402
from sim.config import parse_overrides  # noqa: E402
from ladder import NURSERY_RULES, WORLD_SETS  # noqa: E402

BINS = (1, 2, 5, 10, 20, 50, 100, 1e9)


class RandomMutations(Simulation):
    """Each copy gets a random number of mutated weights (through sim.rng)."""
    low, high = 1.0, 150.0

    def mutation_rate(self, brain, lineage):
        k = math.exp(self.rng.uniform(math.log(self.low), math.log(self.high)))
        return min(1.0, k / brain.n_params)


def run(job: tuple) -> list[dict]:
    dims, hidden, seed, ticks, low, high, rules = job
    size, radius = WORLD_SETS["time"][dims]
    RandomMutations.low, RandomMutations.high = low, high
    sim = RandomMutations(Config(dims=dims, size=size, food_patch_radius=radius, hidden_units=hidden,
                                 seed=seed, **NURSERY_RULES, **rules), log_every=10**9)
    sim.run(ticks)
    return [{"dims": dims, "hidden": hidden, "seed": seed, **life} for life in sim.stats.lives
            if life["mutations"] >= 0 and life["parent_rate"] >= 0]


def report(lives: list[dict]) -> None:
    half = max(r["tick"] for r in lives) / 2
    for dims in sorted({r["dims"] for r in lives}):
        for hidden in sorted({r["hidden"] for r in lives}):
            for origin in ("copy", "birth"):   # copy: a hall-of-fame top-up or seeded copy
                rows = [r for r in lives if r["dims"] == dims and r["hidden"] == hidden
                        and r["origin"] == origin]
                if not rows:
                    continue
                print(f"\n{dims}D, {hidden} hidden units, {origin} ({len(rows)} finished lives)")
                print(f"{'mutated':>9} {'lives':>6} {'beat':>5} {'tie':>5} {'worse':>5} {'gain':>6}"
                      f"  late: {'parent':>6} {'child':>6} {'p=0':>5} {'corr':>5}")
                for lo, hi in zip(BINS, BINS[1:]):
                    cell = [r for r in rows if lo <= r["mutations"] < hi]
                    if not cell:
                        continue
                    gain = np.array([r["parent_rate"] - r["rate"] for r in cell])
                    beat, tie = (gain > 1e-9).mean(), (np.abs(gain) <= 1e-9).mean()
                    late = [r for r in cell if r["tick"] > half]
                    parent = np.array([r["parent_rate"] for r in late])
                    child = np.array([r["rate"] for r in late])
                    corr = (np.corrcoef(parent, child)[0, 1]
                            if len(late) > 2 and parent.std() > 0 and child.std() > 0 else math.nan)
                    label = f"{lo:g}-{hi:g}" if hi < 1e9 else f"{lo:g}+"
                    late_part = (f"{parent.mean():6.2f} {child.mean():6.2f} {(parent == 0).mean():5.0%} "
                                 f"{corr:5.2f}" if late else "")
                    print(f"{label:>9} {len(cell):>6} {beat:5.0%} {tie:5.0%} {1 - beat - tie:5.0%} "
                          f"{gain.mean():+6.2f}        {late_part}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", default=[2, 3])
    ap.add_argument("--hidden", type=int, nargs="+", default=[8, 16])
    ap.add_argument("--seeds", type=int, nargs="+", default=[100, 101, 102, 103])
    ap.add_argument("--ticks", type=int, default=20_000)
    ap.add_argument("--low", type=float, default=1.0)
    ap.add_argument("--high", type=float, default=150.0)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE[,...]")
    ap.add_argument("--csv", type=str, default="runs/mutation-success.csv")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--jobs", type=int, default=None)
    args = ap.parse_args()
    csv_path = Path(args.csv)
    if args.report_only:
        with csv_path.open() as f:
            lives = [{k: (v if k == "origin" else int(float(v)) if k in ("dims", "hidden") else float(v))
                      for k, v in r.items()} for r in csv.DictReader(f)]
        report(lives)
        return
    rules = {}
    for spec in args.set:
        rules.update(parse_overrides(spec))
    jobs = [(d, h, s, args.ticks, args.low, args.high, rules)
            for d in args.dims for h in args.hidden for s in args.seeds]
    jobs.sort(key=lambda j: -(WORLD_SETS["time"][j[0]][0] ** j[0]) * j[1])
    workers = args.jobs or os.cpu_count() or 1
    print(f"Running {len(jobs)} nurseries ({args.ticks} ticks, {args.low:g}-{args.high:g} "
          f"mutations per copy) on {workers} processes.", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        lives = [life for part in pool.map(run, jobs) for life in part]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    keys = ["dims", "hidden", "seed", "origin", "mutations", "parent_rate", "rate", "lifetime", "tick"]
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(lives)
    print(f"Wrote {len(lives)} lives to {csv_path}")
    report(lives)


if __name__ == "__main__":
    main()
