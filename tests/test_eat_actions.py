"""Two eat actions (5zorro, M2 slice 3f): eat_most and eat_need, chosen by the brain."""
import numpy as np
import pytest

from sim import Config, Simulation
from sim.controllers import ScriptedController
from sim.npc import build_actions
from sim.nursery import load_brain_pool, seed_brains
from sim.snapshot import save_snapshot

SMALL = dict(size=12, initial_npcs=6, min_population=2, seed=5)


def world(dims=2, **kw):
    sim = Simulation(Config(dims=dims, two_eat_actions=True, **{**SMALL, **kw}), log_every=10**9)
    npc = sim.npcs[0]
    sim.world.food[(slice(None),) + npc.pos] = 0.0
    npc.inventory[:] = 0.0
    return sim, npc


def act(sim, npc, name):
    sim._act(npc, sim.actions.index(name), sim._spatial_index(), [])


@pytest.mark.parametrize("dims", [2, 4])
def test_eat_becomes_two_actions(dims):
    one, two = build_actions(dims), build_actions(dims, True)
    assert "eat" in one and "eat" not in two
    assert two[two.index("eat_most") + 1] == "eat_need"
    assert len(two) == len(one) + 1
    sim, _ = world(dims)
    assert sim.n_outputs == len(two) + sim.cfg.memory_units


def needy_cell(sim, npc):
    """The NPC lacks food type 0's rich nutrient; its cell has a crumb of type 0
    and a full bite of type 1."""
    rich0 = int(sim.world.rich[0])
    npc.nutrients[:] = 0.9
    npc.nutrients[rich0] = 0.2
    here = sim.world.food_at(npc.pos)
    here[0], here[1] = 0.03, 1.0
    return here


def test_eat_need_takes_the_needed_crumb():
    sim, npc = world()
    here = needy_cell(sim, npc)
    act(sim, npc, "eat_need")
    assert here[0] == pytest.approx(0.0) and here[1] == pytest.approx(1.0)


def test_eat_most_takes_the_full_bite():
    sim, npc = world()
    here = needy_cell(sim, npc)
    body = npc.body
    act(sim, npc, "eat_most")
    assert here[0] == pytest.approx(0.03)
    assert here[1] == pytest.approx(1.0 - sim.cfg.bite_size)
    assert npc.body == pytest.approx(body + sim.cfg.bite_size)
    assert sim.stats.window["eats_most"] == 1


def test_both_fall_back_to_the_inventory():
    sim, npc = world()
    npc.inventory[:] = [0.1, 0.5, 0.0]
    act(sim, npc, "eat_most")
    assert npc.inventory[1] == pytest.approx(0.5 - sim.cfg.bite_size)
    rich0 = int(sim.world.rich[0])
    npc.nutrients[:] = 0.9
    npc.nutrients[rich0] = 0.1
    act(sim, npc, "eat_need")
    assert npc.inventory[0] == pytest.approx(0.0)


@pytest.mark.parametrize("name", ["eat_most", "eat_need"])
def test_eating_is_busy_and_nothing_to_eat_is_not(name):
    sim, npc = world()
    npc.idle_streak = 5
    act(sim, npc, name)                              # nothing here, nothing carried
    assert npc.idle_streak == 6
    sim.world.food_at(npc.pos)[2] = 1.0
    act(sim, npc, name)
    assert npc.idle_streak == 0


def test_mass_is_conserved_with_two_eat_actions():
    sim = Simulation(Config(dims=4, size=6, two_eat_actions=True, seed=2), log_every=10**9)
    before = sim.total_mass()
    sim.run(300)
    assert sim.total_mass() == pytest.approx(before, rel=1e-9)
    eats = sum(h.get("eats", 0) for h in sim.stats.history) + sim.stats.window.get("eats", 0)
    split = sum(sum(h.get(k, 0) for h in sim.stats.history) + sim.stats.window.get(k, 0)
                for k in ("eats_most", "eats_need"))
    assert eats == split > 0


def test_one_eat_brains_dont_fit_a_two_eat_world(tmp_path):
    old = Simulation(Config(**SMALL), log_every=10**9)
    save_snapshot(old, tmp_path / "s")
    new = Simulation(Config(two_eat_actions=True, **SMALL), log_every=10**9)
    with pytest.raises(ValueError, match="two_eat_actions"):
        seed_brains(new, load_brain_pool(tmp_path / "s"))


def test_the_scripted_forager_still_eats():
    sim, npc = world()
    npc.nutrients[:] = 0.3
    sim.world.food_at(npc.pos)[1] = 1.0
    choice = ScriptedController().decide(sim, npc, np.zeros(sim.n_inputs))
    assert sim.actions[choice] == "eat_need"
