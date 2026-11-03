"""Activity-gated time.

Aging only advances while the player is active, or while the player
deliberately turns the clock (fast-forward). This stops a player from
returning to find everyone they knew has died of old age.
"""
from __future__ import annotations


class SimClock:
    def __init__(self, player_active: bool = True):
        self.player_active = player_active
        self.forced_ticks = 0

    @property
    def aging_active(self) -> bool:
        return self.player_active or self.forced_ticks > 0

    def turn(self, ticks: int) -> None:
        """The player deliberately turns the clock forward."""
        self.forced_ticks += max(0, int(ticks))

    def consume_tick(self) -> None:
        if self.forced_ticks > 0:
            self.forced_ticks -= 1

    def to_dict(self) -> dict:
        return {"player_active": self.player_active, "forced_ticks": self.forced_ticks}

    @classmethod
    def from_dict(cls, data: dict) -> "SimClock":
        clock = cls(data.get("player_active", True))
        clock.forced_ticks = data.get("forced_ticks", 0)
        return clock
