"""Tiny neural nets, Creatures-style.

Deliberately plain NumPy arrays with no ML framework, so a brain can be
saved to JSON and loaded by a ~30-line C++ forward pass in the 4D Miner mod.
"""
from __future__ import annotations

import numpy as np


class Brain:
    def __init__(self, w1: np.ndarray, b1: np.ndarray, w2: np.ndarray, b2: np.ndarray):
        self.w1, self.b1, self.w2, self.b2 = w1, b1, w2, b2

    @property
    def n_in(self) -> int:
        return self.w1.shape[1]

    @property
    def n_hidden(self) -> int:
        return self.w1.shape[0]

    @property
    def n_out(self) -> int:
        return self.w2.shape[0]

    @property
    def n_params(self) -> int:
        return sum(a.size for a in self._arrays())

    def _arrays(self):
        return (self.w1, self.b1, self.w2, self.b2)

    @classmethod
    def random(cls, n_in: int, n_hidden: int, n_out: int, rng: np.random.Generator) -> "Brain":
        return cls(
            rng.normal(0.0, 1.0 / np.sqrt(n_in), (n_hidden, n_in)),
            np.zeros(n_hidden),
            rng.normal(0.0, 1.0 / np.sqrt(n_hidden), (n_out, n_hidden)),
            np.zeros(n_out),
        )

    def forward(self, x: np.ndarray) -> np.ndarray:
        hidden = np.tanh(self.w1 @ x + self.b1)
        return self.w2 @ hidden + self.b2

    def mutate(self, rate: float, scale: float, rng: np.random.Generator) -> "Brain":
        new = []
        for a in self._arrays():
            mask = rng.random(a.shape) < rate
            new.append(a + mask * rng.normal(0.0, scale, a.shape))
        return Brain(*new)

    @staticmethod
    def crossover(a: "Brain", b: "Brain", rng: np.random.Generator) -> "Brain":
        new = []
        for x, y in zip(a._arrays(), b._arrays()):
            mask = rng.random(x.shape) < 0.5
            new.append(np.where(mask, x, y))
        return Brain(*new)

    def to_dict(self) -> dict:
        return {
            "n_in": self.n_in,
            "n_hidden": self.n_hidden,
            "n_out": self.n_out,
            "w1": self.w1.tolist(),
            "b1": self.b1.tolist(),
            "w2": self.w2.tolist(),
            "b2": self.b2.tolist(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Brain":
        return cls(*(np.asarray(data[k], dtype=float) for k in ("w1", "b1", "w2", "b2")))
