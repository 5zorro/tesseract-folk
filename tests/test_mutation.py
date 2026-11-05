"""Mutations per birth (research slice R1) and diffusion limits."""
import numpy as np
import pytest

from sim import Config, Simulation
from sim.brain import Brain
from sim.world import World


def brain(n_in=47, hidden=16, n_out=15):
    return Brain.random(n_in, hidden, n_out, np.random.default_rng(0))


def test_rate_per_weight_by_default():
    assert brain().mutation_rate(0.1, 0.0) == 0.1


def test_rate_from_mutations_per_birth_scales_with_brain_size():
    small, big = brain(hidden=8), brain(hidden=16)
    assert small.mutation_rate(0.1, 3) == pytest.approx(3 / small.n_params)
    assert big.mutation_rate(0.1, 3) == pytest.approx(3 / big.n_params)
    assert brain(n_in=2, hidden=1, n_out=1).mutation_rate(0.1, 1e6) == 1.0   # capped


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf")])
def test_bad_mutations_per_birth_is_refused(bad):
    with pytest.raises(ValueError, match="mutations_per_birth"):
        brain().mutation_rate(0.1, bad)


def test_children_get_about_that_many_mutations():
    rng = np.random.default_rng(1)
    parent = brain()
    rate = parent.mutation_rate(0.1, 5)
    changed = [sum(int((a != b).sum()) for a, b in zip(parent._arrays(), parent.mutate(rate, 0.3, rng)._arrays()))
               for _ in range(400)]
    assert np.mean(changed) == pytest.approx(5, abs=0.5)


def test_simulation_runs_with_mutations_per_birth():
    sim = Simulation(Config(size=16, initial_npcs=20, min_population=15, mutations_per_birth=2, seed=3),
                     log_every=10**9)
    sim.run(300)
    assert sim.npcs


@pytest.mark.parametrize("field", ["scent_diffusion", "stink_diffusion"])
@pytest.mark.parametrize("bad", [1.5, -0.1, float("nan")])
def test_diffusion_must_be_a_mix(field, bad):
    with pytest.raises(ValueError, match=field):
        World(Config(size=8, **{field: bad}), np.random.default_rng(0))
