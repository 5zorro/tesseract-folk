"""The multi-seed harness in scripts/sweep.py (M1 slice 2)."""
import math

import pytest

from scripts.sweep import bucket_rates, cover_with, distances, parse_overrides, run_one, where_now
from sim import Config, Simulation
from sim.controllers import ScriptedController

SMALL = dict(size=16, initial_npcs=20, min_population=10)


def test_overrides_take_the_config_field_types():
    o = parse_overrides("smite_damage=0, hidden_units=24,freeze_all_when_afk=true,controller=scripted")
    assert o == {"smite_damage": 0.0, "hidden_units": 24,
                 "freeze_all_when_afk": True, "controller": "scripted"}
    assert isinstance(o["smite_damage"], float) and isinstance(o["hidden_units"], int)


@pytest.mark.parametrize("bad", ["nope=1", "hidden_units=2.5", "smite_damage",
                                 "controller=magic", "freeze_all_when_afk=maybe"])
def test_bad_overrides_fail_loudly(bad):
    with pytest.raises(ValueError):
        parse_overrides(bad)


def test_same_seed_and_config_give_the_same_summary():
    a = run_one(SMALL, seed=3, ticks=300, late_from=0.5, log_every=50)
    b = run_one(SMALL, seed=3, ticks=300, late_from=0.5, log_every=50)
    assert a.keys() == b.keys()
    for key in a:
        assert a[key] == b[key] or (math.isnan(a[key]) and math.isnan(b[key])), key


def test_different_seeds_differ():
    a = run_one(SMALL, seed=1, ticks=300, late_from=0.5, log_every=50)
    b = run_one(SMALL, seed=2, ticks=300, late_from=0.5, log_every=50)
    assert a["collapse_rate"] != b["collapse_rate"]


def test_scripted_cover_includes_new_npcs_and_drops_dead_ones():
    sim = Simulation(Config(**SMALL), log_every=1000)
    ctrl = ScriptedController()
    cover_with(sim, ctrl)
    gone = sim.npcs.pop()                             # as if it died
    newcomer = sim._spawn(sim._random_brain(), sim.world.random_cell(sim.rng), 1.0, 0)
    cover_with(sim, ctrl)
    assert sim.overrides[newcomer.id] is ctrl
    assert gone.id not in sim.overrides
    assert set(sim.overrides) == {n.id for n in sim.npcs}


def test_scripted_run_works_in_4d():
    out = run_one({**SMALL, "dims": 4, "size": 6, "controller": "scripted"},
                  seed=0, ticks=60, late_from=0.5, log_every=20)
    assert out["population"] > 0


def test_bucket_rates_skip_thin_buckets():
    rates = bucket_rates({0: 1000, 1: 500, 2: 500, 7: 100}, {0: 10, 1: 5, 2: 0, 7: 1})
    assert rates["g0"] == 10.0
    assert rates["g1-2"] == 5.0
    assert math.isnan(rates["g3-5"]) and math.isnan(rates["g6-10"])   # none / under the minimum


def test_distance_skips_npcs_that_collapsed_in_between():
    sim = Simulation(Config(size=16, initial_npcs=3, min_population=1), log_every=1000)
    a, b, c = sim.npcs
    before = where_now(sim)
    a.pos = ((a.pos[0] + 3) % 16, (a.pos[1] + 4) % 16)    # moved 5 cells
    b.collapses += 1                                       # teleported: skipped
    assert sorted(distances(before, sim)) == [0.0, 5.0]
