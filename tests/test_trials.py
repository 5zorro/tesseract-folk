"""Hall-of-fame trials (5zorro, 2026-11-06): a finished life is re-run as exact
clones and enters only if enough of its lives pass (sim/trials.py)."""
import pytest

from sim import Config, Simulation
from sim.snapshot import load_snapshot, save_snapshot

SMALL = dict(size=16, initial_npcs=20, min_population=15, seed=3, hall_of_fame_trials=2)


def world(**kw):
    sim = Simulation(Config(**{**SMALL, **kw}), log_every=10**9)
    for n in sim.npcs:                          # the population collapses twice per 1,000 ticks
        n.lifetime, n.collapses = 1000, 2
    sim.hall_of_fame = []
    return sim


def life(sim, collapses, trial_of=-1, offspring=0):
    npc = sim._make_npc(sim.npcs[0].brain, (0, 0), 1.0, 1)
    npc.collapses, npc.lifetime, npc.trial_of, npc.offspring = collapses, 1000, trial_of, offspring
    return npc


def test_a_first_life_waits_for_its_trials():
    sim = world()
    first = life(sim, 0)
    sim._record_hall_of_fame(first)
    assert sim.hall_of_fame == [] and [c["id"] for c in sim.trials] == [first.id]
    assert sim.trials[0]["to_spawn"] == 2


def test_two_of_three_passing_lives_enter_with_all_three_averaged():
    sim = world()
    first = life(sim, 0)                         # passes (0 < 2 per 1,000)
    sim._record_hall_of_fame(first)
    sim._record_hall_of_fame(life(sim, 3, trial_of=first.id))   # fails
    assert sim.hall_of_fame == []
    sim._record_hall_of_fame(life(sim, 1, trial_of=first.id))   # passes: 2 of 3
    (entry,) = sim.hall_of_fame
    assert entry["id"] == first.id and entry["lives"] == 3
    assert entry["excess_sum"] == pytest.approx((0 - 2) + (3 - 2) + (1 - 2))
    assert not any(k in entry for k in ("passes", "to_spawn")) and sim.trials == []


def test_a_candidate_that_can_no_longer_qualify_is_dropped_at_once():
    sim = world()
    first = life(sim, 5)
    sim._record_hall_of_fame(first)
    sim._record_hall_of_fame(life(sim, 4, trial_of=first.id))   # 0 of 2 so far, 1 left: can't reach 2
    assert sim.trials == [] and sim.hall_of_fame == []
    assert sim.stats.window["trial_reject"] == 1


def test_the_absolute_rule_and_the_children_requirement():
    sim = world(hall_of_fame_trial_max_collapses=0, hall_of_fame_trial_parents=2)
    first = life(sim, 0, offspring=1)
    sim._record_hall_of_fame(first)
    sim._record_hall_of_fame(life(sim, 0, trial_of=first.id))            # clean, no kids
    sim._record_hall_of_fame(life(sim, 0, trial_of=first.id, offspring=2))
    assert [e["id"] for e in sim.hall_of_fame] == [first.id]
    sim2 = world(hall_of_fame_trial_max_collapses=0, hall_of_fame_trial_parents=2)
    other = life(sim2, 0)
    sim2._record_hall_of_fame(other)
    sim2._record_hall_of_fame(life(sim2, 0, trial_of=other.id))          # no kids in 2 lives: can't reach 2
    assert sim2.hall_of_fame == [] and sim2.trials == []


def test_top_ups_clone_the_candidate_exactly():
    sim = world()
    first = life(sim, 0)
    sim._record_hall_of_fame(first)
    for n in list(sim.npcs)[:7]:                 # 20 -> 13, two below the floor of 15
        n.alive = False
    sim._top_up()
    clones = [n for n in sim.npcs if n.origin == "trial"]
    assert len(clones) == 2 and all(n.trial_of == first.id for n in clones)
    for n in clones:
        for a, b in zip(n.brain._arrays(), first.brain._arrays()):
            assert (a == b).all()
    assert sim.trials[0]["to_spawn"] == 0 and sim.trials[0]["out"] == 2


def test_candidates_survive_a_snapshot(tmp_path):
    sim = world()
    sim._record_hall_of_fame(life(sim, 0))
    save_snapshot(sim, tmp_path / "s")
    again = load_snapshot(tmp_path / "s")
    assert [(c["id"], c["to_spawn"], c["out"], c["passes"]) for c in again.trials] == \
        [(c["id"], c["to_spawn"], c["out"], c["passes"]) for c in sim.trials]


@pytest.mark.parametrize("kw", [dict(hall_of_fame_trials=99), dict(hall_of_fame_trial_passes=5),
                                dict(hall_of_fame_trial_parents=-1), dict(hall_of_fame_trial_max_collapses=-2)])
def test_bad_trial_settings_are_refused(kw):
    with pytest.raises(ValueError, match=next(iter(kw))):
        Simulation(Config(size=8, **{**dict(hall_of_fame_trials=2), **kw}), log_every=10**9)
