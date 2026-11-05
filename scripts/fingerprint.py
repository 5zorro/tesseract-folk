"""Fingerprint a few short runs, to prove a speed refactor changes nothing.

Run it before and after the change; every hash must match. Covers the world
fields, every NPC's state and the rng state after 600 ticks in 2D, 3D and 4D
(the slice 3e travel-time worlds). Hashes depend on the NumPy version, so
compare runs on the same machine and environment. Times are printed too.

    python scripts/fingerprint.py
"""
from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim import Config, Simulation  # noqa: E402

WORLDS = {2: dict(size=32, food_patch_radius=4.0), 3: dict(size=14, food_patch_radius=1.88),
          4: dict(size=10, food_patch_radius=1.23)}
TICKS = 600


def fingerprint(sim: Simulation) -> str:
    h = hashlib.sha256()
    w = sim.world
    for a in (w.food, w.scent, w.stink, w.soil, w.poop):
        h.update(a.tobytes())
    for n in sim.npcs:
        h.update(np.array([*n.pos, n.body, n.health, n.bowel, n.approach_sum, n.approach_null,
                           *n.nutrients, *n.memory]).tobytes())
    h.update(repr(sim.rng.bit_generator.state).encode())
    return h.hexdigest()[:16]


def main() -> None:
    for dims, kw in WORLDS.items():
        sim = Simulation(Config(dims=dims, hidden_units=8, seed=7, **kw), log_every=100)
        start = time.perf_counter()
        sim.run(TICKS)
        print(f"{dims}D  npcs {len(sim.npcs):3d}  {fingerprint(sim)}  {time.perf_counter() - start:.1f}s")


if __name__ == "__main__":
    main()
