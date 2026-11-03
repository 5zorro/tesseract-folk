"""Collapse/death cause attribution and per-generation collapse rates (M1 slice 1)."""
import pytest

from sim import Config, Simulation
from sim.stats import CAUSES


def small(**kw):
    base = dict(size=16, initial_npcs=20, min_population=10)
    base.update(kw)
    return Config(**base)


@pytest.mark.parametrize("dims,size", [(2, 16), (4, 6)])
def test_cause_counts_add_up_every_window(dims, size):
    sim = Simulation(small(dims=dims, size=size), log_every=50)
    sim.run(600)
    assert sum(h["collapses"] for h in sim.stats.history) > 0
    for h in sim.stats.history:
        assert sum(h[f"collapse_{c}"] for c in CAUSES) == h["collapses"]
        assert sum(h[f"death_{c}"] for c in CAUSES) == h["deaths"]


def test_smiting_collapse_is_blamed_on_smite():
    sim = Simulation(small(), log_every=1000)
    npc = sim.npcs[0]
    npc.piety, npc.smite, npc.health = 0.0, 0.4, 0.2   # one more bad prayer smites
    assert sim.deity.pray(npc, sim.tick) == "smitten"
    sim._metabolize(npc, aging=False)
    assert npc.collapses == 1
    assert sim.stats.window["collapse_smite"] == 1
    assert npc.damage == {}                            # fresh start after a collapse


def test_starvation_collapse_is_blamed_on_nutrients():
    sim = Simulation(small(), log_every=1000)
    npc = sim.npcs[0]
    npc.nutrients[:] = 0.0
    npc.health = 0.01
    sim._metabolize(npc, aging=False)
    assert sim.stats.window["collapse_nutrient_starve"] == 1


def test_elder_death_is_blamed_on_age():
    sim = Simulation(small(), log_every=1000)
    npc = sim.npcs[0]
    npc.age = 2 * sim.cfg.old_age
    npc.health = 0.001
    sim._metabolize(npc, aging=False)
    assert not npc.alive
    assert sim.stats.window["death_elder"] == 1


def test_damage_record_clears_once_fully_healed():
    sim = Simulation(small(), log_every=1000)
    npc = sim.npcs[0]
    npc.take_damage("stink", 0.005)
    assert npc.damage == {"stink": 0.005}
    sim._metabolize(npc, aging=False)                  # healthy and fed: heals to 1.0
    assert npc.health == 1.0 and npc.damage == {}


def test_generation_tallies_match_run_totals():
    sim = Simulation(small(), log_every=50)
    sim.run(400)
    total = sum(h["collapses"] for h in sim.stats.history)
    assert sum(sim.stats.generation_collapses.values()) == total
    rates = sim.stats.collapse_rate_by_generation()
    assert rates and all(r >= 0 for r in rates.values())
