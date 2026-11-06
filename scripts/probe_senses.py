"""Do the senses carry enough information in each dimension? (5zorro,
2026-11-06: "are the 4D senses giving bad results?")

Runs play worlds (matched on travel time, as `ladder.py --worlds time`) under
three hand-written foragers and scores them with the ladder's goals:
`sense` (sim.controllers.SenseController) sees only the sense vector, like a
brain; `scripted` reads the world directly (food in the neighbor cells). If
`sense` meets the goals where brains fail, the senses are enough and the limit
is learning; if it fails too, it's the senses or the world. Also prints how
often the needed food's scent gave the oracle no direction ("blind").

    python scripts/probe_senses.py
    python scripts/probe_senses.py --dims 4 --set scent_decay=0.005
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim.config import parse_overrides  # noqa: E402
from sim.simulation import Batch  # noqa: E402
from ladder import MIN_DIET, MIN_NUTRIENT, MIN_TYPES, WORLD_SETS  # noqa: E402
from sweep import Run  # noqa: E402


def job(args: tuple) -> tuple:
    dims, controller, seeds, ticks, overrides = args
    size, radius = WORLD_SETS["time"][dims]
    runs = [Run({"dims": dims, "size": size, "food_patch_radius": radius, **overrides,
                 "controller": controller}, seed, ticks, 0.5, 250) for seed in seeds]
    batch = Batch([r.sim for r in runs])
    for _ in range(ticks):
        for r in runs:
            r.before_tick()
        batch.step()
        for r in runs:
            r.after_tick()
    rows = [r.result() for r in runs]
    oracle = [r.scripted for r in runs if hasattr(r.scripted, "blind")]
    decisions = sum(o.decisions for o in oracle)
    blind = sum(o.blind for o in oracle) / decisions if decisions else float("nan")
    zero = sum(o.scent_zero for o in oracle) / decisions if decisions else float("nan")
    return dims, controller, rows, blind, zero


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", default=[2, 3, 4])
    ap.add_argument("--controllers", nargs="+", default=["sense", "scripted"])
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--ticks", type=int, default=10_000)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE[,...]")
    args = ap.parse_args()
    overrides: dict = {}
    for spec in args.set:
        overrides.update(parse_overrides(spec))
    jobs = [(d, c, range(args.seeds), args.ticks, overrides) for d in args.dims for c in args.controllers]
    print(f"{'dims':>4} {'forager':>8} {'clpse':>6} {'nutr':>5} {'diet':>5} {'types':>5} {'blind':>6} "
          f"{'no scent':>8}  goals (nutrient {MIN_NUTRIENT}, diet {MIN_DIET}, types {MIN_TYPES})")
    with ProcessPoolExecutor(len(jobs)) as pool:
        for dims, controller, rows, blind, zero in pool.map(job, jobs):
            m = {k: float(np.nanmean([r[k] for r in rows]))
                 for k in ("collapse_rate", "min_nutrient", "diet_diversity", "zone_types_per_life")}
            marks = " ".join("Y" if ok else "." for ok in (m["min_nutrient"] >= MIN_NUTRIENT,
                             m["diet_diversity"] >= MIN_DIET, m["zone_types_per_life"] >= MIN_TYPES))
            print(f"{dims:>4} {controller:>8} {m['collapse_rate']:6.2f} {m['min_nutrient']:5.2f} "
                  f"{m['diet_diversity']:5.2f} {m['zone_types_per_life']:5.2f} {blind:6.1%} {zero:8.1%}  {marks}")


if __name__ == "__main__":
    main()
