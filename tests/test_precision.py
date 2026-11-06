"""Config.precision (docs/plan-gpu-backend.md D2): the array engine at float32."""
import numpy as np
import pytest

from sim import Config, Simulation
from sim.simulation import Batch
from sim.snapshot import load_snapshot, save_snapshot

SMALL = dict(size=12, initial_npcs=20, min_population=15, seed=3)


@pytest.mark.parametrize("dims", [2, 4])
def test_float32_runs_in_float32_and_keeps_mass(dims):
    sim = Simulation(Config(**{**SMALL, "dims": dims, "size": 12 if dims == 2 else 5}, precision="float32"),
                     log_every=50)
    start = sim.total_mass()
    sim.run(300)
    for a in (sim.world.food, sim.world.soil, sim.world.stink, sim.pop.body, sim.pop.nutrients, sim.pop.w1):
        assert a.dtype == np.float32
    assert sim.npcs
    assert sim.total_mass() == pytest.approx(start, rel=1e-5)   # float32: ~7 digits


def test_precision_is_checked_and_shapes_a_batch():
    with pytest.raises(ValueError, match="precision"):
        Simulation(Config(**SMALL, precision="float16"))
    with pytest.raises(ValueError, match="precision"):
        Batch([Simulation(Config(**SMALL)), Simulation(Config(**SMALL, precision="float32"))])


def test_float32_snapshots_resume(tmp_path):
    a = Simulation(Config(**SMALL, precision="float32"), log_every=50)
    a.run(60)
    b = load_snapshot(save_snapshot(a, tmp_path / "s"))
    assert b.cfg.precision == "float32" and b.world.food.dtype == np.float32
    a.run(40)
    b.run(40)
    assert [n.pos for n in a.npcs] == [n.pos for n in b.npcs]


def test_the_plug_holds_float32_mass_to_its_ledger():
    sim = Simulation(Config(**SMALL, precision="float32", mass_plug_every=10), log_every=50)
    start = sim.total_mass()
    sim.run(1000)                                     # ends on a plug tick
    assert sim.total_mass() == pytest.approx(start, rel=1e-8)   # one float32 rounding of a soil cell
    assert sim.stats.mass_plugs > 0
    assert abs(sim.stats.mass_plugged) < 1e-5 * start


def test_a_real_leak_is_an_error_not_a_plug():
    sim = Simulation(Config(**SMALL, precision="float32", mass_plug_every=10), log_every=50)
    sim.run(10)
    sim.world.food[...] *= 0.5                         # a "bug" that destroys mass
    with pytest.raises(RuntimeError, match="conservation bug"):
        sim.run(10)


def test_moving_mass_in_from_outside_resets_the_ledger(tmp_path):
    sim = Simulation(Config(**SMALL, precision="float32", mass_plug_every=10), log_every=50)
    sim.run(10)
    sim.npcs = sim.npcs[:5]                            # a test or script removes NPCs on purpose
    sim.run(30)                                        # no error: the ledger re-reads the total
    b = load_snapshot(save_snapshot(sim, tmp_path / "s"))
    b.run(30)


def test_top_ups_keep_the_ledger():
    """Top-ups move mass from soil to a newcomer inside a tick; the ledger must
    not restart (it did once, letting drift through)."""
    sim = Simulation(Config(**{**SMALL, "min_population": 40}, precision="float32", mass_plug_every=10),
                     log_every=50)
    start = sim.total_mass()
    sim.run(500)
    assert sim.stats.window.get("spawns", 0) + sum(h["spawns"] for h in sim.stats.history) > 0
    assert sim.total_mass() == pytest.approx(start, rel=1e-8)
