"""Keyed randomness (5zorro's "seed x tick as a time salt", 2026-11-04).

Every random number is a pure function of (seed, tick, entity id, purpose,
draw number), mixed with a 64-bit hash, instead of the next number from one
shared stream. So an NPC's dice don't shift when some other NPC draws, many
NPCs can draw at once (arrays, later GPUs), and replaying a tick needs only
the seed and the tick. The hash is integer-only, so any array backend gives
the same bits.

The mixer is SplitMix64's (Steele, Lea & Flood 2014): each input is folded
in with an xor and a full mix, and draw number i of a key is
mix(key + (i + 1) * golden), which is how SplitMix64 itself makes a stream.

    keys = Keys(seed)
    keys.uniform(tick, ids, ORDER)          # one number per id, all at once
    s = keys.stream(tick, npc_id, MATE)     # Generator-like, for a few draws
    s.integers(len(partners)); s.normal(0.0, 0.3, shape)
"""
from __future__ import annotations

import numpy as np

# Purposes: what a draw is for, so two uses by one NPC in one tick differ.
# Never renumber one (that changes every result); add new ones at the end.
ORDER = 1        # priority within a tick (who resolves first)
ACTION = 2       # sampling the brain's action
GIVE = 3         # which neighbor receives a gift
MATE = 4         # which ready neighbor becomes the partner
CROSSOVER = 5    # a child's mix of its parents' weights (keyed by the child's id)
MUTATE = 6       # which weights mutate, and by how much (keyed by the new brain's NPC)
COLLAPSE = 7     # where a collapsed NPC wakes up
SPAWN = 8        # a top-up: which hall-of-fame entries compete, a random brain, where
SECRET = 9       # where a new secret appears and its food type (keyed by secret id)
INIT = 10        # starting NPCs' brains and cells (tick 0)
SCRIPT = 100     # measurement scripts' own draws (scripts/, never sim/)

_GOLDEN = np.uint64(0x9E3779B97F4A7C15)
_C1 = np.uint64(0xBF58476D1CE4E5B9)
_C2 = np.uint64(0x94D049BB133111EB)
_S30, _S27, _S31, _S11 = np.uint64(30), np.uint64(27), np.uint64(31), np.uint64(11)
_UNIT = 2.0 ** -53


def _u64(values) -> np.ndarray:
    """Integers as a 1-d uint64 array; negative ones (e.g. id -1) wrap, which is fine.
    Always at least 1-d: NumPy wraps uint64 overflow silently on arrays (the hash
    relies on it) but warns on scalars."""
    return np.atleast_1d(np.asarray(values, dtype=np.int64)).astype(np.uint64)


def _mix(z: np.ndarray) -> np.ndarray:
    z = (z ^ (z >> _S30)) * _C1
    z = (z ^ (z >> _S27)) * _C2
    return z ^ (z >> _S31)


def key(seed: int, tick, ids, purpose: int) -> np.ndarray:
    """One 64-bit key per id (tick and ids broadcast against each other)."""
    h = _mix(_u64(seed) + _GOLDEN)
    h = _mix(h ^ _u64(tick))
    h = _mix(h ^ _u64(ids))
    return _mix(h ^ _u64(purpose))


def bits(keys: np.ndarray, first: int, n: int) -> np.ndarray:
    """Draws first .. first + n - 1 of each key: shape keys.shape + (n,)."""
    i = np.arange(first + 1, first + n + 1, dtype=np.uint64)
    return _mix(keys[..., None] + i * _GOLDEN)


def to_unit(b: np.ndarray) -> np.ndarray:
    """Uniform floats in [0, 1): the top 53 bits, like NumPy's own generators."""
    return (b >> _S11).astype(np.float64) * _UNIT


class Keys:
    """Every random number a simulation with this seed uses after building its world."""

    def __init__(self, seed: int):
        self.seed = int(seed)

    def uniform(self, tick: int, ids, purpose: int) -> np.ndarray:
        """Draw 0 of each id's key: one uniform in [0, 1) per id."""
        return to_unit(bits(key(self.seed, tick, ids, purpose), 0, 1))[..., 0]

    def stream(self, tick: int, entity: int, purpose: int) -> "Stream":
        return Stream(key(self.seed, tick, entity, purpose))


class Stream:
    """The draws of one key, in order, with the bits of NumPy's Generator API that
    sim/ uses (random, uniform, normal, integers). Two streams with the same key
    give the same numbers."""

    def __init__(self, k: np.ndarray):
        self._key = k.reshape(1)
        self._next = 0

    def _unit(self, n: int) -> np.ndarray:
        u = to_unit(bits(self._key, self._next, n))[0]
        self._next += n
        return u

    @staticmethod
    def _shape(size) -> tuple:
        if size is None:
            return ()
        return (int(size),) if np.ndim(size) == 0 else tuple(int(s) for s in size)

    def _draw(self, size, transform) -> float | np.ndarray:
        shape = self._shape(size)
        n = int(np.prod(shape)) if shape else 1
        out = transform(n).reshape(shape)
        return float(out) if size is None else out

    def random(self, size=None):
        return self._draw(size, self._unit)

    def uniform(self, low: float = 0.0, high: float = 1.0, size=None):
        return self._draw(size, lambda n: low + (high - low) * self._unit(n))

    def normal(self, loc: float = 0.0, scale: float = 1.0, size=None):
        """Box-Muller: two uniforms per normal (the cosine half only)."""
        def gauss(n: int) -> np.ndarray:
            u = self._unit(2 * n)
            r = np.sqrt(-2.0 * np.log(1.0 - u[0::2]))      # 1 - u is in (0, 1]: no log(0)
            return loc + scale * r * np.cos(2.0 * np.pi * u[1::2])
        return self._draw(size, gauss)

    def integers(self, low: int, high: int | None = None, size=None):
        """Integers in [low, high), or [0, low) with one argument. Scaling a 53-bit
        uniform has a bias below 1e-12 for the small ranges used here."""
        if high is None:
            low, high = 0, low
        if high <= low:
            raise ValueError(f"integers needs high > low, got [{low}, {high})")
        out = self._draw(size, lambda n: low + np.floor(self._unit(n) * (high - low)))
        return int(out) if size is None else out.astype(np.int64)
