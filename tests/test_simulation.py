import pytest

from sim import Config, Simulation
from sim.controllers import ScriptedController, describe_observation
from sim.snapshot import load_snapshot, save_snapshot


def small(**kw):
    base = dict(size=16, initial_npcs=20, min_population=10)
    base.update(kw)
    return Config(**base)


def test_total_mass_is_conserved():
    sim = Simulation(small(), log_every=50)
    start = sim.total_mass()
    sim.run(600)
    assert sim.total_mass() == pytest.approx(start, rel=1e-9)


def test_runs_in_4d():
    sim = Simulation(small(dims=4, size=6), log_every=10)
    start = sim.total_mass()
    sim.run(50)
    assert sim.n_actions == 8 + 9
    assert sim.total_mass() == pytest.approx(start, rel=1e-9)


def test_aging_pauses_when_player_afk():
    sim = Simulation(small(), log_every=1000)
    sim.clock.player_active = False
    ages = {n.id: n.age for n in sim.npcs}
    sim.run(10)
    # Only collapses (a penalty) can add age while AFK.
    for n in sim.npcs:
        if n.id in ages and n.collapses == 0:
            assert n.age == ages[n.id]


def test_turning_the_clock_ages_npcs_even_when_afk():
    sim = Simulation(small(), log_every=1000)
    sim.clock.player_active = False
    sim.fast_forward(20)
    assert any(n.age >= 20 for n in sim.npcs)


def test_world_freezes_when_configured():
    sim = Simulation(small(freeze_all_when_afk=True), log_every=1000)
    sim.clock.player_active = False
    assert sim.step() is False
    assert sim.tick == 0


def test_young_npcs_collapse_instead_of_dying():
    sim = Simulation(small(), log_every=1000)
    npc = sim.npcs[0]
    npc.health = -1
    sim.metabolize([npc], aging=False)
    assert npc.alive and npc.collapses == 1


def test_elders_die_and_return_mass():
    sim = Simulation(small(), log_every=1000)
    start = sim.total_mass()
    npc = sim.npcs[0]
    npc.age = sim.cfg.old_age + 1
    npc.health = -1
    sim.metabolize([npc], aging=False)
    assert not npc.alive
    sim.npcs = [n for n in sim.npcs if n.alive]
    assert sim.total_mass() == pytest.approx(start, rel=1e-9)


def test_snapshot_roundtrip_continues_identically(tmp_path):
    a = Simulation(small(), log_every=1000)
    a.run(100)
    save_snapshot(a, tmp_path / "snap")
    b = load_snapshot(tmp_path / "snap", log_every=1000)
    a.run(50)
    b.run(50)
    assert a.tick == b.tick
    assert len(a.npcs) == len(b.npcs)
    assert a.total_mass() == pytest.approx(b.total_mass(), rel=1e-12)
    assert [n.pos for n in a.npcs] == [n.pos for n in b.npcs]


def test_scripted_controller_override():
    sim = Simulation(small(), log_every=1000)
    sim.overrides[sim.npcs[0].id] = ScriptedController()
    sim.run(20)
    assert "Possible actions" in describe_observation(sim, sim.npcs[0])
