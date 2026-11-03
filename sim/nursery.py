"""The nursery: start a fresh world from brains evolved somewhere else.

Selection needs deaths, but in play young NPCs must not die (DESIGN pillar 4).
So brains evolve offline under harsh rules (e.g. a big collapse_age_penalty),
get saved as a snapshot, and new worlds start from that snapshot's best
brains under the gentle play rules. See docs/plan-m1-survival.md, slice 4b.

A brain pool is a list of {"fitness", "generation", "brain"}, best first,
the same shape as Simulation.hall_of_fame.
"""
from __future__ import annotations

import json
from pathlib import Path

from .brain import Brain
from .npc import NPC


def load_brain_pool(path: str | Path) -> list[dict]:
    """Every brain worth keeping from a snapshot folder, best first: the hall
    of fame plus the NPCs alive when it was saved."""
    state = json.loads((Path(path) / "state.json").read_text())
    pool = [{"fitness": e["fitness"], "generation": e["generation"],
             "brain": Brain.from_dict(e["brain"])} for e in state["hall_of_fame"]]
    for data in state["npcs"]:
        npc = NPC.from_dict(data)
        pool.append({"fitness": npc.fitness(), "generation": npc.generation, "brain": npc.brain})
    pool.sort(key=lambda e: e["fitness"], reverse=True)   # stable, so ties keep file order
    return pool


def seed_brains(sim, pool: list[dict]) -> None:
    """Give a fresh world's NPCs the pool's brains, best first, and start its
    hall of fame from the pool's best.

    NPCs beyond the pool's size get mutated copies (through sim.rng, so runs
    stay deterministic). Only brains and generations change, never mass.
    """
    if not pool:
        raise ValueError("the brain pool is empty")
    want = (sim.n_inputs, sim.cfg.hidden_units, sim.n_outputs)
    for entry in pool:
        b = entry["brain"]
        if (b.n_in, b.n_hidden, b.n_out) != want:
            raise ValueError(
                f"brain shape {(b.n_in, b.n_hidden, b.n_out)} doesn't fit this world's "
                f"{want} (inputs, hidden, outputs). dims, n_food_types, n_nutrients, "
                f"hidden_units and memory_units must match the snapshot's.")
    cfg = sim.cfg
    for i, npc in enumerate(sim.npcs):
        entry = pool[i % len(pool)]
        brain = entry["brain"]
        if i >= len(pool):
            brain = brain.mutate(cfg.mutation_rate, cfg.mutation_scale, sim.rng)
        npc.brain = brain
        npc.generation = entry["generation"]
    sim.hall_of_fame = [dict(e) for e in pool[:cfg.hall_of_fame_size]]
