"""Metrics for the proof-of-concept pass criteria (see docs/ROADMAP.md)."""
from __future__ import annotations

from collections import defaultdict

import numpy as np

COUNTERS = [
    "births", "deaths", "collapses", "spawns", "eats", "gives", "poops", "accidents",
    "prayers_answered", "prayers_silent", "prayers_ignored", "smitings", "worships",
    "secrets_claimed", "secrets_shared", "secrets_stale",
]


class Stats:
    def __init__(self, log_every: int = 100):
        self.log_every = log_every
        self.window: dict[str, int] = defaultdict(int)
        self.history: list[dict] = []

    def count(self, name: str, n: int = 1) -> None:
        self.window[name] += n

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
