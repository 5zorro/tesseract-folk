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


@pytest.mark.parametrize("scent", [True, False])
def test_craving_is_the_needed_foods_gradient(scent):
    cfg = Config(dims=4, size=6, seed=3, craving_sense=True, food_scent=scent)
    sim = Simulation(cfg, log_every=10**9)
    sim.run(30)
    L = sim.sense_layout()
    assert L["craving"].stop == sim.n_inputs
    for npc in sim.npcs[:10]:
        obs = sim.sense(npc)
        needed = sim.world.rich == int(np.argmin(npc.nutrients))
        grad = obs[L["scent_grad" if scent else "food_grad"]].reshape(cfg.dims, cfg.n_food_types)
        assert np.allclose(obs[L["craving"]], grad[:, needed].sum(axis=1))


def test_mate_sense_reads_eligibility_readiness_and_direction():
    cfg = Config(dims=3, size=8, seed=4, mate_sense=True, initial_npcs=3, min_population=0)
    sim = Simulation(cfg, log_every=10**9)
    a, b, c = sim.npcs
    for n in (a, b, c):
        n.age, n.body, n.health = cfg.adult_age, 1.5, 1.0
    a.pos, b.pos, c.pos = (0, 0, 0), (0, 0, 1), (0, 6, 0)       # b next to a; c 2 steps (wrapped) away
    c.body = 0.5                                                  # c can't mate
    L = sim.sense_layout()
    obs = sim.sense(a)
    assert obs[L["can_mate"]][0] == 1.0
    assert obs[L["partner_ready"]][0] == 0.0                      # b hasn't signaled yet
    assert obs[L["pheromone_here"]][0] == 0.0 and not obs[L["pheromone_grad"]].any()
    b.mate_ready_until = sim.tick + 3
    assert sim.sense(a)[L["partner_ready"]][0] == 1.0
    assert sim.sense(c)[L["can_mate"]][0] == 0.0
    b.mate_ready_until, b.pos = sim.tick + 10, (0, 0, 3)         # b calls from 3 steps up axis 2
    for _ in range(5):
        sim.batch._call()
        sim.batch._world_step()
    obs = sim.sense(a)
    assert obs[L["pheromone_here"]][0] > 0
    assert obs[L["pheromone_grad"]][2] > 0 and abs(obs[L["pheromone_grad"]][0]) < 1e-9
    b.mate_cooldown_until = sim.tick + 50                         # b can't mate now: no call, not ready
    assert sim.sense(a)[L["partner_ready"]][0] == 0.0


@pytest.mark.parametrize("scent", [True, False])
@pytest.mark.parametrize("craving", [True, False])
@pytest.mark.parametrize("mate", [True, False])
def test_both_engines_count_the_same_inputs(scent, craving, mate):
    """The reference keeps its own sensor_size; a new sense must go into both."""
    from sim.reference import ReferenceSimulation
    cfg = Config(dims=3, size=6, seed=1, initial_npcs=2, food_scent=scent, craving_sense=craving,
                 mate_sense=mate)
    ref, arr = ReferenceSimulation(cfg, log_every=10**9), Simulation(cfg, log_every=10**9)
    assert ref.n_inputs == arr.n_inputs == max(s.stop for s in arr.sense_layout().values())
    assert ref.sense(ref.npcs[0], ref._spatial_index()).size == ref.n_inputs


@pytest.mark.parametrize("bad", [dict(scent_half=0.0), dict(pheromone_half=0.0), dict(pheromone_decay=1.5),
                                 dict(stink_decay=-0.1), dict(pheromone_emission=float("nan")),
                                 dict(extra_stay_actions=10**6), dict(actions_off="move+0")])
def test_bad_rules_are_refused(bad):
    with pytest.raises(ValueError):
        Simulation(Config(size=6, initial_npcs=2, **bad), log_every=10**9)
