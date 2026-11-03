"""The nursery: fresh worlds started from a snapshot's best brains (M1 slice 4b)."""
import numpy as np
import pytest

from scripts.sweep import parse_overrides, run_one
from sim import Config, Simulation
from sim.config import parse_overrides as config_overrides
from sim.nursery import load_brain_pool, seed_brains
from sim.snapshot import save_snapshot

SMALL = dict(size=16, initial_npcs=20, min_population=10, hall_of_fame_size=5)


@pytest.fixture
def trained(tmp_path):
    """A small 'nursery' run under harsh rules, saved as a snapshot."""
    sim = Simulation(Config(**SMALL, collapse_age_penalty=600), log_every=1000)
    sim.run(300)
    return save_snapshot(sim, tmp_path / "nursery")


def same(a, b):
    return all(np.array_equal(x, y) for x, y in zip(a._arrays(), b._arrays()))


def test_pool_holds_hall_of_fame_and_living_npcs_best_first(trained):
    pool = load_brain_pool(trained)
    assert len(pool) > 0
    fitness = [e["fitness"] for e in pool]
    assert fitness == sorted(fitness, reverse=True)


def test_fresh_world_starts_with_the_pool_brains_best_first(trained):
    pool = load_brain_pool(trained)
    sim = Simulation(Config(**SMALL, seed=9), log_every=1000)
    mass = sim.total_mass()
    seed_brains(sim, pool)
    n = min(len(pool), len(sim.npcs))
    for npc, entry in zip(sim.npcs[:n], pool[:n]):
        assert same(npc.brain, entry["brain"])
        assert npc.generation == entry["generation"]
    assert [e["fitness"] for e in sim.hall_of_fame] == [e["fitness"] for e in pool[:5]]
    assert sim.total_mass() == mass                     # brains only, never mass


def test_npcs_beyond_the_pool_get_mutated_copies(trained):
    pool = load_brain_pool(trained)[:3]
    sim = Simulation(Config(**SMALL), log_every=1000)
    seed_brains(sim, pool)
    assert same(sim.npcs[0].brain, pool[0]["brain"])
    assert not same(sim.npcs[3].brain, pool[0]["brain"])   # a mutated copy of the best


def test_seeded_worlds_are_deterministic(trained):
    def run():
        sim = Simulation(Config(**SMALL, seed=4), log_every=1000)
        seed_brains(sim, load_brain_pool(trained))
        sim.run(80)
        return [n.pos for n in sim.npcs], sim.total_mass()
    assert run() == run()


def test_mismatched_brain_shapes_fail_clearly(trained):
    sim = Simulation(Config(**{**SMALL, "dims": 4, "size": 6}), log_every=1000)
    with pytest.raises(ValueError, match="doesn't fit"):
        seed_brains(sim, load_brain_pool(trained))
    with pytest.raises(ValueError, match="empty"):
        seed_brains(sim, [])


def test_tampered_brains_are_refused(trained):
    import json
    from sim.snapshot import load_snapshot
    state_file = trained / "state.json"
    state = json.loads(state_file.read_text())
    state["npcs"][0]["brain"]["w1"][0][0] = float("nan")       # JSON writes this as NaN
    state_file.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="NaN"):
        load_snapshot(trained)
    sim = Simulation(Config(**SMALL), log_every=1000)
    with pytest.raises(ValueError, match="doesn't fit"):
        seed_brains(sim, load_brain_pool(trained))

    state["npcs"][0]["brain"]["w1"][0][0] = 0.0
    state["npcs"][0]["brain"]["b1"] = state["npcs"][0]["brain"]["b1"][:-1]   # one bias short
    state_file.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="b1"):
        load_snapshot(trained)


def test_sweep_can_start_worlds_from_a_pool(trained):
    out = run_one({**SMALL, "brains_from": str(trained)}, seed=1, ticks=100,
                  late_from=0.5, log_every=50)
    assert out["population"] > 0
    assert parse_overrides(f"brains_from={trained},collapse_age_penalty=600") == {
        "brains_from": str(trained), "collapse_age_penalty": 600}


def test_config_overrides_reject_pseudo_keys():
    with pytest.raises(ValueError):
        config_overrides("brains_from=somewhere")          # sweep-only, not a Config field
