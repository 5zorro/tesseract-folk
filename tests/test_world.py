import numpy as np
import pytest

from sim.config import Config
from sim.world import World, wrapped_delta


@pytest.mark.parametrize("dims,size", [(2, 16), (3, 8), (4, 6)])
def test_environment_conserves_mass_in_any_dimension(dims, size):
    w = World(Config(dims=dims, size=size), np.random.default_rng(0))
    w.poop[(0,) * dims] = 5.0
    start = w.mass()
    for _ in range(200):
        w.step()
    assert w.mass() == pytest.approx(start, rel=1e-9)
    assert (w.soil >= -1e-12).all()


def test_stink_spreads_and_fades():
    w = World(Config(size=16), np.random.default_rng(0))
    w.stink[8, 8] = 10.0
    w.step()
    assert w.stink[8, 9] > 0
    assert w.stink.sum() < 10.0


def test_wrapped_delta_takes_short_way_round():
    assert list(wrapped_delta((0, 0), (15, 1), 16)) == [-1, 1]


def test_each_food_type_has_its_own_patches():
    w = World(Config(size=32), np.random.default_rng(1))
    peaks = [np.unravel_index(np.argmax(w.capacity[t]), w.shape) for t in range(3)]
    assert len(set(peaks)) == 3
