"""Tiny neural nets, Creatures-style.

Deliberately plain NumPy arrays with no ML framework, so a brain can be
saved to JSON and loaded by a ~30-line C++ forward pass in the 4D Miner mod.
"""
from __future__ import annotations

import numpy as np


class Brain:
    """inputs -> hidden (tanh) -> outputs. With 0 hidden units the net is linear:
    w1 and b1 are empty and w2 maps the inputs straight to the outputs (a
    baseline for "how much brain does this task need?", research 2026-11-06).

    `memory` is the NPC's memory net when Config.memory_slots is on
    (plan-memory-reaction MR2): a second Brain on the same inputs that manages
    the memory slots. It's part of the genome: mutated, crossed over, saved and
    checked with the forager, so a hall-of-fame entry holds both nets."""

    def __init__(self, w1: np.ndarray, b1: np.ndarray, w2: np.ndarray, b2: np.ndarray,
                 memory: "Brain | None" = None):
        self.w1, self.b1, self.w2, self.b2 = w1, b1, w2, b2
        self.memory = memory

    @property
    def n_in(self) -> int:
        return self.w1.shape[1]

    @property
    def n_hidden(self) -> int:
        return self.w1.shape[0]

    @property
    def n_out(self) -> int:
        return self.w2.shape[0]

    @staticmethod
    def w2_width(n_in: int, n_hidden: int) -> int:
        """Columns of w2: the hidden units, or the inputs when there are none."""
        return n_hidden if n_hidden > 0 else n_in

    @property
    def n_params(self) -> int:
        """Weights in the genome (the memory net's too)."""
        return sum(a.size for a in self._arrays()) + (self.memory.n_params if self.memory else 0)

    def _arrays(self):
        return (self.w1, self.b1, self.w2, self.b2)

    def check(self, n_in: int, n_hidden: int, n_out: int, memory: tuple | None = None) -> None:
        """Raise ValueError unless every array has exactly the expected shape and
        only finite weights. Brains can come from shared files, and JSON happily
        loads NaN and Infinity (docs/SAFETY.md §4). `memory`: the memory net's
        (n_in, n_hidden, n_out), or None when the world has no memory slots."""
        if (memory is None) != (self.memory is None):
            raise ValueError("brain has a memory net but this world has no memory slots" if memory is None
                             else "brain lacks the memory net this world's memory slots need")
        if memory is not None:
            self.memory.check(*memory)
        expected = {"w1": (n_hidden, n_in), "b1": (n_hidden,),
                    "w2": (n_out, self.w2_width(n_in, n_hidden)), "b2": (n_out,)}
        for (name, shape), a in zip(expected.items(), self._arrays()):
            if a.shape != shape:
                raise ValueError(f"brain {name} has shape {a.shape}, expected {shape}")
            if not np.isfinite(a).all():
                raise ValueError(f"brain {name} contains NaN or infinite weights")

    @classmethod
    def random(cls, n_in: int, n_hidden: int, n_out: int, rng: np.random.Generator) -> "Brain":
        width = cls.w2_width(n_in, n_hidden)
        return cls(
            rng.normal(0.0, 1.0 / np.sqrt(n_in), (n_hidden, n_in)),
            np.zeros(n_hidden),
            rng.normal(0.0, 1.0 / np.sqrt(width), (n_out, width)),
            np.zeros(n_out),
        )

    def widen(self, n_in: int) -> "Brain":
        """The same brain with zero-weight inputs appended up to n_in: it behaves
        exactly as before until mutation gives the new inputs weight (a warm start,
        Net2Net-style; plan-memory-reaction MR1). A memory net is widened too."""
        extra = n_in - self.n_in
        if extra < 0:
            raise ValueError(f"can't widen a brain of {self.n_in} inputs to {n_in}")
        if self.n_hidden:
            w1, w2 = np.pad(self.w1, ((0, 0), (0, extra))), self.w2.copy()
        else:                                   # linear: w2 reads the inputs directly
            w1, w2 = self.w1.reshape(0, n_in), np.pad(self.w2, ((0, 0), (0, extra)))
        return Brain(w1, self.b1.copy(), w2, self.b2.copy(),
                     self.memory.widen(n_in) if self.memory else None)

    def with_memory(self, memory: "Brain | None") -> "Brain":
        """This forager with another memory net (or none)."""
        return Brain(self.w1, self.b1, self.w2, self.b2, memory)

    def forward(self, x: np.ndarray) -> np.ndarray:
        hidden = np.tanh(self.w1 @ x + self.b1) if self.w1.shape[0] else x
        return self.w2 @ hidden + self.b2

    def mutation_rate(self, rate: float, per_birth: float) -> float:
        """Chance per weight: `rate`, or `per_birth` / weight count when per_birth > 0
        (the same number of mutated weights per child at any brain size)."""
        if not (np.isfinite(per_birth) and per_birth >= 0):
            raise ValueError(f"mutations_per_birth must be a number >= 0, got {per_birth!r}")
        return min(1.0, per_birth / self.n_params) if per_birth > 0 else rate

    def mutate(self, rate: float, scale: float, rng: np.random.Generator) -> "Brain":
        """The memory net mutates at the same rate, after the forager (its draws
        come last, so a forager's mutations are the same with or without one)."""
        new = []
        for a in self._arrays():
            mask = rng.random(a.shape) < rate
            new.append(a + mask * rng.normal(0.0, scale, a.shape))
        return Brain(*new, self.memory.mutate(rate, scale, rng) if self.memory else None)

    @staticmethod
    def crossover(a: "Brain", b: "Brain", rng: np.random.Generator) -> "Brain":
        if (a.memory is None) != (b.memory is None):
            raise ValueError("can't cross a brain that has a memory net with one that hasn't")
        new = []
        for x, y in zip(a._arrays(), b._arrays()):
            mask = rng.random(x.shape) < 0.5
            new.append(np.where(mask, x, y))
        return Brain(*new, Brain.crossover(a.memory, b.memory, rng) if a.memory else None)

    def to_dict(self) -> dict:
        d = {
            "n_in": self.n_in,
            "n_hidden": self.n_hidden,
            "n_out": self.n_out,
            "w1": self.w1.tolist(),
            "b1": self.b1.tolist(),
            "w2": self.w2.tolist(),
            "b2": self.b2.tolist(),
        }
        if self.memory is not None:
            d["memory"] = self.memory.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict, _depth: int = 0) -> "Brain":
        w1, b1, w2, b2 = (np.asarray(data[k], dtype=float) for k in ("w1", "b1", "w2", "b2"))
        if w1.size == 0:                    # no hidden layer: JSON's [] loses the shape
            w1 = w1.reshape(0, int(data.get("n_in", w2.shape[1] if w2.ndim == 2 else 0)))
        memory = None
        if data.get("memory") is not None:
            if _depth:                      # a memory net has no memory net of its own
                raise ValueError("a memory net can't have its own memory net")
            memory = cls.from_dict(data["memory"], _depth + 1)
        return cls(w1, b1, w2, b2, memory)
