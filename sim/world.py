"""The N-dimensional world.

Every field is a NumPy array of shape (size,) * dims, so the same code runs
in 2D for the prototype and 4D for 4D Miner. The world wraps around on every
axis (a torus), which avoids edge cases at the borders.

Mass is conserved across soil, food, and poop (plus whatever NPCs and the
deity are holding; see Simulation.total_mass). Stink and food scent are
signals, not mass.
"""
from __future__ import annotations

import numpy as np

from .config import Config

Pos = tuple[int, ...]


def wrapped_delta(a: Pos, b: Pos, size: int) -> np.ndarray:
    """Shortest vector from a to b on a wrapping world."""
    d = np.asarray(b) - np.asarray(a)
    return (d + size // 2) % size - size // 2


class World:
    def __init__(self, cfg: Config, rng: np.random.Generator):
        self.cfg = cfg
        self.shape = (cfg.size,) * cfg.dims
        self.soil = np.full(self.shape, cfg.initial_soil_per_cell, dtype=float)
        self.capacity = self._make_capacity(rng)          # (types, *shape)
        self.food = self.capacity * cfg.initial_food_fraction
        self.poop = np.zeros(self.shape)
        self.stink = np.zeros(self.shape)
        self.scent = np.zeros_like(self.food)              # (types, *shape)
        self.profiles = self._make_profiles()              # (types, nutrients)
        self.shrines: list[Pos] = [self.random_cell(rng) for _ in range(cfg.n_shrines)]

    # ----------------------------------------------------------------- setup
    def _make_capacity(self, rng: np.random.Generator) -> np.ndarray:
        """Each food type grows best in its own patches, so NPCs must travel."""
        cfg = self.cfg
        idx = np.indices(self.shape)
        caps = []
        for _ in range(cfg.n_food_types):
            field = np.zeros(self.shape)
            for _ in range(cfg.food_patches_per_type):
                center = rng.integers(0, cfg.size, cfg.dims)
                dist2 = np.zeros(self.shape)
                for axis in range(cfg.dims):
                    d = (idx[axis] - center[axis] + cfg.size // 2) % cfg.size - cfg.size // 2
                    dist2 += d.astype(float) ** 2
                field += np.exp(-dist2 / (2 * cfg.food_patch_radius ** 2))
            field /= field.max()
            base = cfg.food_baseline_fraction
            caps.append((base + (1 - base) * field) * cfg.food_capacity)
        return np.stack(caps)

    def _make_profiles(self) -> np.ndarray:
        """Food type t is rich in nutrient t (mod n_nutrients), poor in the rest."""
        t, n = self.cfg.n_food_types, self.cfg.n_nutrients
        prof = np.full((t, n), 0.1)
        for i in range(t):
            prof[i, i % n] = 0.9
        return prof

    # ------------------------------------------------------------- per tick
    def step(self) -> None:
        cfg = self.cfg

        # Food grows toward its capacity, pulling mass out of the soil.
        room = np.clip(self.capacity - self.food, 0.0, None)
        soil_factor = self.soil / (self.soil + cfg.soil_half_saturation)
        growth = cfg.food_growth_rate * room * soil_factor[None]
        total = growth.sum(axis=0)
        scale = np.minimum(1.0, self.soil / np.maximum(total, 1e-12))
        growth *= scale[None]
        self.food += growth
        self.soil -= growth.sum(axis=0)

        # Poop slowly becomes soil again (fertilizer) and emits stink.
        decomposed = self.poop * cfg.poop_decompose_rate
        self.poop -= decomposed
        self.soil += decomposed
        self.stink += self.poop * cfg.stink_emission

        # Stink spreads to neighbors and fades.
        self.stink += cfg.stink_diffusion * (self._neighbor_mean(self.stink) - self.stink)
        self.stink *= 1.0 - cfg.stink_decay

        # Food smells, in proportion to how much is there; the smell spreads the
        # same way but fades slower, so it reaches farther.
        if cfg.food_scent:
            self.scent += self.food * cfg.scent_emission
            self.scent += cfg.scent_diffusion * (self._neighbor_mean(self.scent, first_axis=1)
                                                 - self.scent)
            self.scent *= 1.0 - cfg.scent_decay

    def _neighbor_mean(self, field: np.ndarray, first_axis: int = 0) -> np.ndarray:
        """Mean of each cell's 2 * dims neighbors (fields may have leading non-space axes)."""
        dims = self.cfg.dims
        return sum(
            np.roll(field, shift, axis=first_axis + axis)
            for axis in range(dims)
            for shift in (1, -1)
        ) / (2 * dims)

    # -------------------------------------------------------------- helpers
    def random_cell(self, rng: np.random.Generator) -> Pos:
        return tuple(int(v) for v in rng.integers(0, self.cfg.size, self.cfg.dims))

    def neighbor(self, pos: Pos, axis: int, sign: int) -> Pos:
        p = list(pos)
        p[axis] = (p[axis] + sign) % self.cfg.size
        return tuple(p)

    def adjacent(self, pos: Pos) -> list[Pos]:
        return [self.neighbor(pos, a, s) for a in range(self.cfg.dims) for s in (1, -1)]

    def food_at(self, pos: Pos) -> np.ndarray:
        """A view of every food type at one cell (writes go through)."""
        return self.food[(slice(None),) + pos]

    def scent_at(self, pos: Pos) -> np.ndarray:
        """The scent of every food type at one cell."""
        return self.scent[(slice(None),) + pos]

    def mass(self) -> float:
        return float(self.soil.sum() + self.food.sum() + self.poop.sum())

    def take_from_soil(self, amount: float) -> bool:
        """Pull mass evenly out of the soil (used to spawn new NPCs)."""
        total = self.soil.sum()
        if total < amount:
            return False
        self.soil -= amount * self.soil / total
        return True
