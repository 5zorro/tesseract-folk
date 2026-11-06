"""Pluggable controllers: who decides what an NPC does.

By default every NPC uses its own tiny brain. A controller registered in
`sim.overrides[npc_id]` takes over that one NPC instead. This is the hook
for the "bring your own API key" Claude pawn and, later, a Claude-powered
deity or a player-possessed NPC.

Design notes for the Claude pawn (not implemented yet, see docs/DESIGN.md):
  * Same senses and actions as everyone else, for a fair comparison.
    Use describe_observation() to turn the sensor vector into text and ask
    for exactly one action name back, as JSON.
  * Call the API at decision points, not every tick. Calls are slow and cost
    money, so cache a plan ("walk east to the berry patch, then trade") and
    replay it over many ticks.
  * Read the key from an environment variable or a local config file.
    Never store it in snapshots or anything that gets shared.
  * In the 4D Miner C++ port, make the HTTP call on a background thread so
    the game never freezes waiting for a reply.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np


class Controller(Protocol):
    def decide(self, sim, npc, obs: np.ndarray) -> int:
        """Return an index into sim.actions."""


class ScriptedController:
    """A hard-coded decision tree. Useful as a baseline to compare evolved
    brains against, and the seed of the "instinct vs. learning" mechanic
    (instincts cost less hunger but never discover secrets)."""

    def decide(self, sim, npc, obs: np.ndarray) -> int:
        cfg = sim.cfg
        A = {name: i for i, name in enumerate(sim.actions)}
        if npc.bowel > 0.8 * cfg.bowel_capacity:
            return A["poop"]
        if npc.nutrients.min() < 0.6 and sim.world.food_at(npc.pos).sum() > 0.05:
            return A["eat"] if "eat" in A else A["eat_need"]
        # Walk toward more food, away from stink.
        best, best_score = None, -np.inf
        for axis in range(cfg.dims):
            for sign in (1, -1):
                cell = sim.world.neighbor(npc.pos, axis, sign)
                score = sim.world.food_at(cell).sum() - sim.world.stink[cell]
                if score > best_score:
                    best, best_score = f"move{'+' if sign > 0 else '-'}{axis}", score
        return A[best]


class SenseController:
    """A hand-written forager that sees only the sense vector, like a brain
    (plus which nutrient each food type is rich in, as an instinct would). A
    probe: if it meets the goals in a dimension, the senses carry enough
    information there and the limit is learning; if not, it's the senses or the
    world (2026-11-06, 5zorro: "are the 4D senses giving bad results?").
    Counts how often the needed food's scent gives no direction (`blind`)."""

    def __init__(self):
        self.decisions = self.blind = self.scent_zero = 0

    def decide(self, sim, npc, obs: np.ndarray) -> int:
        cfg = sim.cfg
        A = {name: i for i, name in enumerate(sim.actions)}
        L = sim.sense_layout()
        self.decisions += 1
        if obs[L["bowel"]][0] > 0.8:
            return A["poop"]
        nutrients = obs[L["nutrients"]]
        need = int(np.argmin(nutrients))
        needed = sim.world.rich == need                      # food types rich in it
        here = obs[L["food_here"]] * cfg.food_capacity
        bite = 0.5 * cfg.bite_size
        eat_need = A["eat"] if "eat" in A else A["eat_need"]
        if nutrients.min() < 0.7 and here[needed].max() > bite:
            return eat_need
        if obs[L["body"]][0] < 0.9 and here.sum() > bite:
            return A.get("eat_most", eat_need)
        t, d = cfg.n_food_types, cfg.dims
        if "scent_grad" in L:
            if not (obs[L["scent_here"]][needed] > 0).any():
                self.scent_zero += 1
            grad = obs[L["scent_grad"]].reshape(d, t)[:, needed].sum(axis=1)
        else:
            grad = obs[L["food_grad"]].reshape(d, t)[:, needed].sum(axis=1)
        if not np.any(np.abs(grad) > 1e-9):
            self.blind += 1
            axis, sign = (npc.id + sim.tick) % d, 1             # no direction: wander
        else:
            axis = int(np.argmax(np.abs(grad)))
            sign = 1 if grad[axis] > 0 else -1
        return A[f"move{'+' if sign > 0 else '-'}{axis}"]


class ClaudeController:
    """Placeholder for an NPC driven by Claude through the player's own API key."""

    def __init__(self, decide_every: int = 50):
        self.decide_every = decide_every
        self.plan: list[str] = []

    def decide(self, sim, npc, obs: np.ndarray) -> int:
        raise NotImplementedError(
            "TODO: build a prompt from describe_observation(), call the API on "
            "a schedule, parse one action name from JSON, and replay the plan."
        )


def describe_observation(sim, npc) -> str:
    """Plain-English summary of what an NPC can sense. Starting point for an
    LLM prompt, and handy for debugging brains too."""
    w = sim.world
    lines = [
        f"Health {npc.health:.2f}, age {npc.age}, body mass {npc.body:.2f}, bowel {npc.bowel:.2f}.",
        "Nutrients: " + ", ".join(f"{v:.2f}" for v in npc.nutrients) + ".",
        "Food here: " + ", ".join(f"type{i}={v:.2f}" for i, v in enumerate(w.food_at(npc.pos))) + ".",
        f"Stink here {w.stink[npc.pos]:.2f}. Piety {npc.piety:.2f}, smite {npc.smite:.2f}.",
        "Carrying: " + ", ".join(f"type{i}={v:.2f}" for i, v in enumerate(npc.inventory)) + ".",
        "Knows a secret." if npc.known_secret is not None else "Knows no secrets.",
        "Possible actions: " + ", ".join(sim.actions) + ".",
    ]
    return "\n".join(lines)
