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


def test_defaults_are_lineage_adaptive_at_30_per_child():
    cfg = Config()
    assert cfg.mutations_per_birth == 30 and cfg.mutation_lineage


def test_old_snapshots_keep_per_weight_mutation(tmp_path):
    import json
    from sim.snapshot import load_snapshot, save_snapshot
    sim = Simulation(Config(size=8, initial_npcs=5, min_population=2, seed=1), log_every=10**9)
    save_snapshot(sim, tmp_path / "s")
    state = json.loads((tmp_path / "s" / "state.json").read_text())
    for key in ("mutations_per_birth", "mutation_lineage"):    # as saved before 2026-11-04
        del state["config"][key]
    (tmp_path / "s" / "state.json").write_text(json.dumps(state))
    cfg = load_snapshot(tmp_path / "s").cfg
    assert cfg.mutations_per_birth == 0 and not cfg.mutation_lineage


def test_simulation_runs_with_mutations_per_birth():
    sim = Simulation(Config(size=16, initial_npcs=20, min_population=15, mutations_per_birth=2,
                            mutation_lineage=False, seed=3), log_every=10**9)
    sim.run(300)
    assert sim.npcs


@pytest.mark.parametrize("field", ["scent_diffusion", "stink_diffusion"])
@pytest.mark.parametrize("bad", [1.5, -0.1, float("nan")])
def test_diffusion_must_be_a_mix(field, bad):
    with pytest.raises(ValueError, match=field):
        World(Config(size=8, **{field: bad}), np.random.default_rng(0))


# ---- Lineage-adaptive mutation (5zorro, research slice R4)
def lineage_sim(**kw):
    cfg = dict(size=16, initial_npcs=20, min_population=15, seed=3, mutations_per_birth=30,
               mutation_lineage=True)
    sim = Simulation(Config(**{**cfg, **kw}), log_every=10**9)
    for n in sim.npcs:                       # population: 2 collapses per 1,000 ticks
        n.lifetime, n.collapses = 1000, 2
    return sim


def test_lineage_weighs_parents_half_and_their_lineage_half():
    sim = lineage_sim()
    b = sim.npcs[0].brain
    assert sim.mutate_child(b, 2.0, 4.0)[2] == pytest.approx(3.0)
    assert sim.mutate_child(b, 2.0, -1.0)[2] == pytest.approx(2.0)     # unknown lineage: parents only
    assert sim.mutate_child(b, -1.0, 4.0)[2] == -1.0                    # unknown parents: unknown


@pytest.mark.parametrize("lineage,expected", [(2.0, 30), (4.0, 60), (1.0, 15), (0.0, 7.5),
                                              (100.0, 120), (-1.0, 30)])
def test_mutations_follow_lineage_relative_to_population(lineage, expected):
    sim = lineage_sim()
    b = sim.npcs[0].brain
    assert sim.population_collapse_rate() == pytest.approx(2.0)
    assert sim.mutation_rate(b, lineage) * b.n_params == pytest.approx(expected)


def test_lineage_rule_off_ignores_lineage():
    sim = lineage_sim(mutation_lineage=False)
    b = sim.npcs[0].brain
    assert sim.mutation_rate(b, 100.0) * b.n_params == pytest.approx(30)


def test_lineage_rule_needs_a_base_count():
    with pytest.raises(ValueError, match="mutations_per_birth"):
        Simulation(Config(size=8, mutations_per_birth=0, mutation_lineage=True), log_every=10**9)
    with pytest.raises(ValueError, match="mutation_lineage_max"):
        Simulation(Config(size=8, mutations_per_birth=30, mutation_lineage_max=0.5), log_every=10**9)


def test_lineage_runs_and_is_recorded(tmp_path):
    from sim.snapshot import load_snapshot, save_snapshot
    sim = Simulation(Config(size=16, initial_npcs=20, min_population=18, mutations_per_birth=10,
                            mutation_lineage=True, collapse_age_penalty=600, seed=4), log_every=10**9)
    sim.run(1500)
    made = [n for n in sim.npcs if n.origin]
    assert made and all(n.mutations > 0 for n in made)
    assert any(n.lineage >= 0 for n in made)
    if sim.hall_of_fame:
        save_snapshot(sim, tmp_path / "s")
        again = load_snapshot(tmp_path / "s")
        assert [e["lineage"] for e in again.hall_of_fame] == [e["lineage"] for e in sim.hall_of_fame]
        assert [n.lineage for n in again.npcs] == [n.lineage for n in sim.npcs]
