"""The hunger limit (5zorro, 2026-11-06): raise hunger step by step until
births go down and never recover. M2 slice R11.

One world per (dims, arm, seed) starts from scratch at the lowest hunger and
holds each level for `HOLD[dims]` ticks, so brains can adapt before the next
step (a staircase, not a ramp: each level gets its own numbers). Hunger scales
`nutrient_decay` and `metabolism_rate` together, as the anneal nursery does
(scripts/anneal.py HUNGER). Each level is scored on its second half.

    python scripts/hunger_ladder.py                       # 2D-4D, both arms, 2 seeds
    python scripts/hunger_ladder.py --dims 2 --hold 2000  # quick look
    python scripts/hunger_ladder.py --report-only

Arms: "off" = today's defaults; "kids" = the hall of fame rewards children
(hall_of_fame_birth_weight 5, the old fitness's child = 5 collapses) and keeps
parents until their children's lives are in (hall_of_fame_child_credit).

Finish line (5zorro): the lowest hunger from which births stay down at every
higher level. "Down" = below `--down` (default 10%) of the arm's peak births.
Other behaviors (gives, prayers, worships, shared secrets) are reported per NPC
per 1,000 ticks alongside, to see where they stop.
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
from sim.snapshot import save_snapshot  # noqa: E402
from anneal import HUNGER  # noqa: E402
from ladder import WORLD_SETS, world  # noqa: E402

LEVELS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0)
HOLD = {2: 20_000, 3: 30_000, 4: 60_000}     # ~ the nursery knee per dimension (slice R7)
ARMS = {"off": {}, "kids": {"hall_of_fame_birth_weight": 5.0, "hall_of_fame_child_credit": True}}
SEEDS = (0, 1)
LOG_EVERY = 1000
BEHAVIORS = {"gives": ("gives",), "prayers": ("prayers_answered", "prayers_silent", "prayers_ignored"),
             "worships": ("worships",), "secrets_shared": ("secrets_shared",)}
CAUSES = ("nutrient_starve", "body_starve", "stink", "smite", "elder")


def config(dims: int, arm: str, seed: int) -> Config:
    shape = (dims, *WORLD_SETS["time"][dims], Config().hidden_units, ())
    return Config(**{**world(shape), **ARMS[arm], "seed": seed})


def climb(job: tuple) -> list[dict]:
    dims, arm, seed, levels, hold, out = job
    sim = Simulation(config(dims, arm, seed), log_every=LOG_EVERY)
    normal = {k: getattr(sim.cfg, k) for k in HUNGER}
    rows = []
    for level in levels:
        for k in HUNGER:
            sim.set_rule(k, normal[k] * level)
        start = sim.tick
        sim.run(hold)
        late = [h for h in sim.stats.history if h["tick"] > start + hold // 2]
        ticks = LOG_EVERY * len(late)
        pop = float(np.mean([h["population"] for h in late]))
        total = lambda *keys: sum(h.get(k, 0) for h in late for k in keys)   # noqa: E731
        collapses = total("collapses")
        row = {"dims": dims, "arm": arm, "seed": seed, "hunger": level, "tick": sim.tick,
               "population": pop, "births": 1000.0 * total("births") / ticks,
               "births_per_npc": 1000.0 * total("births") / ticks / pop,
               "collapse_rate": 1000.0 * collapses / ticks / pop,
               "deaths": 1000.0 * total("deaths") / ticks, "spawns": 1000.0 * total("spawns") / ticks,
               "mean_generation": float(np.mean([h["mean_generation"] for h in late])),
               "diet": float(np.mean([h["diet_diversity"] for h in late]))}
        for c in CAUSES:
            row[f"cause_{c}"] = total(f"collapse_{c}") / collapses if collapses else math.nan
        for name, keys in BEHAVIORS.items():
            row[name] = 1000.0 * total(*keys) / ticks / pop
        rows.append(row)
    save_snapshot(sim, Path(out) / f"d{dims}-{arm}-s{seed}-end")
    return rows


def finish(curve: list[tuple[float, float]], down: float) -> tuple[float, float]:
    """(peak births, lowest hunger from which births stay below `down` x peak at
    every higher level; nan if they never stay down)."""
    peak = max(b for _, b in curve)
    for i, (level, _) in enumerate(curve):
        if all(b < down * peak for _, b in curve[i:]):
            return peak, level
    return peak, math.nan


def report(rows: list[dict], down: float) -> None:
    for dims in sorted({int(r["dims"]) for r in rows}):
        for arm in sorted({r["arm"] for r in rows if int(r["dims"]) == dims}):
            rs = [r for r in rows if int(r["dims"]) == dims and r["arm"] == arm]
            levels = sorted({r["hunger"] for r in rs})
            mean = {lv: {k: float(np.nanmean([r[k] for r in rs if r["hunger"] == lv])) for k in rs[0]
                         if k not in ("arm",)} for lv in levels}
            print(f"\n{dims}D, arm {arm} ({len({r['seed'] for r in rs})} seeds; per 1,000 ticks; "
                  f"behaviors per NPC)")
            print(f"{'hunger':>6} {'pop':>5} {'births':>6} {'/npc':>5} {'clpse':>5} {'spawns':>6} "
                  f"{'starve':>6} {'body':>5} {'stink':>5} {'gives':>6} {'prays':>6} {'worsh':>5} {'gen':>5}")
            for lv in levels:
                m = mean[lv]
                print(f"{lv:6.2f} {m['population']:5.0f} {m['births']:6.2f} {m['births_per_npc']:5.2f} "
                      f"{m['collapse_rate']:5.2f} {m['spawns']:6.2f} {m['cause_nutrient_starve']:6.2f} "
                      f"{m['cause_body_starve']:5.2f} {m['cause_stink']:5.2f} {m['gives']:6.2f} "
                      f"{m['prayers']:6.2f} {m['worships']:5.2f} {m['mean_generation']:5.0f}")
            peak, at = finish([(lv, mean[lv]["births"]) for lv in levels], down)
            print(f"  finish: births stay below {down:.0%} of their peak ({peak:.2f}) from hunger "
                  + (f"{at:g}x on" if not math.isnan(at) else "- (never within these levels)"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", default=[2, 3, 4])
    ap.add_argument("--arms", nargs="+", default=list(ARMS), choices=list(ARMS))
    ap.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    ap.add_argument("--levels", type=float, nargs="+", default=list(LEVELS))
    ap.add_argument("--hold", type=int, default=None, help="ticks per level (default: HOLD per dims)")
    ap.add_argument("--down", type=float, default=0.10, help="'down' = below this fraction of peak births")
    ap.add_argument("--out", default="snapshots/hunger")
    ap.add_argument("--csv", default="runs/hunger-ladder.csv")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    path = Path(args.csv)
    if not args.report_only:
        jobs = [(d, a, s, sorted(args.levels), args.hold or HOLD[d], args.out)
                for d in sorted(args.dims, reverse=True) for a in args.arms for s in args.seeds]
        rows = []
        with ProcessPoolExecutor(min(args.jobs, len(jobs))) as pool:
            for fut in as_completed([pool.submit(climb, j) for j in jobs]):
                rows.extend(fut.result())
                print(f"  climbed {len(rows) // len(args.levels)}/{len(jobs)}", flush=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    with path.open() as f:
        rows = [{k: (v if k == "arm" else float(v) if v not in ("", "nan") else math.nan) for k, v in r.items()}
                for r in csv.DictReader(f)]
    report(rows, args.down)


if __name__ == "__main__":
    main()
