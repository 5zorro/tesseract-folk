"""Does a working 4D brain exist? (M2 slice R8 follow-up, 2026-11-06.)

A hand-built linear brain (hidden_units=0, craving_sense on) wired to do what
the sense-only forager does: step along the craving (the needed food's scent
gradient), eat when there's food here, poop when the bowel is full, and
nothing else. It runs through the normal action draw (softmax over outputs at
`action_temperature`), with mutation off so every copy and child stays
hand-built. `--sharpness` scales every weight: high values make the draw
nearly an argmax, so the gap between sharpness levels is the cost of the draw
itself.

If it meets the goals in 4D, such a brain exists and evolution doesn't find it;
if it fails even when sharp, the action draw and the rules are the limit.

    python scripts/probe_handbrain.py
    python scripts/probe_handbrain.py --dims 4 --sharpness 1 3 10 30
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim.brain import Brain  # noqa: E402
from sim.simulation import Batch  # noqa: E402
from ladder import MIN_DIET, MIN_NUTRIENT, MIN_TYPES, WORLD_SETS  # noqa: E402
from sweep import Run  # noqa: E402

FIXED = {"hidden_units": 0, "craving_sense": True, "mutations_per_birth": 0.0,
         "mutation_rate": 0.0, "mutation_lineage": False}


def hand_brain(sim, sharpness: float) -> Brain:
    """Linear weights (outputs x inputs) for: follow the craving, eat on food, poop when full."""
    L, A = sim.sense_layout(), {a: i for i, a in enumerate(sim.actions)}
    w = np.zeros((sim.n_outputs, sim.n_inputs))
    b = np.zeros(sim.n_outputs)
    b[:sim.n_actions] = -3.0                                  # everything else: rarely
    crave = np.arange(L["craving"].start, L["craving"].stop)
    for axis, col in enumerate(crave):
        w[A[f"move+{axis}"], col], w[A[f"move-{axis}"], col] = 3.0, -3.0
        b[A[f"move+{axis}"]] = b[A[f"move-{axis}"]] = 0.0
    eat = A.get("eat_need", A.get("eat"))
    w[eat, L["food_here"]] = 6.0 * sim.cfg.food_capacity / sim.cfg.bite_size   # ~+6 per bite here
    b[eat] = -2.0
    w[A["poop"], L["bowel"]] = 8.0                             # bowel share of capacity
    b[A["poop"]] = -6.0
    return Brain(np.zeros((0, sim.n_inputs)), np.zeros(0), w * sharpness, b * sharpness)


def job(args: tuple) -> tuple:
    dims, sharpness, seeds, ticks = args
    size, radius = WORLD_SETS["time"][dims]
    runs = [Run({"dims": dims, "size": size, "food_patch_radius": radius, **FIXED}, seed, ticks, 0.5, 250)
            for seed in seeds]
    batch = Batch([r.sim for r in runs])
    for r in runs:
        brain = hand_brain(r.sim, sharpness)
        for slot in r.sim.pop.live(r.sim.index).tolist():
            r.sim.pop.set_brain(slot, brain)
    for _ in range(ticks):
        for r in runs:
            r.before_tick()
        batch.step()
        for r in runs:
            r.after_tick()
    return dims, sharpness, [r.result() for r in runs]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", default=[2, 3, 4])
    ap.add_argument("--sharpness", type=float, nargs="+", default=[0.3, 1.0, 3.0])
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--ticks", type=int, default=10_000)
    args = ap.parse_args()
    jobs = [(d, k, range(args.seeds), args.ticks) for d in args.dims for k in args.sharpness]
    print(f"{'dims':>4} {'sharp':>5} {'clpse':>6} {'nutr':>5} {'diet':>5} {'types':>5}  "
          f"goals (nutrient {MIN_NUTRIENT}, diet {MIN_DIET}, types {MIN_TYPES})")
    with ProcessPoolExecutor(len(jobs)) as pool:
        for dims, k, rows in pool.map(job, jobs):
            m = {key: float(np.nanmean([r[key] for r in rows]))
                 for key in ("collapse_rate", "min_nutrient", "diet_diversity", "zone_types_per_life")}
            marks = " ".join("Y" if ok else "." for ok in (m["min_nutrient"] >= MIN_NUTRIENT,
                             m["diet_diversity"] >= MIN_DIET, m["zone_types_per_life"] >= MIN_TYPES))
            print(f"{dims:>4} {k:5g} {m['collapse_rate']:6.2f} {m['min_nutrient']:5.2f} "
                  f"{m['diet_diversity']:5.2f} {m['zone_types_per_life']:5.2f}  {marks}")


if __name__ == "__main__":
    main()
