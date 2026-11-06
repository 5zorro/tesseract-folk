import json

import numpy as np

from sim.brain import Brain


def test_forward_shape():
    b = Brain.random(10, 8, 5, np.random.default_rng(0))
    assert b.forward(np.ones(10)).shape == (5,)


def test_json_roundtrip_is_exact():
    rng = np.random.default_rng(0)
    b = Brain.random(10, 8, 5, rng)
    b2 = Brain.from_dict(json.loads(json.dumps(b.to_dict())))
    x = rng.normal(size=10)
    assert np.allclose(b.forward(x), b2.forward(x))


def test_mutation_and_crossover_change_weights():
    rng = np.random.default_rng(0)
    a, b = Brain.random(6, 4, 3, rng), Brain.random(6, 4, 3, rng)
    assert not np.allclose(a.mutate(0.5, 0.5, rng).w1, a.w1)
    child = Brain.crossover(a, b, rng)
    assert ((child.w1 == a.w1) | (child.w1 == b.w1)).all()


def test_zero_hidden_units_is_a_linear_brain():
    """0 hidden units: no hidden layer, w2 maps the inputs straight to the outputs."""
    b = Brain.random(5, 0, 3, np.random.default_rng(0))
    assert b.w1.shape == (0, 5) and b.w2.shape == (3, 5) and b.n_hidden == 0
    assert b.n_params == 3 * 5 + 3
    x = np.arange(5.0)
    assert np.array_equal(b.forward(x), b.w2 @ x + b.b2)
    b.check(5, 0, 3)
    back = Brain.from_dict(json.loads(json.dumps(b.to_dict())))
    assert back.w1.shape == (0, 5)
    back.check(5, 0, 3)
    assert np.array_equal(back.forward(x), b.forward(x))
    rng = np.random.default_rng(1)
    child = Brain.crossover(b, b.mutate(0.5, 0.3, rng), rng)
    child.check(5, 0, 3)
