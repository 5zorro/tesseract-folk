"""Ticks to walk from the heart of one food's patch to the nearest heart of another food's."""
import sys
from pathlib import Path

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sim import Config
from sim.world import World

def l1_distance_to(mask, dims):
    dist = np.where(mask, 0.0, np.inf)
    frontier, k = mask.copy(), 0
    while not np.isfinite(dist).all():
        k += 1
        grown = frontier.copy()
        for ax in range(dims):
            grown |= np.roll(frontier, 1, ax) | np.roll(frontier, -1, ax)
        dist[grown & ~np.isfinite(dist)] = k
        frontier = grown
        if k > 10000: break
    return dist

def measure(kw, seeds=range(4)):
    trips, food, cells = [], [], 0
    for s in seeds:
        cfg = Config(**kw, seed=s)
        w = World(cfg, np.random.default_rng(s))
        cells = w.capacity[0].size
        food.append(w.capacity.sum())
        cores = w.zones >= 0
        for b in range(cfg.n_food_types):
            if not cores[b].any(): continue
            d = l1_distance_to(cores[b], cfg.dims)
            for a in range(cfg.n_food_types):
                if a != b and cores[a].any():
                    trips.append(d[cores[a]].mean())
    return cells, float(np.mean(food)), float(np.mean(trips))

if __name__ == "__main__":
    worlds = [("1D ladder", dict(dims=1, size=1024, food_patch_radius=55.0)),
              ("2D today", dict(dims=2, size=32)),
              ("3D ladder", dict(dims=3, size=10, food_patch_radius=1.84)),
              ("4D ladder", dict(dims=4, size=6, food_patch_radius=1.35)),
              ("4D today", dict(dims=4, size=10, food_patch_radius=2.0))]
    for name, kw in worlds:
        cells, food, trip = measure(kw)
        print(f"{name:10} cells {cells:6d} food {food:7.0f}  trip {trip:5.1f} ticks  trip/300 {trip/300:.3f}")
