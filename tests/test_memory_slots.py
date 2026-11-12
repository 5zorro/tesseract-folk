"""Memory slots and the memory net (Config.memory_slots; docs/plan-memory-reaction.md
MR2): the forager senses K slots, a second net in the same genome writes and
forgets them, and both nets are inherited, saved and checked together."""
import json

import numpy as np
import pytest

from sim import Config, Simulation
from sim.brain import Brain
from sim.npc import memory_net_shape
from sim.nursery import seed_brains
from sim.reference import ReferenceSimulation
from sim.snapshot import load_snapshot, save_snapshot

SMALL = dict(size=12, initial_npcs=6, min_population=0, seed=5)
ENGINES = [Simulation, ReferenceSimulation]


def first(sim):
    return min(sim.npcs, key=lambda n: n.id)


def forced(sim, choice: int) -> Brain:
    """A copy of the first NPC's brain whose memory net always picks `choice`."""
    brain = first(sim).brain
    m = brain.memory
    b2 = np.full_like(m.b2, -50.0)
    b2[choice] = 50.0
    return brain.with_memory(Brain(np.zeros_like(m.w1), m.b1 * 0, np.zeros_like(m.w2), b2))


def sense_of(sim, npc):
    return sim.sense(npc) if isinstance(sim, Simulation) else sim.sense(npc, sim._spatial_index())


def test_slots_add_their_senses_last_and_the_memory_net_reads_them_all():
    plain = Simulation(Config(**SMALL, reaction_queue=2))
    sim = Simulation(Config(**SMALL, reaction_queue=2, memory_slots=4))
    d, t = sim.cfg.dims, sim.cfg.n_food_types
    assert sim.n_inputs == plain.n_inputs + 4 * (2 + d + t)
    layout = sim.sense_layout()
    assert layout["slots"] == slice(plain.n_inputs, sim.n_inputs)
    assert list(layout)[-2:] == ["queue", "slots"]
    m = first(sim).brain.memory
    assert (m.n_in, m.n_hidden, m.n_out) == memory_net_shape(sim.cfg, sim.n_inputs) == (sim.n_inputs, 8, 9)
    assert ReferenceSimulation(Config(**SMALL, reaction_queue=2, memory_slots=4)).n_inputs == sim.n_inputs


def test_a_new_memory_net_rarely_writes():
    sim = Simulation(Config(size=16, initial_npcs=40, min_population=0, seed=2, memory_slots=8))
    sim.run(200)
    h = sim.stats.history + [sim.stats.window]
    ops = sum(x.get("memory_writes", 0) + x.get("memory_forgets", 0) for x in h)
    npc_ticks = sum(x.get("population", 0) for x in sim.stats.history) * sim.stats.log_every
    assert 0.01 < ops / npc_ticks < 0.15                    # memory_write_start = 0.05


@pytest.mark.parametrize("engine", ENGINES)
def test_remember_writes_here_now_and_what_grows_here(engine):
    sim = engine(Config(**SMALL, memory_slots=3))
    npc = first(sim)
    npc.brain = forced(sim, 1)                              # remember in slot 1
    sim.step()
    npc = first(sim)
    assert list(npc.mem_filled) == [False, True, False]
    assert npc.mem_tick[1] == sim.tick
    # Written while deciding, so from where it stood before this tick's move.
    assert tuple(npc.mem_pos[1]) != () and npc.mem_food[1].shape == (sim.cfg.n_food_types,)
    obs = sense_of(sim, npc)
    if isinstance(sim, Simulation):
        part = obs[sim.sense_layout()["slots"]].reshape(3, -1)
        assert part[1, 0] == 1.0 and part[0].sum() == 0 and part[2].sum() == 0
        assert np.allclose(part[1, -sim.cfg.n_food_types:], npc.mem_food[1])


@pytest.mark.parametrize("engine", ENGINES)
def test_forget_clears_a_slot(engine):
    sim = engine(Config(**SMALL, memory_slots=3))
    npc = first(sim)
    sim.write_memory(npc, 2, (1, 1))
    npc.brain = forced(sim, 3 + 2)                          # forget slot 2
    sim.step()
    npc = first(sim)
    assert not npc.mem_filled.any() and not npc.mem_pos.any() and not npc.mem_food.any()


@pytest.mark.parametrize("engine", ENGINES)
def test_nothing_leaves_the_slots_alone(engine):
    sim = engine(Config(**SMALL, memory_slots=3))
    npc = first(sim)
    sim.write_memory(npc, 0, (2, 3), food=[0.5, 0.25, 0.0])
    npc.brain = forced(sim, 6)                              # nothing
    for _ in range(5):
        sim.step()
    npc = first(sim)
    assert list(npc.mem_filled) == [True, False, False]
    assert tuple(npc.mem_pos[0]) == (2, 3) and list(npc.mem_food[0]) == [0.5, 0.25, 0.0]


@pytest.mark.parametrize("engine", ENGINES)
def test_write_memory_checks_its_arguments(engine):
    sim = engine(Config(**SMALL, memory_slots=2))
    npc = first(sim)
    for slot, pos, food in [(2, (1, 1), None), (-1, (1, 1), None), (0, (99, 1), None),
                            (0, (1, 1, 1), None), (0, (1, 1), [1.0]), (0, (1, 1), [np.nan, 0, 0])]:
        with pytest.raises(ValueError):
            sim.write_memory(npc, slot, pos, food)


def test_slot_senses_point_home_and_fade():
    sim = Simulation(Config(**SMALL, memory_slots=2, memory_tau=100.0))
    npc = first(sim)
    x, y = npc.pos
    sim.write_memory(npc, 0, ((x + 3) % 12, y), food=[1.0, 0.0, 0.0])
    tick0 = sim.tick
    part = sim.sense(npc)[sim.sense_layout()["slots"]].reshape(2, -1)
    assert list(part[0, :4]) == [1.0, 3 / 6, 0.0, 1.0]     # filled, +3 cells on axis 0 (/ half), fresh
    sim.batch.tick = tick0 + 100
    part = sim.sense(npc)[sim.sense_layout()["slots"]].reshape(2, -1)
    assert part[0, 3] == pytest.approx(np.exp(-1.0))


def test_the_genome_mutates_crosses_and_saves_both_nets():
    rng = np.random.default_rng(0)
    a = Brain.random(10, 4, 5, rng).with_memory(Brain.random(10, 3, 7, rng))
    b = Brain.random(10, 4, 5, rng).with_memory(Brain.random(10, 3, 7, rng))
    assert a.n_params == sum(x.size for x in a._arrays()) + a.memory.n_params
    m = a.mutate(1.0, 0.1, np.random.default_rng(1))
    assert not np.allclose(m.memory.w1, a.memory.w1)
    c = Brain.crossover(a, b, np.random.default_rng(2))
    assert np.all((c.memory.w2 == a.memory.w2) | (c.memory.w2 == b.memory.w2))
    back = Brain.from_dict(json.loads(json.dumps(a.to_dict())))
    assert np.array_equal(back.memory.w1, a.memory.w1)
    back.check(10, 4, 5, (10, 3, 7))
    with pytest.raises(ValueError, match="memory slots"):
        back.check(10, 4, 5)
    with pytest.raises(ValueError, match="lacks"):
        Brain.random(10, 4, 5, rng).check(10, 4, 5, (10, 3, 7))
    nested = a.to_dict()
    nested["memory"]["memory"] = a.memory.to_dict()
    with pytest.raises(ValueError, match="own memory net"):
        Brain.from_dict(nested)
    with pytest.raises(ValueError):
        Brain.crossover(a, Brain.random(10, 4, 5, rng), rng)
    # A forager's mutations don't depend on whether it carries a memory net.
    plain = Brain(a.w1, a.b1, a.w2, a.b2)
    assert np.array_equal(plain.mutate(0.3, 0.1, np.random.default_rng(5)).w1,
                          a.mutate(0.3, 0.1, np.random.default_rng(5)).w1)


@pytest.mark.parametrize("engine", ENGINES)
def test_each_net_has_its_own_mutation_budget(engine):
    """A memory net doesn't thin the forager's mutations: each gets
    mutations_per_birth expected mutated weights per child (2026-11-11)."""
    cfg = dict(**{**SMALL, "seed": 3}, mutation_lineage=False, mutations_per_birth=12.0)
    plain, sim = engine(Config(**cfg)), engine(Config(**cfg, memory_slots=4))
    b = first(sim).brain
    assert b.memory.n_params != b.own_params
    rate = sim.mutation_rate(b, -1.0)
    assert rate * b.own_params == pytest.approx(12.0)
    assert b.memory_rate(rate, 12.0) * b.memory.n_params == pytest.approx(12.0)
    _, expected, _ = sim.mutate_child(b, -1.0)
    assert expected == pytest.approx(24.0)
    _, expected, _ = plain.mutate_child(first(plain).brain, -1.0)
    assert expected == pytest.approx(12.0)
    # Per-weight mode (old snapshots): both nets at the same rate.
    assert b.memory_rate(0.1, 0.0) == 0.1


@pytest.mark.parametrize("queue", [0, 3])
def test_pools_without_slots_warm_start_with_a_new_memory_net(queue):
    old = Simulation(Config(**SMALL))
    pool = [{"fitness": 1.0, "generation": 3, "brain": n.brain} for n in old.npcs]
    new = Simulation(Config(**SMALL, reaction_queue=queue, memory_slots=8))
    seed_brains(new, pool)
    brain = first(new).brain
    assert brain.n_in == new.n_inputs and brain.memory is not None
    assert np.allclose(brain.w1[:, :old.n_inputs], first(old).brain.w1)
    assert not brain.w1[:, old.n_inputs:].any()
    again = Simulation(Config(**SMALL, reaction_queue=queue, memory_slots=8))
    seed_brains(again, pool)
    assert np.array_equal(first(again).brain.memory.w1, brain.memory.w1)      # keyed, so repeatable


def test_snapshots_keep_slots_and_memory_nets(tmp_path):
    sim = Simulation(Config(**SMALL, memory_slots=4, memory_write_start=0.5))
    sim.run(30)
    before = {n.id: (n.mem_filled.tolist(), n.mem_pos.tolist(), n.brain.memory.w2.tolist()) for n in sim.npcs}
    assert any(any(f) for f, _, _ in before.values())
    save_snapshot(sim, tmp_path / "m")
    back = load_snapshot(tmp_path / "m")
    assert {n.id: (n.mem_filled.tolist(), n.mem_pos.tolist(), n.brain.memory.w2.tolist())
            for n in back.npcs} == before
    assert all(e["brain"].memory is not None for e in back.hall_of_fame)


def test_old_snapshots_load_with_slots_off(tmp_path):
    save_snapshot(Simulation(Config(**SMALL)), tmp_path / "old")
    state_file = tmp_path / "old" / "state.json"
    state = json.loads(state_file.read_text())
    for key in ("memory_slots", "memory_net_hidden", "memory_tau", "memory_write_start"):
        state["config"].pop(key)
    for npc in state["npcs"]:
        for key in ("mem_pos", "mem_tick", "mem_food", "mem_filled"):
            npc.pop(key)
    state_file.write_text(json.dumps(state))
    back = load_snapshot(tmp_path / "old")
    assert back.cfg.memory_slots == 0 and all(n.brain.memory is None for n in back.npcs)


@pytest.mark.parametrize("field, value, message", [
    ("mem_pos", [[0, 0], [99, 0]], "remembered cell"),
    ("mem_pos", [[0, 0]], "shape"),
    ("mem_tick", [0, 1.5], "whole numbers"),
    ("mem_food", [[0, 0, 0], [0, np.nan, 0]], "NaN"),
])
def test_crafted_slots_are_refused_at_load(tmp_path, field, value, message):
    save_snapshot(Simulation(Config(**SMALL, memory_slots=2)), tmp_path / "s")
    state_file = tmp_path / "s" / "state.json"
    state = json.loads(state_file.read_text())
    state["npcs"][0][field] = value
    state_file.write_text(json.dumps(state).replace("NaN", "NaN"))
    with pytest.raises(ValueError, match=message):
        load_snapshot(tmp_path / "s")


def test_a_memory_net_in_a_world_without_slots_is_refused(tmp_path):
    save_snapshot(Simulation(Config(**SMALL, memory_slots=2)), tmp_path / "s")
    state_file = tmp_path / "s" / "state.json"
    state = json.loads(state_file.read_text())
    state["config"]["memory_slots"] = 0
    for npc in state["npcs"]:
        for key in ("mem_pos", "mem_tick", "mem_food", "mem_filled"):
            npc[key] = []
    state_file.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="memory"):
        load_snapshot(tmp_path / "s")


@pytest.mark.parametrize("kw", [dict(memory_tau=0.0), dict(memory_write_start=1.0),
                                dict(memory_write_start=0.0), dict(memory_slots=65)])
def test_bad_memory_settings_are_refused(kw):
    for engine in ENGINES:
        with pytest.raises(ValueError):
            engine(Config(**{**SMALL, "memory_slots": 2, **kw}))
