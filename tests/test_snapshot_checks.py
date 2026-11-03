"""Snapshots are untrusted input: crafted world arrays fail clearly (docs/SAFETY.md §4)."""
import numpy as np
import pytest

from sim import Config, Simulation
from sim.snapshot import load_snapshot, save_snapshot

SMALL = dict(size=16, initial_npcs=20, min_population=10)


@pytest.fixture
def snap(tmp_path):
    sim = Simulation(Config(**SMALL), log_every=1000)
    sim.run(20)
    return save_snapshot(sim, tmp_path / "s")


def tamper(path, name, value):
    with np.load(path / "world.npz") as arrays:
        data = {k: arrays[k] for k in arrays.files}
    data[name] = value
    np.savez_compressed(path / "world.npz", **data)


def test_untampered_snapshot_loads(snap):
    load_snapshot(snap)


@pytest.mark.parametrize("name,make,message", [
    ("soil", lambda a: a[:-1], "shape"),
    ("food", lambda a: np.where(a > 0, np.nan, a), "finite"),
    ("scent", lambda a: np.full_like(a, np.inf), "finite"),
    ("stink", lambda a: a.astype(str), "finite"),
    ("zones", lambda a: a.astype(float), "integers"),
    ("zones", lambda a: a + 50, "out of range"),
])
def test_crafted_world_arrays_are_refused(snap, name, make, message):
    with np.load(snap / "world.npz") as arrays:
        bad = make(arrays[name])
    tamper(snap, name, bad)
    with pytest.raises(ValueError, match=message):
        load_snapshot(snap)
