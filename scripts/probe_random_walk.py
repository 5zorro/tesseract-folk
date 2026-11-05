"""Probe (5zorro, 2026-11-05): how much harder is it for a random walker to stumble
onto the food it needs as dimensions grow?

In each travel-time world (scripts/ladder.py, WORLD_SETS["time"], plus 1D from
the coverage set), walkers start at random cells in one food type's cores and
take random unit steps (what a brain that hasn't learned to steer does). How
many steps until they reach a core of a different food type? Compared with the
shortest trip (L1, scripts/travel_time.py) and with the hunger clock (~300 ticks
from full to starving).

    python scripts/probe_random_walk.py
    python scripts/probe_random_walk.py --scaling   # same width, only dims change

--scaling (5zorro's question: what's the base of the exponential?): one round
target of radius 2 in a world of fixed width, walkers starting 4 cells away;
mean steps to reach it in 1D-4D. Each extra dimension multiplies the time by
about the same factor, roughly 0.7 x width / target radius (2026-11-05: 3.5x at
width 10, 4.8x at width 14). The base comes from the world, not a constant.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim import Config  # noqa: E402
from sim.world import World  # noqa: E402
from ladder import WORLD_SETS  # noqa: E402
from travel_time import l1_distance_to  # noqa: E402

WALKERS, MAX_STEPS, HUNGER_CLOCK = 4000, 20_000, 300
WORLDS = {1: WORLD_SETS["coverage"][1], **WORLD_SETS["time"]}


def walk(cfg: Config, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Steps for each walker from a type-a core to any type-b core (b != a), and
    the shortest L1 trip from each start."""
    w = World(cfg, np.random.default_rng(seed))
    rng = np.random.default_rng(1000 + seed)
    cores = w.zones >= 0
    steps_all, short_all = [], []
    types = cores.shape[0]
    for a in range(types):
        starts = np.argwhere(cores[a])
        if not len(starts):
            continue
        target = np.zeros_like(cores[0])
        for b in range(types):
            if b != a:
                target |= cores[b]
        target &= ~cores[a]                  # overlapping cells don't count as a trip
        if not target.any():
            continue
        dist = l1_distance_to(target, cfg.dims)
        pos = starts[rng.integers(len(starts), size=WALKERS)].copy()
        short_all.append(dist[tuple(pos.T)])
        steps = np.full(WALKERS, MAX_STEPS)
        active = np.ones(WALKERS, dtype=bool)
        for t in range(1, MAX_STEPS + 1):
            n = int(active.sum())
            if n == 0:
                break
            axis = rng.integers(cfg.dims, size=n)
            sign = rng.choice((-1, 1), size=n)
            idx = np.nonzero(active)[0]
            pos[idx, axis] = (pos[idx, axis] + sign) % cfg.size
            hit = target[tuple(pos[idx].T)]
            steps[idx[hit]] = t
            active[idx[hit]] = False
        steps_all.append(steps)
    return np.concatenate(steps_all), np.concatenate(short_all)


def hit_time(dims: int, width: int, radius: int, start: int, walkers: int = 1500,
             cap: int = 400_000, seed: int = 0) -> float:
    """Mean steps for a random walk to enter a ball of `radius` at the world's
    center, starting `start` cells from the center along axis 0."""
    rng = np.random.default_rng(seed)
    c = width // 2
    pos = np.full((walkers, dims), c)
    pos[:, 0] = (c + start) % width
    steps = np.full(walkers, cap)
    active = np.ones(walkers, dtype=bool)
    for t in range(1, cap + 1):
        idx = np.nonzero(active)[0]
        if not len(idx):
            break
        axis = rng.integers(dims, size=len(idx))
        pos[idx, axis] = (pos[idx, axis] + rng.choice((-1, 1), size=len(idx))) % width
        delta = np.abs(pos[idx] - c)
        delta = np.minimum(delta, width - delta)
        hit = (delta ** 2).sum(axis=1) <= radius * radius
        steps[idx[hit]] = t
        active[idx[hit]] = False
    return float(steps.mean())


def scaling() -> None:
    print("Same width, same target (radius 2), same start (4 cells away); only dims change")
    for width in (10, 14):
        prev = None
        for dims in (1, 2, 3, 4):
            mean = hit_time(dims, width, 2, 4)
            factor = f"x{mean / prev:4.1f} per extra dimension" if prev else ""
            print(f"  width {width:2d}  {dims}D  mean steps {mean:7.0f}  {factor}")
            prev = mean


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scaling", action="store_true")
    if ap.parse_args().scaling:
        scaling()
        return
    print(f"Random walk from one food's core to another food's core ({WALKERS} walkers per type, 4 maps)")
    print(f"{'dims':>4} {'size':>5} {'shortest':>8} {'walk median':>11} {'walk mean':>9} "
          f"{'x shortest':>10} {'within 300':>10}")
    for dims, (size, radius) in WORLDS.items():
        cfg_kw = dict(dims=dims, size=size, food_patch_radius=radius)
        steps, short = zip(*(walk(Config(**cfg_kw, seed=s), s) for s in range(4)))
        steps, short = np.concatenate(steps), np.concatenate(short)
        print(f"{dims:>4} {size:>5} {np.median(short):8.1f} {np.median(steps):11.0f} {steps.mean():9.0f} "
              f"{np.median(steps) / max(np.median(short), 1):10.1f} {(steps <= HUNGER_CLOCK).mean():10.0%}")


if __name__ == "__main__":
    main()
