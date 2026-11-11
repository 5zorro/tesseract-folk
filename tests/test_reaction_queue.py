"""The reaction queue (Config.reaction_queue; docs/plan-memory-reaction.md MR1):
decided actions wait Q ticks, the queue is sensed, newborns start with "stay",
and controllers (the LLM pawn's seam) can pass or rewrite the queue."""
import json

import numpy as np
import pytest

from sim import Config, Simulation
from sim.brain import Brain
from sim.nursery import seed_brains
from sim.reference import ReferenceSimulation
from sim.snapshot import load_snapshot, save_snapshot

SMALL = dict(size=12, initial_npcs=6, min_population=0, seed=5)


class Script:
    """Returns its list of choices in turn (None = let the brain decide), and
    optionally rewrites the queue on a given tick."""

    def __init__(self, choices, rewrite=None):
        self.choices, self.rewrite = list(choices), rewrite or {}

    def decide(self, sim, npc, obs):
        if sim.tick in self.rewrite:
            npc.queue[:] = self.rewrite[sim.tick]
        return self.choices.pop(0) if self.choices else None


def first(sim):
    return min(sim.npcs, key=lambda n: n.id)


@pytest.mark.parametrize("engine", [Simulation, ReferenceSimulation])
def test_an_action_resolves_q_ticks_after_it_was_decided(engine):
    sim = engine(Config(**SMALL, reaction_queue=3))
    A = {a: i for i, a in enumerate(sim.actions)}
    npc = first(sim)
    assert list(npc.queue) == [A["stay"]] * 3               # newborns start with stay queued
    move, still = A["move+0"], A["stay"]
    sim.overrides[npc.id] = Script([move, still, move, still, still, still])
    path = []
    for _ in range(6):
        before = tuple(first(sim).pos)
        sim.step()
        path.append(tuple(first(sim).pos) != before)
    # Decided: move, stay, move, stay...; resolved three ticks later.
    assert path == [False, False, False, True, False, True]
    assert list(first(sim).queue) == [still, still, still]


def test_the_queue_is_sensed_last_as_one_hots():
    sim = Simulation(Config(**SMALL, reaction_queue=2))
    plain = Simulation(Config(**SMALL))
    A = sim.n_actions
    assert sim.n_inputs == plain.n_inputs + 2 * A
    layout = sim.sense_layout()
    assert layout["queue"] == slice(plain.n_inputs, plain.n_inputs + 2 * A)
    npc = first(sim)
    before = sim.sense(npc)
    npc.queue[:] = [1, 4]
    obs = sim.sense(npc)
    onehot = obs[layout["queue"]].reshape(2, A)
    assert onehot.sum() == 2 and list(onehot.argmax(axis=1)) == [1, 4]
    assert np.array_equal(obs[:plain.n_inputs], before[:plain.n_inputs])     # the rest is unchanged
    ref = ReferenceSimulation(Config(**SMALL, reaction_queue=2))
    ref_npc = first(ref)
    ref_npc.queue[:] = [1, 4]
    assert np.array_equal(ref.sense(ref_npc, ref._spatial_index())[layout["queue"]], obs[layout["queue"]])


def test_the_queue_needs_the_stay_action():
    with pytest.raises(ValueError, match="stay"):
        Simulation(Config(**SMALL, reaction_queue=1, actions_off="stay"))
    with pytest.raises(ValueError, match="stay"):
        ReferenceSimulation(Config(**SMALL, reaction_queue=1, actions_off="stay"))


@pytest.mark.parametrize("engine", [Simulation, ReferenceSimulation])
def test_a_controller_passing_leaves_the_brain_in_charge(engine):
    """Returning None is the just-in-time change-out: the run is identical to
    one with no controller (the brain ran, and kept its memory current)."""
    cfg = Config(**{**SMALL, "initial_npcs": 12}, reaction_queue=2)
    a, b = engine(cfg), engine(cfg)
    for npc in a.npcs:
        a.overrides[npc.id] = Script([])
    for _ in range(40):
        a.step()
        b.step()
    assert [n.to_dict() for n in sorted(a.npcs, key=lambda n: n.id)] == \
           [n.to_dict() for n in sorted(b.npcs, key=lambda n: n.id)]


@pytest.mark.parametrize("engine", [Simulation, ReferenceSimulation])
def test_a_controller_can_rewrite_the_queue(engine):
    sim = engine(Config(**SMALL, reaction_queue=3))
    A = {a: i for i, a in enumerate(sim.actions)}
    npc = first(sim)
    move, still = A["move+1"], A["stay"]
    sim.overrides[npc.id] = Script([still] * 3, rewrite={1: [move, move, still]})
    moved = []
    for _ in range(3):
        before = tuple(first(sim).pos)
        sim.step()
        moved.append(tuple(first(sim).pos) != before)
    assert moved == [True, True, False]                    # the rewritten queue resolved at once


@pytest.mark.parametrize("engine", [Simulation, ReferenceSimulation])
@pytest.mark.parametrize("bad", [-1, 10**6, 1.5, True])
def test_bad_controller_actions_are_refused(engine, bad):
    sim = engine(Config(**SMALL, reaction_queue=2))
    sim.overrides[first(sim).id] = Script([bad])
    with pytest.raises(ValueError):
        sim.step()


@pytest.mark.parametrize("engine", [Simulation, ReferenceSimulation])
def test_a_bad_rewritten_queue_is_refused(engine):
    sim = engine(Config(**SMALL, reaction_queue=2))
    sim.overrides[first(sim).id] = Script([None], rewrite={1: [0, -3]})
    with pytest.raises(ValueError, match="queued action"):
        sim.step()


def test_queue_order_doesnt_depend_on_list_order():
    cfg = Config(size=12, initial_npcs=30, min_population=34, seed=4, collapse_age_penalty=600,
                 reaction_queue=2)
    a, b = ReferenceSimulation(cfg, log_every=10**9), ReferenceSimulation(cfg, log_every=10**9)
    for _ in range(150):
        b.npcs.reverse()
        a.step()
        b.step()
    key = lambda s: sorted((n.to_dict() for n in s.npcs), key=lambda d: d["id"])   # noqa: E731
    assert key(a) == key(b)


def test_snapshots_keep_the_queue(tmp_path):
    sim = Simulation(Config(**SMALL, reaction_queue=3))
    sim.run(5)
    queues = {n.id: list(n.queue) for n in sim.npcs}
    save_snapshot(sim, tmp_path / "q")
    back = load_snapshot(tmp_path / "q")
    assert back.cfg.reaction_queue == 3
    assert {n.id: list(n.queue) for n in back.npcs} == queues


def test_old_snapshots_load_with_the_queue_off(tmp_path):
    sim = Simulation(Config(**SMALL))
    save_snapshot(sim, tmp_path / "old")
    state_file = tmp_path / "old" / "state.json"
    state = json.loads(state_file.read_text())
    state["config"].pop("reaction_queue")
    for npc in state["npcs"]:
        npc.pop("queue")
    state_file.write_text(json.dumps(state))
    back = load_snapshot(tmp_path / "old")
    assert back.cfg.reaction_queue == 0 and all(n.queue.size == 0 for n in back.npcs)


@pytest.mark.parametrize("value, message", [([0, 999, 1], "out of range"), ([0, -1, 1], "out of range"),
                                            ([0, 1], "shape"), ([0, 1.5, 2], "whole numbers")])
def test_crafted_queues_are_refused_at_load(tmp_path, value, message):
    sim = Simulation(Config(**SMALL, reaction_queue=3))
    save_snapshot(sim, tmp_path / "s")
    state_file = tmp_path / "s" / "state.json"
    state = json.loads(state_file.read_text())
    state["npcs"][0]["queue"] = value
    state_file.write_text(json.dumps(state))
    with pytest.raises(ValueError, match=message):
        load_snapshot(tmp_path / "s")


@pytest.mark.parametrize("hidden", [6, 0])
def test_widened_brains_act_as_before(hidden):
    rng = np.random.default_rng(0)
    brain = Brain.random(10, hidden, 5, rng)
    wide = brain.widen(14)
    x = rng.normal(size=10)
    for extra in (np.zeros(4), rng.normal(size=4)):
        assert np.allclose(wide.forward(np.concatenate([x, extra])), brain.forward(x))
    wide.check(14, hidden, 5)
    with pytest.raises(ValueError):
        brain.widen(9)


def test_brains_without_the_queue_warm_start_into_a_queued_world():
    """A pool saved before MR1 seeds a queued world: its brains gain zero-weight
    queue inputs (the last ones), so they choose exactly as before."""
    old = Simulation(Config(**SMALL))
    pool = [{"fitness": 1.0, "generation": 3, "brain": n.brain} for n in old.npcs]
    new = Simulation(Config(**SMALL, reaction_queue=3))
    seed_brains(new, pool)
    npc, before = first(new), first(old)
    assert npc.brain.n_in == new.n_inputs
    assert np.allclose(npc.brain.w1[:, :old.n_inputs], before.brain.w1)
    assert not npc.brain.w1[:, old.n_inputs:].any()
    with pytest.raises(ValueError, match="doesn't fit"):
        seed_brains(Simulation(Config(**SMALL, reaction_queue=3, hidden_units=4)), pool)
