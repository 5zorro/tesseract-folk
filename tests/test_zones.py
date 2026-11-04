"""Food zones and travel metrics (M2 plan, slice 1)."""
import json

import numpy as np
import pytest

from sim import Config, Simulation
from sim.snapshot import load_snapshot, save_snapshot
from sim.world import World

SMALL = dict(size=16, initial_npcs=20, min_population=10)


@pytest.mark.parametrize("kw", [{}, {"dims": 4, "size": 10, "food_patch_radius": 2.0}])
def test_zones_are_the_cores_of_each_patch(kw):
    cfg = Config(**kw)
    w = World(cfg, np.random.default_rng(3))
    assert len(w.patch_centers) == cfg.n_food_types
    for t, centers in enumerate(w.patch_centers):
        assert len(centers) == cfg.food_patches_per_type
        in_core = w.capacity[t] >= cfg.zone_core * cfg.food_capacity
        assert np.array_equal(w.zones[t] >= 0, in_core)
        for c in centers:
            assert w.zone_at(t, c) >= 0            # a patch's center is always in a core


def test_zone_map_doesnt_change_the_world():
    # Recording zones uses no extra random draws, so worlds stay as they were.
    a = Simulation(Config(**SMALL, seed=5), populate=False)
    b = Simulation(Config(**SMALL, seed=5, zone_core=0.9), populate=False)
    assert np.array_equal(a.world.capacity, b.world.capacity)
    assert (b.world.zones >= 0).sum() < (a.world.zones >= 0).sum()   # stricter core


@pytest.mark.parametrize("kw", [{}, {"dims": 4, "size": 10, "food_patch_radius": 2.0}])
def test_shared_layout_grows_every_food_in_the_same_patches(kw):
    sep = World(Config(**kw), np.random.default_rng(3))
    shared = World(Config(**kw, food_layout="shared"), np.random.default_rng(3))
    for t in range(1, shared.cfg.n_food_types):
        ratio = shared.capacity[t] / shared.capacity[0]
        assert np.allclose(ratio, ratio.flat[0])            # same shape, same peaks
        assert shared.patch_centers[t] == shared.patch_centers[0]
        assert np.array_equal(shared.zones[t], shared.zones[0])
    assert np.allclose(shared.capacity.sum(axis=tuple(range(1, shared.capacity.ndim))),
                       sep.capacity.sum(axis=tuple(range(1, sep.capacity.ndim))))
    assert shared.shrines == sep.shrines                    # the rest of the world matches


def test_unknown_food_layout_is_refused():
    with pytest.raises(ValueError, match="food_layout"):
        World(Config(food_layout="mixed"), np.random.default_rng(0))


def test_shared_layout_survives_a_snapshot(tmp_path):
    a = Simulation(Config(**SMALL, food_layout="shared"), log_every=1000)
    a.run(60)
    b = load_snapshot(save_snapshot(a, tmp_path / "s"), log_every=1000)
    assert b.cfg.food_layout == "shared"
    assert np.array_equal(a.world.capacity, b.world.capacity)
    a.run(30)
    b.run(30)
    assert [n.pos for n in a.npcs] == [n.pos for n in b.npcs]


def eat_at(sim, npc, t, pos):
    npc.pos = pos
    here = sim.world.food_at(pos)
    here[:] = 0.0
    here[t] = 2.0
    npc.nutrients[:] = 0.2
    npc.satiation[:] = 0.0
    sim._eat(npc)


def core_cell(sim, t, patch):
    cells = np.argwhere(sim.world.zones[t] == patch)
    return tuple(int(v) for v in cells[0])


def only_in(sim, t, patch):
    """A cell in this zone's core and in no other food type's core."""
    others = [u for u in range(sim.cfg.n_food_types) if u != t]
    mask = (sim.world.zones[t] == patch) & np.all(sim.world.zones[others] < 0, axis=0)
    return tuple(int(v) for v in np.argwhere(mask)[0])


def test_bites_in_zones_are_recorded_and_switches_counted():
    sim = Simulation(Config(**SMALL, food_patch_radius=2.0), log_every=1000)
    npc = sim.npcs[0]
    a = only_in(sim, 0, sim.world.zone_at(0, sim.world.patch_centers[0][0]))
    other_type = only_in(sim, 1, sim.world.zone_at(1, sim.world.patch_centers[1][0]))
    eat_at(sim, npc, 0, a)
    assert npc.zones_eaten == {(0, sim.world.zone_at(0, a))} and npc.zone_switches == 0
    eat_at(sim, npc, 0, a)                         # same zone again: no switch
    assert npc.zone_switches == 0
    eat_at(sim, npc, 1, other_type)
    assert npc.zone_switches == 1 and len(npc.zones_eaten) == 2
    assert sim.stats.window["zone_switches"] == 1


def test_eating_another_food_where_zones_overlap_isnt_a_switch():
    sim = Simulation(Config(**SMALL), log_every=1000)
    z = sim.world.zones
    both = np.argwhere((z[0] >= 0) & (z[1] >= 0))
    cell = tuple(int(v) for v in both[0])
    npc = sim.npcs[0]
    eat_at(sim, npc, 0, cell)
    eat_at(sim, npc, 1, cell)
    eat_at(sim, npc, 0, cell)
    assert len(npc.zones_eaten) == 2 and npc.zone_switches == 0


@pytest.mark.parametrize("lowest,hit", [(1, 1.0), (2, 0.0)])
def test_switches_record_whether_they_reached_the_needed_food(lowest, hit):
    sim = Simulation(Config(**SMALL, food_patch_radius=2.0), log_every=1000)
    npc = sim.npcs[0]
    a = only_in(sim, 0, sim.world.zone_at(0, sim.world.patch_centers[0][0]))
    b = only_in(sim, 1, sim.world.zone_at(1, sim.world.patch_centers[1][0]))
    assert list(sim.world.serves(b)) == [False, True, False]
    eat_at(sim, npc, 0, a)
    npc.pos = b
    sim.world.food_at(b)[:] = 0.0
    sim.world.food_at(b)[1] = 2.0
    npc.nutrients[:] = 0.5
    npc.nutrients[lowest] = 0.1
    sim._eat(npc)
    assert npc.zone_switches == 1
    assert npc.directed_hits == hit and npc.directed_chance == pytest.approx(1 / 3)


@pytest.mark.parametrize("kw", [{}, {"dims": 4, "size": 10, "food_patch_radius": 2.0}])
def test_need_distance_is_zero_at_each_patch_center(kw):
    w = World(Config(**kw), np.random.default_rng(3))
    rich = np.argmax(w.profiles, axis=1)
    for t, centers in enumerate(w.patch_centers):
        for c in centers:
            assert w.need_distance[(rich[t],) + c] == 0.0
    assert np.isfinite(w.need_distance).all()
    assert w.need_distance.max() <= w.cfg.size / 2 * np.sqrt(w.cfg.dims)


@pytest.mark.parametrize("dims,size", [(2, 16), (4, 8)])
def test_moves_toward_the_needed_food_score_positive(dims, size):
    sim = Simulation(Config(**{**SMALL, "dims": dims, "size": size}), log_every=1000)
    w, npc = sim.world, sim.npcs[0]
    npc.nutrients[:] = 0.5
    npc.nutrients[1] = 0.1                            # needs nutrient 1
    cells = np.argwhere(~np.any(w.zones[np.argmax(w.profiles, axis=1) == 1] >= 0, axis=0))
    start = tuple(int(v) for v in cells[0])
    scores = {}
    for axis in range(dims):
        for sign in ("+", "-"):
            npc.pos, npc.approach_sum, npc.approach_null, npc.approach_moves = start, 0.0, 0.0, 0
            sim._act(npc, sim.actions.index(f"move{sign}{axis}"), {}, [])
            delta = w.need_distance[(slice(None),) + npc.pos] - w.need_distance[(slice(None),) + start]
            assert npc.approach_moves == 1
            assert npc.approach_sum == pytest.approx(np.delete(delta, 1).mean() - delta[1])
            scores[(axis, sign)] = npc.approach_sum
    assert max(scores.values()) > 0 > min(scores.values())
    assert npc.approach_null == pytest.approx(np.mean(list(scores.values())))   # the random step


def test_moves_inside_the_needed_food_dont_count():
    sim = Simulation(Config(**SMALL), log_every=1000)
    w, npc = sim.world, sim.npcs[0]
    npc.nutrients[:] = 0.5
    npc.nutrients[0] = 0.1
    npc.pos = tuple(w.patch_centers[0][0])           # food 0 is rich in nutrient 0
    sim._act(npc, sim.actions.index("move+0"), {}, [])
    assert npc.approach_moves == 0


def test_bites_outside_zones_and_from_inventory_dont_count():
    sim = Simulation(Config(**SMALL, zone_core=0.99), log_every=1000)
    npc = sim.npcs[0]
    outside = tuple(int(v) for v in np.argwhere(sim.world.zones[0] < 0)[0])
    eat_at(sim, npc, 0, outside)
    sim.world.food_at(npc.pos)[:] = 0.0
    npc.inventory[:] = 0.5
    sim._eat(npc)
    assert npc.zones_eaten == set() and npc.last_zone is None


def test_completed_lives_feed_the_travel_summary():
    sim = Simulation(Config(**SMALL), log_every=1000)
    npc = sim.npcs[0]
    npc.zones_eaten = {(0, 0), (0, 1), (2, 0)}
    npc.zone_switches = 4
    npc.directed_hits, npc.directed_chance = 3.0, 1.5
    npc.approach_sum, npc.approach_null, npc.approach_moves = 2.0, 0.8, 40
    npc.lifetime = 800
    npc.age = sim.cfg.old_age
    sim._die(npc)
    s = sim.stats.travel_summary()
    assert s["lives"] == 1 and s["zones"] == 3 and s["zone_types"] == 2
    assert s["switch_rate"] == pytest.approx(5.0)
    assert s["directed"] == pytest.approx(0.75) and s["chance"] == pytest.approx(0.375)
    assert s["approach"] == pytest.approx(0.05) and s["approach_null"] == pytest.approx(0.02)
    assert sim.stats.travel_summary(min_lifetime=1000)["lives"] == 0


def test_collapse_keeps_zones_but_teleporting_isnt_a_switch():
    sim = Simulation(Config(**SMALL), log_every=1000)
    npc = sim.npcs[0]
    npc.zones_eaten = {(0, 0)}
    npc.last_zone = (0, 0)
    sim._collapse(npc)
    assert npc.zones_eaten == {(0, 0)} and npc.last_zone is None


@pytest.mark.parametrize("dims,size", [(2, 16), (4, 6)])
def test_zones_survive_a_snapshot_and_runs_resume_identically(tmp_path, dims, size):
    a = Simulation(Config(**{**SMALL, "dims": dims, "size": size}), log_every=1000)
    a.run(150)
    assert any(n.zones_eaten for n in a.npcs)
    b = load_snapshot(save_snapshot(a, tmp_path / "s"), log_every=1000)
    assert np.array_equal(a.world.zones, b.world.zones)
    assert [n.zones_eaten for n in a.npcs] == [n.zones_eaten for n in b.npcs]
    a.run(50)
    b.run(50)
    assert [n.pos for n in a.npcs] == [n.pos for n in b.npcs]
    assert [n.zone_switches for n in a.npcs] == [n.zone_switches for n in b.npcs]
    assert [n.directed_hits for n in a.npcs] == [n.directed_hits for n in b.npcs]
    assert a.total_mass() == pytest.approx(b.total_mass(), rel=1e-12)


def test_snapshots_from_before_zones_still_load(tmp_path):
    a = Simulation(Config(**SMALL), log_every=1000)
    a.run(40)
    path = save_snapshot(a, tmp_path / "old")
    state = json.loads((path / "state.json").read_text())
    state["format"] = 2
    for n in state["npcs"]:
        for k in ("zones_eaten", "last_zone", "zone_switches"):
            del n[k]
    (path / "state.json").write_text(json.dumps(state))
    with np.load(path / "world.npz") as arrays:
        kept = {k: arrays[k] for k in arrays.files if k != "zones"}
    np.savez_compressed(path / "world.npz", **kept)
    b = load_snapshot(path, log_every=1000)
    assert np.array_equal(a.world.zones, b.world.zones)      # rebuilt from the seed
    assert all(n.zones_eaten == set() for n in b.npcs)
