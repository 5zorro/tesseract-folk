"""Tesseract Folk: an N-dimensional artificial-life society prototype.

The simulation core is engine-agnostic on purpose. Nothing in this package
knows about rendering, so the same rules can later be ported to a 4D Miner
C++ mod (or anything else).
"""
from .config import Config
from .simulation import Simulation

__all__ = ["Config", "Simulation"]
