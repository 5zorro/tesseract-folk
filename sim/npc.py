"""NPC state. Behavior lives in Simulation; this is just the data."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .brain import Brain

BASE_ACTIONS = ["stay", "eat", "pick_up", "give", "poop", "mate", "pray", "worship", "share"]


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

    def __post_init__(self):
        if self.eaten is None:
            self.eaten = np.zeros_like(self.inventory)

    def fitness(self) -> float:
        """Used only to pick parents when topping up the population.

        Keep this simple and avoid rewarding specific behaviors (like trading)
        directly; the point is to see whether those emerge on their own.
        """
        return self.offspring * 500.0 + self.lifetime - self.collapses * 100.0

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "brain"}
        for k, v in d.items():
            if isinstance(v, np.ndarray):
                d[k] = v.tolist()
        d["pos"] = list(self.pos)
        d["brain"] = self.brain.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "NPC":
        d = dict(data)
        d["brain"] = Brain.from_dict(d["brain"])
        d["pos"] = tuple(d["pos"])
        for k in ("nutrients", "satiation", "inventory", "memory", "eaten"):
            d[k] = np.asarray(d[k], dtype=float)
        return cls(**d)
