"""Metrics for the proof-of-concept pass criteria (see docs/ROADMAP.md)."""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from .npc import DAMAGE_CAUSES

# "unknown" covers health set to zero directly (tests, future mechanics).
CAUSES = DAMAGE_CAUSES + ["unknown"]

COUNTERS = [
    "births", "deaths", "collapses", "spawns", "eats", "gives", "poops", "accidents",
    "prayers_answered", "prayers_silent", "prayers_ignored", "smitings", "worships",
    "secrets_claimed", "secrets_shared", "secrets_stale",
] + [f"collapse_{c}" for c in CAUSES] + [f"death_{c}" for c in CAUSES]


class Stats:
    def __init__(self, log_every: int = 100):
        self.log_every = log_every
        self.window: dict[str, int] = defaultdict(int)
        self.history: list[dict] = []
        # Cumulative over the whole run (not per window), for M1's
        # "collapses per NPC fall over generations". Not saved in snapshots.
        self.generation_lifetime: dict[int, int] = defaultdict(int)
        self.generation_collapses: dict[int, int] = defaultdict(int)

    def count(self, name: str, n: int = 1) -> None:
        self.window[name] += n

    def collapse_rate_by_generation(self, per: int = 1000) -> dict[int, float]:
        """Collapses per `per` ticks of NPC lifetime, for each generation."""
        return {g: self.generation_collapses[g] * per / t
                for g, t in sorted(self.generation_lifetime.items()) if t > 0}

    def maybe_sample(self, sim) -> dict | None:
        if sim.tick % self.log_every != 0:
            return None
        return self.sample(sim)

    def sample(self, sim) -> dict:
        npcs = sim.npcs
        row = {"tick": sim.tick, "population": len(npcs)}
        if npcs:
            row["mean_generation"] = float(np.mean([n.generation for n in npcs]))
            row["max_generation"] = int(max(n.generation for n in npcs))
            row["mean_age"] = float(np.mean([n.age for n in npcs]))
            row["diet_diversity"] = float(np.mean([_diet_entropy(n.eaten) for n in npcs]))
        else:
            row.update(mean_generation=0.0, max_generation=0, mean_age=0.0, diet_diversity=0.0)
        for name in COUNTERS:
            row[name] = self.window.get(name, 0)
        row["secrets_active"] = len(sim.deity.secrets)
        row["total_mass"] = sim.total_mass()
        self.history.append(row)
        self.window.clear()
        for n in npcs:
            n.eaten[:] = 0.0
        return row


def _diet_entropy(eaten: np.ndarray) -> float:
    """0 = ate one food type only, 1 = perfectly even diet across all types."""
    total = eaten.sum()
    if total <= 0 or len(eaten) < 2:
        return 0.0
    p = eaten[eaten > 0] / total
    return float(-(p * np.log(p)).sum() / np.log(len(eaten)))
