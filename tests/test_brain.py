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
