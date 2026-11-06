"""The all-knowing deity: prayer, piety, smiting, and stale secrets.

A secret is a hidden cache of food. Its mass is pulled out of the soil when
it appears and returns to the soil if nobody claims it before it goes stale,
so secrets never create or destroy mass.

Later, this is the natural place for the player (or a Claude-powered god)
to sit. See controllers.py.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from . import keyed
from .config import Config
from .world import Pos, World, wrapped_delta


@dataclass
class Secret:
    id: int
    pos: Pos
    food_type: int
    amount: float
    created: int
    expires: int


class Deity:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.secrets: dict[int, Secret] = {}
        self.next_id = 0

    def step(self, tick: int, world: World, keys, stats) -> None:
        """`keys`: the simulation's keyed.Keys; a new secret's draws are keyed by its id."""
        for s in list(self.secrets.values()):
            if tick >= s.expires:
                world.soil[s.pos] += s.amount
                del self.secrets[s.id]
                stats.count("secrets_stale")

        cfg = self.cfg
        if tick % cfg.secret_interval == 0 and len(self.secrets) < cfg.max_secrets:
            rng = keys.stream(tick, self.next_id, keyed.SECRET)
            pos = world.random_cell(rng)
            amount = min(cfg.secret_amount, float(world.soil[pos]))
            if amount > 0:
                before = float(world.soil[pos])
                world.soil[pos] -= amount
                amount = before - float(world.soil[pos])     # exactly what left the soil
                food_type = int(rng.integers(0, cfg.n_food_types))
                self.secrets[self.next_id] = Secret(
                    self.next_id, pos, food_type, amount, tick, tick + cfg.secret_lifetime
                )
                self.next_id += 1

    def claim_at(self, pos: Pos, world: World) -> int:
        """Stepping onto a secret reveals its cache as ordinary food."""
        claimed = 0
        for s in list(self.secrets.values()):
            if s.pos == pos:
                world.food[(s.food_type,) + pos] += s.amount
                del self.secrets[s.id]
                claimed += 1
        return claimed

    def claim_cells(self, cells: set, world: World) -> int:
        """claim_at for every cell in `cells` at once (the array engine's moves).
        Same additions in the same order per cell: secrets in creation order."""
        claimed = 0
        for s in list(self.secrets.values()):
            if s.pos in cells:
                world.food[(s.food_type,) + s.pos] += s.amount
                del self.secrets[s.id]
                claimed += 1
        return claimed

    def nearest(self, pos: Pos) -> Secret | None:
        best, best_d = None, None
        for s in self.secrets.values():
            d = float(np.abs(wrapped_delta(pos, s.pos, self.cfg.size)).sum())
            if best_d is None or d < best_d:
                best, best_d = s, d
        return best

    def pray(self, npc, tick: int) -> str:
        """Returns 'answered', 'silent' (nothing to reveal), 'smitten' or 'ignored'.

        Praying needs enough piety, a low smite score, and patience. Praying
        when unqualified (including spamming during the cooldown) builds the
        smite score, and crossing the smite threshold hurts. With
        `cfg.smiting` off (the default for now), unqualified prayers are just
        ignored.
        """
        cfg = self.cfg
        eligible = (
            npc.piety >= cfg.piety_threshold
            and npc.smite < cfg.smite_threshold
            and tick - npc.last_prayer >= cfg.prayer_cooldown
        )
        npc.last_prayer = tick
        if eligible:
            secret = self.nearest(npc.pos)
            if secret is None:
                return "silent"
            npc.piety -= cfg.prayer_piety_cost
            npc.known_secret = secret.id
            return "answered"
        if not cfg.smiting:
            return "ignored"
        npc.smite += cfg.smite_gain
        if npc.smite >= cfg.smite_threshold:
            npc.take_damage("smite", cfg.smite_damage)
            return "smitten"
        return "ignored"

    def mass(self) -> float:
        return float(sum(s.amount for s in self.secrets.values()))

    def to_dict(self) -> dict:
        return {
            "next_id": self.next_id,
            "secrets": [{**asdict(s), "pos": list(s.pos)} for s in self.secrets.values()],
        }

    def load_dict(self, data: dict) -> None:
        self.next_id = data["next_id"]
        self.secrets = {}
        for s in data["secrets"]:
            s = dict(s, pos=tuple(s["pos"]))
            self.secrets[s["id"]] = Secret(**s)
