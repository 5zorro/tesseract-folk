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

from .brain import Brain
from .clock import SimClock
from .config import Config
from .npc import NPC
from .simulation import Simulation

ARRAYS = ("soil", "food", "poop", "stink", "scent", "capacity", "profiles")
FORMAT = 2   # 2 added food scent (M1 slice 6)

# Config fields added after snapshots existed, with the value that reproduces
# the behavior from before them. A snapshot saved without a field gets this
# value instead of today's default, so it resumes the way it was saved.
LEGACY = {
    "food_scent": False,           # M1 slice 6; without it, old brains wouldn't fit
    "busy_resets_idle": False,     # 2026-11-02
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
        "hall_of_fame": [{"fitness": e["fitness"], "generation": e["generation"],
                          "brain": e["brain"].to_dict()} for e in sim.hall_of_fame],
        "rng_state": sim.rng.bit_generator.state,
    }
    (path / "state.json").write_text(json.dumps(state))
    return path


def load_snapshot(path: str | Path, log_every: int = 100) -> Simulation:
    path = Path(path)
    state = json.loads((path / "state.json").read_text())
    config = {**LEGACY, **state["config"]}   # fields the snapshot predates keep the old behavior
    sim = Simulation(Config.from_dict(config), populate=False, log_every=log_every)
    arrays = np.load(path / "world.npz")
    for k in ARRAYS:
        if k in arrays:                    # format 1 has no scent; it stays zeros
            setattr(sim.world, k, arrays[k].copy())
    sim.world.shrines = [tuple(s) for s in state["shrines"]]
    sim.tick = state["tick"]
    sim.next_id = state["next_id"]
    sim.clock = SimClock.from_dict(state["clock"])
    sim.deity.load_dict(state["deity"])
    sim.npcs = [NPC.from_dict(n) for n in state["npcs"]]
    sim.hall_of_fame = [{"fitness": e["fitness"], "generation": e["generation"],
                         "brain": Brain.from_dict(e["brain"])} for e in state["hall_of_fame"]]
    sim.rng.bit_generator.state = state["rng_state"]
    for brain in [n.brain for n in sim.npcs] + [e["brain"] for e in sim.hall_of_fame]:
        brain.check(sim.n_inputs, sim.cfg.hidden_units, sim.n_outputs)
    return sim
