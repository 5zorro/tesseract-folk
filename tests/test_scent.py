"""Food scent: a long-range smell per food type (M1 plan, slice 6)."""
import json

import numpy as np
import pytest

from sim import Config, Simulation
from sim.nursery import load_brain_pool, seed_brains
from sim.snapshot import load_snapshot, save_snapshot
from sim.world import World

SMALL = dict(size=16, initial_npcs=20, min_population=10)


def lone_patch(dims=2, size=16, **kw):
    """A world whose only food is one cell of type 1."""
    w = World(Config(dims=dims, size=size, **kw), np.random.default_rng(0))
    w.food[:] = 0.0
    w.capacity[:] = 0.0
    w.food[(1,) + (size // 2,) * dims] = 2.0
    return w


@pytest.mark.parametrize("dims,size", [(2, 16), (4, 8)])
def test_scent_spreads_from_food_and_points_toward_it(dims, size):
    w = lone_patch(dims, size)
    for _ in range(100):
        w.step()
    center = (size // 2,) * dims
    near = (size // 2 - 2,) + (size // 2,) * (dims - 1)
    far = (size // 2 - 4,) + (size // 2,) * (dims - 1)
    assert w.scent_at(center)[1] > w.scent_at(near)[1] > w.scent_at(far)[1] > 0
    assert w.scent_at(far)[0] == 0 and w.scent_at(far)[2] == 0   # only type 1 smells


@pytest.mark.parametrize("dims,size", [(2, 16), (4, 8)])
def test_meal_scent_ignores_crumbs(dims, size):
    w = lone_patch(dims, size, scent_min_food=0.2)
    crumb = (size // 4,) * dims
    w.food[(0,) + crumb] = 0.15                      # a crumb of type 0: below a bite
    w.step()
    center = (size // 2,) * dims
    assert w.scent[0].max() == 0                     # the crumb is silent
    assert w.scent_at(center)[1] > 0                 # the meal smells...
    plain = lone_patch(dims, size)
    plain.step()
    assert w.scent_at(center)[1] < plain.scent_at(center)[1]   # ...by its amount beyond a bite


def test_scent_is_a_signal_not_mass():
    w = lone_patch()
    start = w.mass()
    for _ in range(50):
        w.step()
    assert w.scent.sum() > 0
    assert w.mass() == pytest.approx(start, rel=1e-12)


def test_scent_off_leaves_the_field_empty():
    w = lone_patch(food_scent=False)
    for _ in range(20):
        w.step()
    assert not w.scent.any()


@pytest.mark.parametrize("dims", [2, 4])
def test_scent_senses_add_level_and_gradient_per_food_type(dims):
    shape = {**SMALL, "dims": dims, "size": 6 if dims == 4 else 16}
    on = Simulation(Config(**shape), log_every=1000)
    off = Simulation(Config(**shape, food_scent=False), log_every=1000)
    t = on.cfg.n_food_types
    assert on.n_inputs - off.n_inputs == t + dims * t
    on.run(30)
    obs = on.sense(on.npcs[0], on._spatial_index())
    scent = obs[-(t + dims * t):]
    assert np.all((scent[:t] >= 0) & (scent[:t] < 1))      # level, squashed
    assert np.all(np.abs(scent[t:]) <= 1)                   # relative gradient


def test_off_keeps_the_pre_scent_input_size():
    assert Simulation(Config(**SMALL, food_scent=False), log_every=1000).n_inputs == 38


def test_npc_sees_which_way_the_scent_is():
    sim = Simulation(Config(**SMALL), log_every=1000)
    sim.world.scent[:] = 0.0
    sim.world.scent[1, 5, 8] = 1.0         # type 1 smells, one cell up axis 0
    npc = sim.npcs[0]
    npc.pos = (4, 8)
    t, d = sim.cfg.n_food_types, sim.cfg.dims
    grad = sim.sense(npc, sim._spatial_index())[-d * t:].reshape(d, t)
    assert grad[0, 1] == pytest.approx(1.0)
    assert grad[1, 1] == 0 and grad[0, 0] == 0


def test_scent_survives_a_snapshot(tmp_path):
    a = Simulation(Config(**SMALL), log_every=1000)
    a.run(60)
    b = load_snapshot(save_snapshot(a, tmp_path / "s"), log_every=1000)
    assert np.array_equal(a.world.scent, b.world.scent)
    a.run(30)
    b.run(30)
    assert [n.pos for n in a.npcs] == [n.pos for n in b.npcs]


def make_format_1(path):
    """Rewrite a no-scent snapshot the way the code saved it before slice 6."""
    state = json.loads((path / "state.json").read_text())
    state["format"] = 1
    del state["config"]["food_scent"]
    (path / "state.json").write_text(json.dumps(state))
    with np.load(path / "world.npz") as arrays:
        kept = {k: arrays[k] for k in arrays.files if k != "scent"}
    np.savez_compressed(path / "world.npz", **kept)


def test_pre_scent_snapshots_resume_without_scent(tmp_path):
    a = Simulation(Config(**SMALL, food_scent=False), log_every=1000)
    a.run(60)
    path = save_snapshot(a, tmp_path / "old")
    make_format_1(path)
    b = load_snapshot(path, log_every=1000)
    assert b.cfg.food_scent is False
    a.run(30)
    b.run(30)
    assert [n.pos for n in a.npcs] == [n.pos for n in b.npcs]


def test_pre_scent_pools_need_scent_off(tmp_path):
    a = Simulation(Config(**SMALL, food_scent=False), log_every=1000)
    a.run(60)
    pool = load_brain_pool(save_snapshot(a, tmp_path / "old"))
    with pytest.raises(ValueError, match="food_scent"):
        seed_brains(Simulation(Config(**SMALL), log_every=1000), pool)
    seed_brains(Simulation(Config(**SMALL, food_scent=False), log_every=1000), pool)
