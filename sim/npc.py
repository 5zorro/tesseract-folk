"""NPC state. Behavior lives in Simulation; this is just the data."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .brain import Brain

BASE_ACTIONS = ["stay", "eat", "pick_up", "give", "poop", "mate", "pray", "worship", "share"]

# Everything that can lower health. A collapse or death is blamed on whichever
# cause did the most damage since the NPC was last at full health.
DAMAGE_CAUSES = ["nutrient_starve", "body_starve", "stink", "smite", "elder"]


def build_actions(dims: int) -> list[str]:
    """Two moves per axis (so 4 in 2D, 8 in 4D), then everything else."""
    moves = [f"move{sign}{axis}" for axis in range(dims) for sign in ("+", "-")]
    return moves + BASE_ACTIONS


@dataclass
class NPC:
    id: int
    pos: tuple[int, ...]
    brain: Brain
    body: float
    nutrients: np.ndarray
    satiation: np.ndarray
    inventory: np.ndarray
    memory: np.ndarray
    generation: int = 0
    bowel: float = 0.0
    health: float = 1.0
    age: int = 0
    lifetime: int = 0
    piety: float = 0.0
    smite: float = 0.0
    idle_streak: int = 0
    moved_last: bool = False
    mate_ready_until: int = -1
    mate_cooldown_until: int = 0
    last_prayer: int = -10**9
    known_secret: int | None = None
    offspring: int = 0
    collapses: int = 0
    gifts_given: int = 0
    gifts_received: int = 0
    alive: bool = True
    eaten: np.ndarray = field(default=None)  # per food type, reset each stats window
    damage: dict = field(default_factory=dict)  # cause -> damage since last at full health
    # M2 travel: zones (food type, patch index) it has eaten in this lifetime,
    # the zone of its last in-zone bite, and how often that zone changed.
    zones_eaten: set = field(default_factory=set)
    last_zone: tuple | None = None
    zone_switches: int = 0

    def __post_init__(self):
        if self.eaten is None:
            self.eaten = np.zeros_like(self.inventory)

    def take_damage(self, cause: str, amount: float) -> None:
        self.health -= amount
        self.damage[cause] = self.damage.get(cause, 0.0) + amount

    def main_damage_cause(self) -> str:
        return max(self.damage, key=self.damage.get) if self.damage else "unknown"

    def fitness(self) -> float:
        """Used only to pick parents when topping up the population.

        Keep this simple and avoid rewarding specific behaviors (like trading)
        directly; the point is to see whether those emerge on their own.
        """
        return self.offspring * 500.0 + self.lifetime - self.collapses * 100.0

    def record_zone(self, zone: tuple) -> bool:
        """A bite eaten inside `zone` (food type, patch index). True if it's a
        different zone from the last in-zone bite (a switch)."""
        self.zones_eaten.add(zone)
        switched = self.last_zone is not None and zone != self.last_zone
        self.zone_switches += switched
        self.last_zone = zone
        return switched

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "brain"}
        for k, v in d.items():
            if isinstance(v, np.ndarray):
                d[k] = v.tolist()
        d["pos"] = list(self.pos)
        d["zones_eaten"] = sorted(list(z) for z in self.zones_eaten)
        d["last_zone"] = list(self.last_zone) if self.last_zone is not None else None
        d["brain"] = self.brain.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "NPC":
        d = dict(data)
        d["brain"] = Brain.from_dict(d["brain"])
        d["pos"] = tuple(d["pos"])
        for k in ("nutrients", "satiation", "inventory", "memory", "eaten"):
            d[k] = np.asarray(d[k], dtype=float)
        d["zones_eaten"] = {tuple(z) for z in d.get("zones_eaten", [])}   # absent before M2
        if d.get("last_zone") is not None:
            d["last_zone"] = tuple(d["last_zone"])
        return cls(**d)
