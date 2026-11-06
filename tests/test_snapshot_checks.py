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


@pytest.mark.parametrize("field,bad", [("lineage", float("nan")), ("body", float("inf")),
                                       ("nutrients", [0.5, float("nan"), 0.5])])
def test_npc_numbers_must_be_finite(tmp_path, field, bad):
    import json
    sim = Simulation(Config(size=8, initial_npcs=3, min_population=1, seed=1), log_every=10**9)
    save_snapshot(sim, tmp_path / "s")
    state = json.loads((tmp_path / "s" / "state.json").read_text())
    state["npcs"][0][field] = bad
    (tmp_path / "s" / "state.json").write_text(json.dumps(state))
    with pytest.raises(ValueError, match=field):
        load_snapshot(tmp_path / "s")


@pytest.mark.parametrize("kw", [dict(action_temperature=0.0), dict(mutations_per_birth=-1.0),
                                dict(hall_of_fame_min_copies=-1)])
def test_bad_settings_are_refused_at_start(kw):
    with pytest.raises(ValueError, match=next(iter(kw))):
        Simulation(Config(size=8, **kw), log_every=10**9)


@pytest.mark.parametrize("field, value, message", [
    ("pos", [99, 3], "position"), ("pos", [-1, 2], "position"), ("pos", [1, 2, 3], "position"),
    ("zones_eaten", [[0, -1]], "zone"), ("last_zone", [7, 0], "zone"),
    ("damage", {"lava": 0.1}, "damage"), ("origin", "alien", "origin"), ("nutrients", [0.5], "nutrients"),
])
def test_crafted_npcs_fail_clearly_at_load(snap, field, value, message):
    """A negative index would otherwise wrap silently into the arrays."""
    import json
    state = json.loads((snap / "state.json").read_text())
    state["npcs"][0][field] = value
    (snap / "state.json").write_text(json.dumps(state))
    with pytest.raises(ValueError, match=message):
        load_snapshot(snap)
