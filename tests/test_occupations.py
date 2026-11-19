"""Occupations, O1 (docs/plan-occupations.md): posts with shifts, the fallback
walk for late workers, the frazzled debuff, wages, the work senses."""
import json

import numpy as np
import pytest

from sim import Config, Simulation
from sim.nursery import seed_brains
from sim.reference import ReferenceSimulation
from sim.snapshot import load_snapshot, save_snapshot
from sim.world import wrapped_delta

ENGINES = [Simulation, ReferenceSimulation]
WORK = dict(size=12, initial_npcs=3, min_population=0, seed=4, adult_age=0, n_posts=1,
            day_length=20, shift_length=6, frazzled_ticks=5)


class Stay:
    def decide(self, sim, npc, obs):
        return sim.actions.index("stay")


def first(sim):
    return min(sim.npcs, key=lambda n: n.id)


def still(sim):
    sim.overrides = {n.id: Stay() for n in sim.npcs}
    return sim


def counted(sim, name):
    return sum(h.get(name, 0) for h in sim.stats.history) + sim.stats.window.get(name, 0)


def away(cell, size, steps=3):
    return ((cell[0] + steps) % size,) + tuple(cell[1:])


def sense_of(sim, npc):
    return sim.sense(npc) if isinstance(sim, Simulation) else sim.sense(npc, sim._spatial_index())


def test_off_by_default_and_senses_go_last():
    plain = Simulation(Config(size=12, initial_npcs=3))
    sim = Simulation(Config(size=12, initial_npcs=3, n_posts=2, reaction_queue=2, memory_slots=1))
    assert "work" not in plain.sense_layout() and plain.posts == []
    assert list(sim.sense_layout())[-3:] == ["queue", "slots", "work"]
    assert sim.sense_layout()["work"].stop - sim.sense_layout()["work"].start == 5 + sim.cfg.dims
    assert ReferenceSimulation(sim.cfg).n_inputs == sim.n_inputs


def test_posts_follow_the_seed_and_spread_their_shifts():
    cfg = Config(size=16, n_posts=4, day_length=300, seed=9)
    a, b = Simulation(cfg), ReferenceSimulation(cfg)
    assert a.posts == b.posts
    assert [start for _, start in a.posts] == [0, 75, 150, 225]
    assert Simulation(Config(size=16, n_posts=4, seed=10)).posts != a.posts


@pytest.mark.parametrize("engine", ENGINES)
def test_adults_take_free_posts_lowest_id_first(engine):
    sim = still(engine(Config(**{**WORK, "adult_age": 3, "n_posts": 2, "initial_npcs": 4})))
    sim.step()
    assert all(n.post == -1 for n in sim.npcs)              # too young
    sim.run(3)
    assert {n.id: n.post for n in sim.npcs} == {0: 0, 1: 1, 2: -1, 3: -1}
    assert counted(sim, "work_assigned") == 2


@pytest.mark.parametrize("engine", ENGINES)
def test_on_time_shift_is_paid_from_the_soil(engine):
    sim = still(engine(Config(**WORK)))
    cell = sim.posts[0][0]
    npc = first(sim)
    npc.pos = cell
    start = sim.total_mass()
    sim.run(20)                                             # tick 20: the shift starts
    npc = first(sim)
    assert npc.post == 0 and not npc.walking and npc.shift_clean
    assert counted(sim, "work_on_time") == 1 and counted(sim, "work_late") == 0
    before = npc.inventory.copy()
    sim.run(6)                                              # tick 26: the first tick off shift
    npc = first(sim)
    assert counted(sim, "work_paid") == 1
    gained = npc.inventory - before
    t = int(np.flatnonzero(np.asarray(sim.world.rich) == int(np.argmin(npc.nutrients)))[0])
    assert gained[t] == pytest.approx(sim.cfg.wage) and gained.sum() == pytest.approx(sim.cfg.wage)
    assert sim.total_mass() == pytest.approx(start, rel=1e-12)


@pytest.mark.parametrize("engine", ENGINES)
def test_a_late_worker_is_walked_to_its_post_frazzled(engine):
    sim = still(engine(Config(**WORK)))
    cell = sim.posts[0][0]
    first(sim).pos = away(cell, 12)
    sim.step()                                              # tick 1: assigned mid-shift, far away
    npc = first(sim)
    assert counted(sim, "work_late") == 1 and npc.walking and npc.frazzled == 5 - 1   # metabolism ticked once
    assert int(np.abs(wrapped_delta(npc.pos, cell, 12)).sum()) == 2       # one step closer
    sim.step()
    npc = first(sim)
    assert int(np.abs(wrapped_delta(npc.pos, cell, 12)).sum()) == 1
    sim.step()                                              # within reach: the walk ends
    npc = first(sim)
    assert not npc.walking and npc.on_post and not npc.shift_clean
    assert counted(sim, "work_walk_ticks") == 2
    sim.run(3)                                              # tick 6, the first off shift: unpaid,
    assert counted(sim, "work_paid") == 0                   # the shift wasn't clean
    sim.run(20)                                             # the next shift starts on time: paid
    assert counted(sim, "work_on_time") == 1 and counted(sim, "work_paid") == 1


@pytest.mark.parametrize("engine", ENGINES)
def test_leaving_the_post_mid_shift_counts_and_frazzles(engine):
    sim = still(engine(Config(**WORK)))
    cell = sim.posts[0][0]
    first(sim).pos = cell
    sim.step()
    first(sim).pos = away(cell, 12, 2)
    sim.step()
    npc = first(sim)
    assert counted(sim, "work_left") == 1 and counted(sim, "work_late") == 0
    assert npc.walking and npc.frazzled > 0


@pytest.mark.parametrize("engine", ENGINES)
def test_the_walk_holds_the_queue_at_stay(engine):
    sim = still(engine(Config(**WORK, reaction_queue=3)))
    first(sim).pos = away(sim.posts[0][0], 12)
    sim.step()
    npc = first(sim)
    stay = sim.actions.index("stay")
    assert npc.walking and list(npc.queue) == [stay] * 3


@pytest.mark.parametrize("engine", ENGINES)
def test_frazzled_burns_hunger_faster(engine):
    sim = engine(Config(**{**WORK, "initial_npcs": 2, "frazzled_hunger_multiplier": 1.5}))
    a, b = sorted(sim.npcs, key=lambda n: n.id)
    b.frazzled = 3
    before = (a.nutrients.copy(), b.nutrients.copy())
    for n in (a, b):
        n.idle_streak = 0
    sim.metabolize(sorted(sim.npcs, key=lambda n: n.id), True)
    a, b = sorted(sim.npcs, key=lambda n: n.id)
    da, db = before[0] - a.nutrients, before[1] - b.nutrients
    assert np.allclose(db, 1.5 * da) and b.frazzled == 2


@pytest.mark.parametrize("engine", ENGINES)
def test_work_senses(engine):
    sim = still(engine(Config(**WORK)))
    cell = sim.posts[0][0]
    first(sim).pos = away(cell, 12, 2)
    sim.step()                                              # tick 1: late, walking, frazzled
    npc = first(sim)
    d = sim.cfg.dims
    part = sense_of(sim, npc)[-(5 + d):]
    delta = wrapped_delta(npc.pos, cell, 12)
    assert part[0] == 1.0 and part[1] == 1.0                # has a post, on shift
    assert part[2] == pytest.approx(((0 - sim.tick) % 20) / 20)
    assert part[3] == (1.0 if np.abs(delta).sum() <= 1 else 0.0)
    assert part[4] == pytest.approx(npc.frazzled / 5)
    assert np.allclose(part[5:], delta / 6)
    other = max(sim.npcs, key=lambda n: n.id)               # no post: zeros
    assert not sense_of(sim, other)[-(5 + d):].any()


def test_snapshots_keep_work_state_and_refuse_bad_posts(tmp_path):
    sim = still(Simulation(Config(**WORK)))
    first(sim).pos = away(sim.posts[0][0], 12)
    sim.step()
    save_snapshot(sim, tmp_path / "s")
    back = load_snapshot(tmp_path / "s")
    a, b = first(sim), first(back)
    assert (b.post, b.walking, b.frazzled, b.on_post, b.shift_clean) == \
           (a.post, a.walking, a.frazzled, a.on_post, a.shift_clean)
    assert back.posts == sim.posts
    state_file = tmp_path / "s" / "state.json"
    state = json.loads(state_file.read_text())
    state["npcs"][0]["post"] = 7
    state_file.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="post"):
        load_snapshot(tmp_path / "s")


def test_old_snapshots_load_with_posts_off(tmp_path):
    save_snapshot(Simulation(Config(size=12, initial_npcs=3)), tmp_path / "old")
    state_file = tmp_path / "old" / "state.json"
    state = json.loads(state_file.read_text())
    for key in ("n_posts", "day_length", "shift_length", "frazzled_ticks", "frazzled_hunger_multiplier",
                "frazzled_temperature", "wage"):
        state["config"].pop(key)
    for npc in state["npcs"]:
        for key in ("post", "walking", "frazzled", "on_post", "shift_clean"):
            npc.pop(key)
    state_file.write_text(json.dumps(state))
    back = load_snapshot(tmp_path / "old")
    assert back.cfg.n_posts == 0 and all(n.post == -1 for n in back.npcs)


@pytest.mark.parametrize("extra", [dict(), dict(reaction_queue=3), dict(reaction_queue=2, memory_slots=2)])
def test_pools_without_work_senses_warm_start(extra):
    old = Simulation(Config(size=12, initial_npcs=4))      # a pool from before the queue, slots and posts
    pool = [{"fitness": 1.0, "generation": 1, "brain": n.brain} for n in old.npcs]
    new = Simulation(Config(size=12, initial_npcs=4, n_posts=2, **extra))
    seed_brains(new, pool)
    brain = first(new).brain
    assert brain.n_in == new.n_inputs
    assert np.allclose(brain.w1[:, :old.n_inputs], first(old).brain.w1)
    assert not brain.w1[:, old.n_inputs:].any()


@pytest.mark.parametrize("kw", [dict(shift_length=20), dict(shift_length=0), dict(day_length=1),
                                dict(frazzled_ticks=-1), dict(wage=float("nan")), dict(wage=-0.1),
                                dict(frazzled_temperature=0.0), dict(frazzled_hunger_multiplier=-1.0),
                                dict(n_posts=-1)])
def test_bad_work_settings_are_refused(kw):
    for engine in ENGINES:
        with pytest.raises(ValueError):
            engine(Config(**{**WORK, **kw}))
