"""Save and load whole simulations.

The plan: run the world without players until it stabilizes once, save that
as the baseline snapshot, and boot every new player from it instead of
re-deriving a fresh (and probably samey) world every time.

Format: a folder with world.npz (big arrays) and state.json (everything
else, including brains as plain lists so other engines can read them).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .clock import SimClock
from .config import Config
from .npc import NPC
from .nursery import entry_to_dict, hall_of_fame_entry
from .simulation import Simulation

ARRAYS = ("soil", "food", "poop", "stink", "scent", "capacity", "profiles", "zones")
FORMAT = 3   # 2 added food scent (M1 slice 6); 3 added the zone map (M2)

# Config fields added after snapshots existed, with the value that reproduces
# the behavior from before them. A snapshot saved without a field gets this
# value instead of today's default, so it resumes the way it was saved.
LEGACY = {
    "food_scent": False,           # M1 slice 6; without it, old brains wouldn't fit
    "busy_resets_idle": False,     # 2026-11-02
    "mutations_per_birth": 0.0,    # 2026-11-04: older worlds mutate per weight
    "mutation_lineage": False,     # 2026-11-04
}


def save_snapshot(sim: Simulation, path: str | Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path / "world.npz", **{k: getattr(sim.world, k) for k in ARRAYS})
    state = {
        "format": FORMAT,
        "config": sim.cfg.to_dict(),
        "tick": sim.tick,
        "next_id": sim.next_id,
        "shrines": [list(s) for s in sim.world.shrines],
        "clock": sim.clock.to_dict(),
        "deity": sim.deity.to_dict(),
        "npcs": [n.to_dict() for n in sim.npcs],
        "hall_of_fame": [entry_to_dict(e) for e in sim.hall_of_fame],
        "rng_state": sim.rng.bit_generator.state,
    }
    (path / "state.json").write_text(json.dumps(state))
    return path


def _checked(name: str, loaded: np.ndarray, fresh: np.ndarray, cfg: Config) -> np.ndarray:
    """A world array from a (possibly shared, untrusted) snapshot must have the
    shape this config makes, hold real numbers, and (zones) valid patch indices."""
    if loaded.shape != fresh.shape:
        raise ValueError(f"world array {name} has shape {loaded.shape}, expected {fresh.shape}")
    if name == "zones":
        if not np.issubdtype(loaded.dtype, np.integer):
            raise ValueError(f"world array zones must hold integers, not {loaded.dtype}")
        if loaded.min() < -1 or loaded.max() >= cfg.food_patches_per_type:
            raise ValueError("world array zones holds patch indices out of range")
        return loaded.copy()
    if not np.issubdtype(loaded.dtype, np.floating) or not np.isfinite(loaded).all():
        raise ValueError(f"world array {name} must hold finite real numbers")
    return loaded.astype(float)


def load_snapshot(path: str | Path, log_every: int = 100) -> Simulation:
    path = Path(path)
    state = json.loads((path / "state.json").read_text())
    config = {**LEGACY, **state["config"]}   # fields the snapshot predates keep the old behavior
    sim = Simulation(Config.from_dict(config), populate=False, log_every=log_every)
    with np.load(path / "world.npz") as arrays:
        for k in ARRAYS:
            if k in arrays:   # older formats lack scent (stays zeros) or zones (World rebuilt them from the seed)
                setattr(sim.world, k, _checked(k, arrays[k], getattr(sim.world, k), sim.cfg))
    sim.world.shrines = [tuple(s) for s in state["shrines"]]
    sim.tick = state["tick"]
    sim.next_id = state["next_id"]
    sim.clock = SimClock.from_dict(state["clock"])
    sim.deity.load_dict(state["deity"])
    sim.npcs = [NPC.from_dict(n) for n in state["npcs"]]
    sim.hall_of_fame = [hall_of_fame_entry(e) for e in state["hall_of_fame"]]
    sim.rng.bit_generator.state = state["rng_state"]
    for brain in [n.brain for n in sim.npcs] + [e["brain"] for e in sim.hall_of_fame]:
        brain.check(sim.n_inputs, sim.cfg.hidden_units, sim.n_outputs)
    return sim
