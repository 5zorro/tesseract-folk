"""StillController: the never-moves sanity probe (sweep controller=still, 5zorro 2026-11-07)."""
import numpy as np
import pytest

from sim import Config, Simulation
from sim.controllers import StillController


@pytest.mark.parametrize("two_eat", [False, True])
def test_the_still_controller_never_moves(two_eat):
    sim = Simulation(Config(size=12, initial_npcs=4, min_population=2, seed=1, two_eat_actions=two_eat),
                     log_every=10**9)
    npc, still = sim.npcs[0], StillController()
    obs = np.zeros(sim.n_inputs)
    pick = lambda: sim.actions[still.decide(sim, npc, obs)]          # noqa: E731
    npc.bowel = sim.cfg.bowel_capacity
    assert pick() == "poop"                                          # full: poop first
    npc.bowel = 0.0
    sim.world.food_at(npc.pos)[:] = 0.0
    assert pick() == "stay"                                          # nothing here: wait
    npc.nutrients[:] = 1.0
    npc.nutrients[0] = 0.1
    sim.world.food_at(npc.pos)[int(np.argmax(sim.world.rich == 0))] = 1.0
    assert pick() == ("eat_need" if two_eat else "eat")              # the needed food is here
    if two_eat:
        sim.world.food_at(npc.pos)[:] = 0.0
        sim.world.food_at(npc.pos)[int(np.argmax(sim.world.rich != 0))] = 1.0
        assert pick() == "eat_most"                                  # only other food: biggest bite

