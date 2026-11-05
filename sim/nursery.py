"""The nursery: start a fresh world from brains evolved somewhere else.

Selection needs deaths, but in play young NPCs must not die (DESIGN pillar 4).
So brains evolve offline under harsh rules (e.g. a big collapse_age_penalty),
get saved as a snapshot, and new worlds start from that snapshot's best
brains under the gentle play rules. See docs/plan-m1-survival.md, slice 4b.

A brain pool is a list of hall-of-fame entries ({"fitness", "generation", "rate",
"lineage", the track-record fields, "brain"}), best first by fitness.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .brain import Brain
from .npc import NPC


# Track-record fields of a hall-of-fame entry (plan-m2 slice R5) and their values
# for entries saved before they existed: one life of unknown merit, no copies.
TRACK_FIELDS = {"id": -1, "lives": 1.0, "excess_sum": 0.0, "copies": 0.0, "copy_excess_sum": 0.0}


def hall_of_fame_entry(data: dict) -> dict:
    """A hall-of-fame entry from saved JSON (snapshots may be shared, so
    untrusted): known fields only, numbers checked finite."""
    entry = {"fitness": float(data["fitness"]), "generation": int(data["generation"]),
             "rate": float(data.get("rate", -1.0)), "lineage": float(data.get("lineage", -1.0)),
             **{k: float(data.get(k, v)) for k, v in TRACK_FIELDS.items()},
             "brain": Brain.from_dict(data["brain"])}
    entry["id"] = int(entry["id"])
    numbers = [v for k, v in entry.items() if k != "brain"]
    if not all(math.isfinite(v) for v in numbers) or entry["lives"] < 0 or entry["copies"] < 0:
        raise ValueError("a hall-of-fame entry holds a non-finite or negative number")
    return entry


def entry_to_dict(entry: dict) -> dict:
    return {**{k: v for k, v in entry.items() if k != "brain"}, "brain": entry["brain"].to_dict()}


def load_brain_pool(path: str | Path) -> list[dict]:
    """Every brain worth keeping from a snapshot folder, best first: the hall
    of fame plus the NPCs alive when it was saved."""
    state = json.loads((Path(path) / "state.json").read_text())
    pool = [hall_of_fame_entry(e) for e in state["hall_of_fame"]]
    for data in state["npcs"]:
        npc = NPC.from_dict(data)
        pool.append({"fitness": npc.fitness(), "generation": npc.generation,
                     "rate": npc.collapse_rate(), "lineage": npc.lineage, **TRACK_FIELDS,
                     "id": npc.id, "brain": npc.brain})
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
    for entry in pool:
        try:
            entry["brain"].check(sim.n_inputs, sim.cfg.hidden_units, sim.n_outputs)
        except ValueError as e:
            raise ValueError(
                f"a pool brain doesn't fit this world: {e}. dims, n_food_types, "
                f"n_nutrients, hidden_units, memory_units and food_scent must match the "
                f"snapshot's (pools saved before food scent need food_scent=false).") from e
    cfg = sim.cfg
    pool = [dict(e) for e in pool]
    if cfg.hall_of_fame_track_record:
        # Pool ids come from another world and could clash with this one's NPC
        # ids, so entries get fresh ones (only needed to credit the track record).
        for entry in pool:
            entry["id"], sim.next_id = sim.next_id, sim.next_id + 1
    for i, npc in enumerate(sim.npcs):
        entry = pool[i % len(pool)]
        brain = entry["brain"]
        if i >= len(pool):
            parent_rate = entry.get("rate", -1.0)
            brain, mutations, npc.lineage = sim.mutate_child(brain, parent_rate,
                                                             entry.get("lineage", -1.0))
            npc.origin, npc.mutations, npc.parent_rate = "copy", mutations, parent_rate
        npc.source = int(entry.get("id", -1))     # an exact brain is a re-test of its entry
        npc.brain = brain
        npc.generation = entry["generation"]
    sim.hall_of_fame = pool[:cfg.hall_of_fame_size]
