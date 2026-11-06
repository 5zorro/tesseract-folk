"""Training time vs the number of brain outputs (5zorro, 2026-11-06: "one of the
findings should be the quantity of training time vs the number of outputs. I
want to get that relationship down and tested").

The task stays fixed; only the output count changes: optional actions are
switched off (`actions_off`) or do-nothing copies of `stay` are added
(`extra_stay_actions`). For each arm, fixed-rules nurseries (as the ladder's)
are saved at checkpoints along one run, and each checkpoint is scored in play
worlds; scratch brains are the 0-tick point. From the learning curves:
ticks for nursery brains to reach a collapse-rate target (interpolated in log
ticks), and the fitted exponent k in ticks ~ outputs^k.

Mutations per child are held fixed (Config.mutations_per_birth), so more
outputs also means each weight mutates less often: that's part of the cost
being measured, as it would be for real extra actions.

    python scripts/outputs_vs_time.py                    # 2D, ~10 min on 16 cores
    python scripts/outputs_vs_time.py --dims 3 --report-only
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
from ladder import NURSERY_RULES, NURSERY_SEEDS, WORLD_SETS, read_csv, world  # noqa: E402
from sweep import run_batch  # noqa: E402

OPTIONAL = "pick_up+give+pray+worship+share"
ARMS = {"off5": dict(actions_off=OPTIONAL), "base": {}, "plus8": dict(extra_stay_actions=8),
        "plus16": dict(extra_stay_actions=16), "plus32": dict(extra_stay_actions=32)}
CHECKPOINTS = (2_500, 5_000, 10_000, 20_000, 40_000)


def shape(dims: int, arm: str) -> tuple:
    size, radius = WORLD_SETS["time"][dims]
    return (dims, size, radius, 16, tuple(sorted(ARMS[arm].items())))


def outputs(dims: int, arm: str) -> int:
    return Simulation(Config(**world(shape(dims, arm)), initial_npcs=1), log_every=10**9).n_outputs


def folder(out: Path, dims: int, arm: str, nseed: int, tick: int) -> Path:
    return out / f"d{dims}-{arm}-n{nseed}-t{tick}"


def train(job: tuple) -> list[str]:
    dims, arm, out = job
    sims = [Simulation(Config(**{**world(shape(dims, arm)), **NURSERY_RULES, "seed": n}), log_every=1000)
            for n in NURSERY_SEEDS]
    Batch(sims)
    done = 0
    for tick in CHECKPOINTS:
        sims[0].run(tick - done)
        done = tick
        for n, sim in zip(NURSERY_SEEDS, sims):
            save_snapshot(sim, folder(out, dims, arm, n, tick))
    return [f"trained d{dims} {arm}"]


def play(job: tuple) -> list[dict]:
    dims, arm, tick, seeds, ticks, out = job
    base = world(shape(dims, arm))
    nseeds = NURSERY_SEEDS if tick else (None,)
    runs = [({**base, **({"brains_from": str(folder(out, dims, arm, n, tick))} if n is not None else {})},
             seed, ticks, 0.5, 250) for n in nseeds for seed in range(seeds)]
    rows = run_batch(runs)
    return [{"dims": dims, "arm": arm, "outputs": outputs(dims, arm), "nursery_ticks": tick,
             "nursery": n if n is not None else -1, **row}
            for (n, row) in zip([n for n in nseeds for _ in range(seeds)], rows)]


def report(rows: list[dict]) -> None:
    arms = sorted({r["arm"] for r in rows}, key=lambda a: min(r["outputs"] for r in rows if r["arm"] == a))
    ticks = sorted({int(r["nursery_ticks"]) for r in rows})
    mean = {}
    for a in arms:
        for t in ticks:
            vals = [r["collapse_rate"] for r in rows if r["arm"] == a and int(r["nursery_ticks"]) == t
                    and not math.isnan(r["collapse_rate"])]
            mean[a, t] = float(np.mean(vals)) if vals else math.nan
    print("\nCollapses per 1,000 ticks in play, by nursery ticks (0 = scratch)")
    print(f"{'arm':>7} {'outputs':>7} " + " ".join(f"{t:>7}" for t in ticks))
    for a in arms:
        o = int(next(r["outputs"] for r in rows if r["arm"] == a))
        print(f"{a:>7} {o:>7} " + " ".join(f"{mean[a, t]:7.2f}" for t in ticks))
    # Target: 60% of the way from scratch to the best final, averaged over arms.
    start = np.nanmean([mean[a, 0] for a in arms])
    best = np.nanmin([mean[a, ticks[-1]] for a in arms])
    target = start - 0.6 * (start - best)
    print(f"\nTicks to reach {target:.2f} collapses (60% of the way from scratch {start:.2f} "
          f"to the best final {best:.2f}), interpolated in log ticks:")
    xs, ys = [], []
    for a in arms:
        curve = [(t, mean[a, t]) for t in ticks if t > 0]
        hit = math.nan
        for (t0, v0), (t1, v1) in zip([(ticks[1] / 2, mean[a, 0])] + curve[:-1], curve):
            if v0 > target >= v1:
                f = (v0 - target) / (v0 - v1)
                hit = math.exp(math.log(t0) + f * (math.log(t1) - math.log(t0)))
                break
        o = int(next(r["outputs"] for r in rows if r["arm"] == a))
        print(f"  {a:>7} ({o} outputs): " + (f"{hit:,.0f}" if not math.isnan(hit) else "not reached"))
        if not math.isnan(hit):
            xs.append(math.log(o))
            ys.append(math.log(hit))
    if len(xs) >= 3:
        k, c = np.polyfit(xs, ys, 1)
        print(f"\nFit: ticks ~ outputs^{k:.2f} (ticks = {math.exp(c):.3g} x outputs^{k:.2f}, "
              f"{len(xs)} arms)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, default=2)
    ap.add_argument("--arms", nargs="+", default=list(ARMS))
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--ticks", type=int, default=5_000)
    ap.add_argument("--out", default="snapshots/outputs")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--jobs", type=int, default=None)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    csv_path = Path(args.csv or f"runs/outputs-vs-time-{args.dims}d.csv")
    if not args.report_only:
        out, workers = Path(args.out), args.jobs or os.cpu_count() or 1
        with ProcessPoolExecutor(min(workers, len(args.arms))) as pool:
            for fut in as_completed([pool.submit(train, (args.dims, a, out)) for a in args.arms]):
                print("  ", *fut.result(), flush=True)
        jobs = [(args.dims, a, t, args.seeds, args.ticks, out) for a in args.arms for t in (0,) + CHECKPOINTS]
        rows = []
        with ProcessPoolExecutor(min(workers, len(jobs))) as pool:
            for fut in as_completed([pool.submit(play, j) for j in jobs]):
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
