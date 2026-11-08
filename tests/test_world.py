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


# ---- Poop and soil diffusion (plan-m3 slice S3b)
from sim.world import diffuse_mass  # noqa: E402


@pytest.mark.parametrize("dims,size", [(1, 7), (2, 9), (3, 6), (4, 5), (4, 2)])
def test_diffuse_mass_conserves_and_stays_positive(dims, size):
    field = np.random.default_rng(1).random((size,) * dims) ** 4
    start = float(np.sum(field, dtype=np.float64))
    for _ in range(50):
        diffuse_mass(field, 1.0, dims, 0)
    assert float(field.sum()) == pytest.approx(start, rel=1e-12)
    assert (field >= 0).all()


def test_diffuse_mass_matches_the_neighbor_mix_to_first_order():
    """A small rate moves what stink's x += rate * (mean - x) would (the passes
    differ only at second order in the rate)."""
    dims, rate = 4, 1e-4
    w = World(Config(dims=dims, size=5), np.random.default_rng(0))
    field = np.random.default_rng(2).random(w.shape)
    mixed = field + rate * (w._neighbor_mean(field) - field)
    diffuse_mass(field, rate, dims, 0)
    change = mixed - field
    assert np.abs(change).max() < 1e-3 * rate


def test_diffuse_mass_flattens_a_peak_and_wraps():
    field = np.zeros((6, 6))
    field[0, 0] = 1.0
    for _ in range(400):
        diffuse_mass(field, 0.5, 2, 0)
    assert field.sum() == pytest.approx(1.0, rel=1e-12)
    assert field[5, 5] > 0 and np.ptp(field) < 1e-3       # across the wrap, then even


def test_diffuse_mass_takes_per_world_rates():
    """Batch form: a leading world axis with a rate per world; rate 0 changes nothing."""
    rng = np.random.default_rng(3)
    stacked = rng.random((2, 5, 5, 5, 5))
    alone = stacked[1].copy()
    untouched = stacked[0].copy()
    diffuse_mass(stacked, np.array([0.0, 0.4]).reshape(2, 1, 1, 1, 1), 4, 1)
    diffuse_mass(alone, 0.4, 4, 0)
    assert stacked[0].tobytes() == untouched.tobytes()
    assert stacked[1].tobytes() == alone.tobytes()


@pytest.mark.parametrize("dims,size", [(2, 16), (4, 6)])
def test_poop_and_soil_diffusion_conserve_world_mass(dims, size):
    w = World(Config(dims=dims, size=size, poop_diffusion=0.5, soil_diffusion=0.5), np.random.default_rng(0))
    w.poop[(0,) * dims] = 5.0
    w.soil[(1,) * dims] = 0.0
    start = w.mass()
    for _ in range(200):
        w.step()
    assert w.mass() == pytest.approx(start, rel=1e-12)
    assert (w.soil >= 0).all() and (w.poop >= 0).all()
    assert w.poop[(2,) * dims] > 0                      # poop moved off its cell


def test_soil_diffusion_refills_a_mined_cell():
    on, off = (World(Config(size=16, soil_diffusion=r, food_growth_rate=0.0), np.random.default_rng(0))
               for r in (0.3, 0.0))
    for w in (on, off):
        w.soil[8, 8] = 0.0
        for _ in range(50):
            w.step()
    assert off.soil[8, 8] == 0.0 and on.soil[8, 8] > 0.9
