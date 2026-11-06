"""sense_layout names every part of the sense vector, and the sense-only
oracle (SenseController) forages from it alone."""
import numpy as np
import pytest

from sim import Config, Simulation
from sim.controllers import SenseController


@pytest.mark.parametrize("dims", [1, 2, 4])
def test_sense_layout_matches_the_vector(dims):
    cfg = Config(dims=dims, size=40 if dims == 1 else 6, seed=1)
    sim = Simulation(cfg, log_every=10**9)
    L, npc = sim.sense_layout(), sim.npcs[0]
    obs = sim.sense(npc)
    assert max(s.stop for s in L.values()) == obs.size == sim.n_inputs
    assert np.allclose(obs[L["nutrients"]], npc.nutrients)
    assert np.allclose(obs[L["inventory"]], npc.inventory / cfg.carry_capacity)
    assert np.allclose(obs[L["food_here"]], sim.world.food_at(tuple(npc.pos)) / cfg.food_capacity)
    assert obs[L["bias"]][0] == 1.0
    assert L["scent_grad"].stop - L["scent_grad"].start == dims * cfg.n_food_types


def test_sense_oracle_forages_and_conserves_mass():
    sim = Simulation(Config(dims=3, size=8, seed=2), log_every=10**9)
    oracle = SenseController()
    start = sim.total_mass()
    for _ in range(300):
        sim.overrides = {n.id: oracle for n in sim.npcs}
        sim.step()
    assert oracle.decisions > 0 and sim.stats.history is not None
    assert sim.total_mass() == pytest.approx(start, rel=1e-9)
