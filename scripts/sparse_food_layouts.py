"""Sparse-food design (docs/plan-memory-reaction.md, after the scent probe):
for candidate food layouts, how hidden is food from an NPC's local senses?

World-only runs (no NPCs) to the food steady state, then per food type:
meal cells (food > a bite), directed distance from random cells to the nearest
meal, and the random-walk time to hit one (what a forager with only local senses
pays, roughly), against the nutrient slack (ticks from full to empty).
Total capacity is held at the baseline's by scaling food_capacity.
Static proxy only: NPCs eating thin the meals further.

    python scripts/sparse_food_layouts.py      # ~10 minutes
"""
import sys
from pathlib import Path

import numpy as np

sys.path[:0] = [str(Path(__file__).resolve().parent.parent), str(Path(__file__).resolve().parent)]
from mr1_ladder import play_rules  # noqa: E402
from sim import Config, Simulation  # noqa: E402

TICKS = 3000
WALKERS = 3000
CAP = 4000


def world(dims, radius, patches, cap, seed):
    rules = {**play_rules(dims, 3, {}), "seed": seed, "initial_npcs": 0, "min_population": 0,
             "food_patch_radius": radius, "food_patches_per_type": patches, "food_capacity": cap}
    sim = Simulation(Config(**rules))
    return sim


def measure(sim, rng):
    b, c = sim.batch, sim.cfg
    size, d, T = b.size, c.dims, c.n_food_types
    shape = (size,) * d
    food = b.food.reshape(b.W, T, -1)[0]
    out = []
    for t in range(T):
        meal = (food[t] > c.bite_size).reshape(shape)
        cells = np.flatnonzero(meal.ravel())
        # directed: L1 torus distance from random cells to nearest meal
        idx = np.array(np.unravel_index(np.arange(size ** d), shape)).T
        src = idx[cells]
        start = rng.integers(0, size, (WALKERS, d))
        dd = np.abs(start[:, None, :] - src[None, :, :])
        dist = np.minimum(dd, size - dd).sum(-1).min(1)
        # random walk until a meal cell
        pos = start.copy()
        hit = meal[tuple(pos.T)].copy()
        steps = np.zeros(WALKERS)
        for s in range(1, CAP + 1):
            live = ~hit
            if not live.any():
                break
            axis = rng.integers(0, d, live.sum())
            sign = rng.choice([-1, 1], live.sum())
            p = pos[live]
            p[np.arange(len(p)), axis] = (p[np.arange(len(p)), axis] + sign) % size
            pos[live] = p
            steps[live] = s
            hit[live] = meal[tuple(p.T)]
        out.append((meal.mean(), np.median(dist), np.percentile(dist, 90), np.median(steps),
                    np.mean(steps), food[t].sum()))
    return np.array(out).mean(0)



def main() -> None:
    rng = np.random.default_rng(0)
    for dims, base_r, grid in ((2, 4.0, [(4.0, 3), (2.0, 3), (2.0, 1), (1.5, 1)]),
                               (4, 1.23, [(1.23, 3), (0.9, 3), (0.9, 1), (0.7, 1)])):
        base = world(dims, base_r, 3, 2.0, 1)
        base_cap = base.batch.capacity.sum()
        decay = base.cfg.nutrient_decay
        print(f"\n=== {dims}D size {base.cfg.size}; nutrient slack 1/decay = {1/decay:.0f} ticks ===")
        print("radius patches cap   meal%  dist p50 p90  walk p50  mean   food total")
        for radius, patches in grid:
            probe = world(dims, radius, patches, 2.0, 1)
            cap = 2.0 * base_cap / probe.batch.capacity.sum()
            rows = []
            for seed in (1, 2, 3):
                sim = world(dims, radius, patches, cap, seed)
                sim.run(TICKS)
                rows.append(measure(sim, rng))
            m = np.mean(rows, 0)
            print(f"{radius:6.2f} {patches:5d} {cap:5.1f} {100*m[0]:6.2f}%  {m[1]:6.1f} {m[2]:4.0f}  {m[3]:7.0f} {m[4]:6.0f}   {m[5]:8.0f}")


if __name__ == "__main__":
    main()
