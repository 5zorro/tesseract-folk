"""Keyed randomness (sim/keyed.py): draws depend only on their key."""
import numpy as np
import pytest

from sim import keyed
from sim.keyed import Keys


def test_same_key_same_numbers_and_each_part_matters():
    k = Keys(7)
    base = k.uniform(3, [5], keyed.MATE)
    assert base == k.uniform(3, [5], keyed.MATE)
    for other in (Keys(8).uniform(3, [5], keyed.MATE), k.uniform(4, [5], keyed.MATE),
                  k.uniform(3, [6], keyed.MATE), k.uniform(3, [5], keyed.GIVE)):
        assert other != base


def test_an_ids_draw_ignores_who_else_draws():
    k = Keys(1)
    alone = k.uniform(9, [42], keyed.ACTION)[0]
    crowd = k.uniform(9, np.arange(100), keyed.ACTION)
    assert crowd[42] == alone
    assert len(np.unique(crowd)) == 100


def test_negative_ids_and_ticks_are_fine():
    k = Keys(0)
    assert k.uniform(0, [-1], keyed.SECRET) != k.uniform(0, [1], keyed.SECRET)


def test_uniforms_look_uniform():
    u = Keys(3).uniform(1, np.arange(200_000), keyed.ORDER)
    assert u.min() >= 0.0 and u.max() < 1.0
    assert abs(u.mean() - 0.5) < 0.005 and abs(u.var() - 1 / 12) < 0.002


def test_a_stream_continues_where_it_stopped():
    one = Keys(2).stream(5, 7, keyed.MUTATE)
    parts = np.concatenate([one.random(3), one.random((2, 2)).ravel()])
    assert np.array_equal(parts, Keys(2).stream(5, 7, keyed.MUTATE).random(7))


def test_stream_shapes_and_ranges():
    s = Keys(4).stream(1, 1, keyed.SPAWN)
    assert isinstance(s.random(), float)
    assert isinstance(s.integers(5), int)
    cells = s.integers(0, 10, 3)
    assert cells.shape == (3,) and cells.dtype == np.int64
    many = s.integers(3, 6, 10_000)
    assert many.min() == 3 and many.max() == 5
    z = s.normal(1.0, 2.0, (50_000,))
    assert abs(z.mean() - 1.0) < 0.05 and abs(z.std() - 2.0) < 0.05
    with pytest.raises(ValueError):
        s.integers(0)
