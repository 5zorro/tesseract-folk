"""Probe (research slice R2): how far does smell reach in each dimension, and
does following it lead to food?

Part 1, lone source: one cell of food in an empty world; once the smell is
steady, how fast does it fade with distance? Prints the predicted decay length
(docs/research-tuning.md §4) and the distance at which the smell drops below
10% and 1% of its peak. "reach per dim" multiplies scent_diffusion by dims / 2,
which keeps 2D's decay length.

Part 2, real worlds (the slice 3e travel-time worlds, with NPCs grazing): for
every cell outside a type's food cores, take the step toward that type's
strongest smell (the best a brain could do with the scent inputs). Does it
bring the cell closer to that type's nearest core? Reported by distance to the
core, next to the chance a random step would.

    python scripts/probe_scent.py
    python scripts/probe_scent.py --set scent_min_food=0.2
"""
from __future__ import annotations

import argparse
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim import Config, Simulation  # noqa: E402
from sim.config import parse_overrides  # noqa: E402
from sim.world import World  # noqa: E402
from ladder import WORLD_SETS  # noqa: E402
from travel_time import l1_distance_to  # noqa: E402

LONE_SIZE = {1: 81, 2: 41, 3: 21, 4: 15}
BINS = ((1, 1), (2, 2), (3, 3), (4, 5), (6, 99))
SEEDS, BURN_IN = (0, 1, 2), 1000


def predicted_length(cfg: Config) -> float:
    """Decay length of a plane wave on the grid: cosh(1/L) = 1 + dims*k / ((1-k) D)."""
    d, k = cfg.scent_diffusion, cfg.scent_decay
    return 1.0 / math.acosh(1 + cfg.dims * k / ((1 - k) * d))


def scaled(dims: int, rules: dict) -> dict:
    """The "reach per dim" variant: diffusion x dims/2 keeps 2D's decay length."""
    return {**rules, "scent_diffusion": rules.get("scent_diffusion", 0.3) * dims / 2}


def lone_source(dims: int, rules: dict) -> dict:
    size = LONE_SIZE[dims]
    w = World(Config(dims=dims, size=size, **rules), np.random.default_rng(0))
    w.food[:] = 0.0
    w.capacity[:] = 0.0
    center = (size // 2,) * dims
    w.food[(0,) + center] = 2.0
    for _ in range(1500):
        w.step()
    line = w.scent[(0,) + tuple(slice(None) if a == 0 else size // 2 for a in range(dims))]
    profile = line[size // 2:] / line[size // 2]

    def reach(frac):
        below = np.nonzero(profile < frac)[0]
        return int(below[0]) if below.size else math.inf

    return {"profile": profile[:7], "r10": reach(0.1), "r1": reach(0.01),
            "predicted": predicted_length(w.cfg)}


def follow(job: tuple) -> dict:
    """Per distance bin: how often the strongest-smell step gets closer, and chance."""
    dims, rules, seed = job
    size, radius = WORLD_SETS["time"][dims]
    sim = Simulation(Config(dims=dims, size=size, food_patch_radius=radius, hidden_units=8,
                            seed=seed, **rules), log_every=10**9)
    sim.run(BURN_IN)
    w = sim.world
    right = np.zeros(len(BINS))
    chance = np.zeros(len(BINS))
    count = np.zeros(len(BINS))
    shifts = [(ax, s) for ax in range(dims) for s in (-1, 1)]
    for t in range(w.food.shape[0]):
        dist = l1_distance_to(w.zones[t] >= 0, dims)
        # Neighbor values: np.roll(x, -s, ax)[cell] is x at cell + s along ax.
        scent_n = np.stack([np.roll(w.scent[t], -s, ax) for ax, s in shifts])
        dist_n = np.stack([np.roll(dist, -s, ax) for ax, s in shifts])
        closer = dist_n < dist[None]
        best = np.argmax(scent_n, axis=0)
        took = np.take_along_axis(closer, best[None], axis=0)[0]
        for i, (lo, hi) in enumerate(BINS):
            cells = (dist >= lo) & (dist <= hi)
            count[i] += cells.sum()
            right[i] += took[cells].sum()
            chance[i] += closer.mean(axis=0)[cells].sum()
    return {"dims": dims, "right": right, "chance": chance, "count": count}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE[,...]")
    args = ap.parse_args()
    base = {}
    for spec in args.set:
        base.update(parse_overrides(spec))
    variants = [("as built", lambda dims: base), ("reach per dim", lambda dims: scaled(dims, base))]
    if base:
        print(f"rules: {base}")

    print("\nPart 1: one food cell, steady smell along an axis (fraction of peak)")
    print(f"{'variant':<14}{'dims':>4} {'length':>6} {'<10%':>5} {'<1%':>4}  profile r=0..6")
    for name, rules in variants:
        for dims in (1, 2, 3, 4):
            r = lone_source(dims, rules(dims))
            prof = " ".join(f"{v:.3f}" for v in r["profile"])
            print(f"{name:<14}{dims:>4} {r['predicted']:6.2f} {r['r10']:>5} {r['r1']:>4}  {prof}")

    print(f"\nPart 2: travel-time worlds after {BURN_IN} ticks of grazing; step toward the "
          f"strongest smell -> closer to that food's core? (right / chance)")
    header = "  ".join(f"d={lo}" + (f"-{hi}" if hi != lo else "") if hi < 99 else f"d>={lo}"
                       for lo, hi in BINS)
    print(f"{'variant':<14}{'dims':>4}  {header}")
    with ProcessPoolExecutor() as pool:
        for name, rules in variants:
            jobs = [(dims, rules(dims), s) for dims in (2, 3, 4) for s in SEEDS]
            results = list(pool.map(follow, jobs))
            for dims in (2, 3, 4):
                rs = [r for r in results if r["dims"] == dims]
                right = sum(r["right"] for r in rs)
                chance = sum(r["chance"] for r in rs)
                count = sum(r["count"] for r in rs)
                cells = "  ".join(f"{right[i] / count[i]:.2f}/{chance[i] / count[i]:.2f}"
                                  if count[i] else "   -     " for i in range(len(BINS)))
                print(f"{name:<14}{dims:>4}  {cells}")


if __name__ == "__main__":
    main()
