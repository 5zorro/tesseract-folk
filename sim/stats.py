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
    "secrets_claimed", "secrets_shared", "secrets_stale", "zone_switches",
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
        # One entry per completed life (death), for M2's travel metrics.
        # Cumulative, not saved in snapshots.
        self.lives: list[dict] = []

    def count(self, name: str, n: int = 1) -> None:
        self.window[name] += n

    def record_life(self, npc, tick: int) -> None:
        self.lives.append({
            "tick": tick, "lifetime": npc.lifetime, "zones": len(npc.zones_eaten),
            "zone_types": len({t for t, _ in npc.zones_eaten}), "switches": npc.zone_switches,
            "directed_hits": npc.directed_hits, "directed_chance": npc.directed_chance,
        })

    def travel_summary(self, since_tick: int = 0, min_lifetime: int = 500) -> dict:
        """M2 metrics over lives that ended at or after `since_tick` and lasted
        at least `min_lifetime` ticks (short lives can't have travelled much).

        `directed` is the share of zone switches that arrived where the NPC's
        lowest nutrient grows; `chance` is the same for a random nutrient at
        those cells. Diet drives travel when directed beats chance (and beats
        scratch brains: geometry alone can lift it, gotchas.md)."""
        nan = float("nan")
        lives = [l for l in self.lives if l["tick"] >= since_tick and l["lifetime"] >= min_lifetime]
        if not lives:
            return {"lives": 0, "zones": nan, "zone_types": nan, "switch_rate": nan,
                    "directed": nan, "chance": nan}
        switches = sum(l["switches"] for l in lives)
        return {
            "lives": len(lives),
            "zones": float(np.mean([l["zones"] for l in lives])),
            "zone_types": float(np.mean([l["zone_types"] for l in lives])),
            "switch_rate": 1000 * switches / sum(l["lifetime"] for l in lives),
            "directed": sum(l.get("directed_hits", 0.0) for l in lives) / switches if switches else nan,
            "chance": sum(l.get("directed_chance", 0.0) for l in lives) / switches if switches else nan,
        }

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
