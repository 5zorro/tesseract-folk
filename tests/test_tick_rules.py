"""The G1 tick rules (docs/plan-gpu-backend.md): decide together from the
start-of-tick world, resolve in phases by priority, keyed randomness."""
import numpy as np
import pytest

from sim import Config, Simulation, keyed

SMALL = dict(size=12, initial_npcs=12, min_population=10, seed=4)


class Fixed:
    """A controller that always picks one action and records what it saw."""

    def __init__(self, action: int, seen: list):
        self.action, self.seen = action, seen

    def decide(self, sim, npc, obs):
        self.seen.append((sim.tick, float(sim.world.food.sum())))
        return self.action


def test_everyone_decides_from_the_same_world():
    sim = Simulation(Config(**SMALL), log_every=10**9)
    seen: list = []
    eat = sim.actions.index("eat")
    for npc in sim.npcs:
        sim.overrides[npc.id] = Fixed(eat, seen)
    sim.run(5)
    for tick in range(1, 6):
        food = {f for t, f in seen if t == tick}
        assert len(food) == 1, "an NPC decided after another one's bite"


def test_eaters_on_one_cell_go_in_priority_order():
    sim = Simulation(Config(**{**SMALL, "initial_npcs": 2, "min_population": 0},
                            food_growth_rate=0.0, food_scent=False), log_every=10**9)
    a, b = sim.npcs
    b.pos = a.pos
    for npc in (a, b):
        npc.inventory[:] = 0.0
        sim.overrides[npc.id] = Fixed(sim.actions.index("eat"), [])
    here = sim.world.food_at(a.pos)
    here[:] = 0.0
    here[0] = sim.cfg.bite_size                    # one bite for two eaters
    prio = sim.keys.uniform(sim.tick + 1, [a.id, b.id], keyed.ORDER)
    first, second = (a, b) if prio[0] < prio[1] else (b, a)
    sim.step()
    assert first.eaten[0] == pytest.approx(sim.cfg.bite_size)
    assert second.eaten[0] == 0.0


def state(sim):
    return sorted((n.id, n.pos, n.body, n.health, n.age, *n.nutrients, *n.memory) for n in sim.npcs)


def test_results_dont_depend_on_list_order():
    """Arrays (G2) won't keep Python's list order, so nothing may depend on it."""
    # min_population above the start forces top-ups (their candidate picks) at once.
    cfg = Config(**{**SMALL, "initial_npcs": 30, "min_population": 34}, collapse_age_penalty=600)
    a, b = Simulation(cfg, log_every=10**9), Simulation(cfg, log_every=10**9)
    for _ in range(200):
        b.npcs.reverse()
        a.step()
        b.step()
    assert state(a) == state(b)
    assert a.stats.window == b.stats.window
    assert a.stats.history == b.stats.history
    assert a.next_id == b.next_id > 30            # births or top-ups happened


@pytest.mark.parametrize("dims", [2, 4])
def test_same_seed_same_run(dims):
    kw = dict(SMALL, dims=dims, size=12 if dims == 2 else 5)
    a, b = Simulation(Config(**kw), log_every=10**9), Simulation(Config(**kw), log_every=10**9)
    a.run(80)
    b.run(80)
    assert state(a) == state(b)
    assert np.array_equal(a.world.food, b.world.food)
