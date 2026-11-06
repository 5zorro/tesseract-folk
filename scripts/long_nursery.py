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
    python scripts/long_nursery.py --dims 3 --arms h4 h8 h16 h32 h64 \
        --checkpoints 2500 5000 10000 20000 40000 80000 160000 --out snapshots/sizes
        # brain size vs ideal training length (report_sizes)
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

ARMS = {"base": (16, {}), "both32": (32, {"craving_sense": True, "mate_sense": True}),
        "both64": (64, {"craving_sense": True, "mate_sense": True})}   # 5zorro: "the 64 ... brain"
CHECKPOINTS = (50_000, 100_000, 200_000, 350_000, 500_000, 700_000)


def arm_spec(arm: str) -> tuple[int, dict]:
    """A named arm, or `h<N>`: N hidden units and today's senses (brain size only)."""
    if arm in ARMS:
        return ARMS[arm]
    if arm.startswith("h") and arm[1:].isdigit():
        return int(arm[1:]), {}
    raise ValueError(f"unknown arm {arm!r}: one of {', '.join(ARMS)} or h<hidden units>")


def shape(dims: int, arm: str) -> tuple:
    hidden, rules = arm_spec(arm)
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


def ideal_ticks(curve: list[tuple[int, float]], within: float = 0.10) -> tuple[int, float]:
    """(tick of the best score, ticks to first get within `within` of the way from
    scratch to the best: interpolated in log ticks). Lower scores are better."""
    best_t, best = min(curve[1:], key=lambda c: c[1])
    start = curve[0][1]
    target = best + within * (start - best)
    points = [(curve[1][0] / 2, start)] + curve[1:]
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if v0 > target >= v1:
            f = (v0 - target) / (v0 - v1)
            return best_t, math.exp(math.log(t0) + f * (math.log(t1) - math.log(t0)))
    return best_t, math.nan


def report_sizes(rows: list[dict]) -> None:
    """Brain size vs ideal training length (5zorro: "what was the ideal training
    tick size for each brain size? I want that relationship to be down")."""
    sized = sorted({r["arm"] for r in rows if r["arm"].startswith("h") and r["arm"][1:].isdigit()},
                   key=lambda a: int(a[1:]))
    if len(sized) < 2:
        return
    dims = int(rows[0]["dims"])
    n_in = n_out = None
    print("\nBrain size vs training length (collapses; scratch = tick 0):")
    xs, best_ys, near_ys = [], [], []
    for arm in sized:
        hidden = int(arm[1:])
        if n_in is None:
            s = Simulation(Config(**world(shape(dims, arm)), initial_npcs=1), log_every=10**9)
            n_in, n_out = s.n_inputs, s.n_outputs
        weights = n_in * hidden + hidden + hidden * n_out + n_out if hidden else n_in * n_out + n_out
        curve = []
        for t in sorted({int(r["nursery_ticks"]) for r in rows if r["arm"] == arm}):
            vals = [r["collapse_rate"] for r in rows if r["arm"] == arm and int(r["nursery_ticks"]) == t
                    and not math.isnan(r["collapse_rate"])]
            curve.append((t, float(np.mean(vals))))
        best_t, near_t = ideal_ticks(curve)
        best = min(v for _, v in curve[1:])
        print(f"  {hidden:>3} hidden ({weights:>5,} weights): best {best:.2f} at {best_t:>7,} ticks; "
              f"within 10% of it by " + (f"{near_t:>8,.0f}" if not math.isnan(near_t) else "never") +
              ("  (best at the last checkpoint: may still be improving)" if best_t == curve[-1][0] else ""))
        xs.append(math.log(weights))
        best_ys.append(math.log(best_t))
        near_ys.append(math.log(near_t) if not math.isnan(near_t) else math.nan)
    ok = [i for i, y in enumerate(near_ys) if not math.isnan(y)]
    if len(ok) >= 3:
        k, c = np.polyfit([xs[i] for i in ok], [near_ys[i] for i in ok], 1)
        print(f"  fit: ticks to within 10% ~ weights^{k:.2f} ({len(ok)} sizes)")


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
    report_sizes(rows)


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
