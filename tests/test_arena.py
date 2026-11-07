"""scripts/arena.py: the hall-of-fame race on shared scenarios (5zorro, 2026-11-07)."""
import numpy as np
import pytest

import scripts.arena as arena
from sim import Config, Simulation

BASE = dict(dims=2, size=12, food_patch_radius=3.0, hidden_units=4, collapse_age_penalty=0, initial_npcs=6,
            min_population=4)


def fake_play(true_rates):
    """play_scenarios stand-in: brain b scores true_rates[b] + scenario luck shared by all brains."""
    calls = []

    def play(brains, base, seeds, ticks):
        calls.append((list(brains), list(seeds)))
        luck = np.array([10.0 * (s % 7) for s in seeds])      # big, but the same for every brain
        return np.array([[true_rates[b] + l for l in luck] for b in brains])
    return play, calls


def test_shared_luck_cancels_and_the_field_halves(monkeypatch):
    true = [3.0, 1.0, 4.0, 0.5, 2.0, 5.0, 1.5, 2.5]
    play, calls = fake_play(true)
    monkeypatch.setattr(arena, "play_scenarios", play)
    entries = [{"brain": b} for b in range(len(true))]
    records = arena.race(entries, {}, [1, 1, 2], 100, nseed=1, rnd=1)
    assert [len(c[0]) for c in calls] == [8, 4, 2]             # everyone, then halves
    assert [len(c[1]) for c in calls] == [1, 1, 2]
    # Finalists (3, 1), then stage-2 dropouts (6, 4), then stage-1 dropouts, each by true rate.
    assert arena.ranked(records) == [3, 1, 6, 4, 7, 0, 2, 5]
    # Shared luck cancels: excess = true rate minus the field mean, on every scenario.
    field = np.mean(true)
    for i, rec in enumerate(records):
        assert np.allclose(rec["excess"], true[i] - field)


def test_each_stage_uses_new_shared_seeds(monkeypatch):
    play, calls = fake_play([1.0, 2.0, 3.0, 4.0])
    monkeypatch.setattr(arena, "play_scenarios", play)
    arena.race([{"brain": b} for b in range(4)], {}, [2, 2], 100, nseed=7, rnd=3)
    seeds = [s for _, ss in calls for s in ss]
    assert len(set(seeds)) == len(seeds) == 4
    assert seeds[0] == arena.scenario_seed(7, 3, 0)


def test_write_back_keeps_the_best_with_arena_records():
    sim = Simulation(Config(**BASE, seed=0))
    sim.hall_of_fame = [{"id": i, "brain": None, "lives": 9.0, "excess_sum": 9.0, "generation": 0}
                        for i in range(4)]
    records = [{"stage": 1, "excess": [2.0]}, {"stage": 2, "excess": [-1.0, -0.5]},
               {"stage": 2, "excess": [0.5, 0.5]}, {"stage": 1, "excess": [-3.0]}]
    info = arena.write_back(sim, records, keep=3)
    assert info == {"raced": 4, "kept": 3, "best_excess": -0.75}
    assert [e["id"] for e in sim.hall_of_fame] == [1, 2, 3]   # stage reached first, then excess
    assert sim.hall_of_fame[0]["lives"] == 2.0 and sim.hall_of_fame[0]["excess_sum"] == -1.5


def test_real_scenarios_are_clonal_deterministic_and_keep_their_founders():
    sim = Simulation(Config(**BASE, seed=1))
    brains = [sim.npcs[0].brain, sim.npcs[1].brain]
    base = {**BASE, "precision": "float32"}
    a = arena.play_scenarios(brains, base, [11, 12], 150)
    b = arena.play_scenarios(brains, base, [11, 12], 150)
    assert a.shape == (2, 2) and np.isfinite(a).all()
    assert np.array_equal(a, b)                               # same brain, same seed: same score


def test_luck_splits_into_quality_shared_and_leftover():
    rng = np.random.default_rng(0)
    B, S = 400, 40
    quality = rng.normal(0, 1.0, size=(B, 1))         # variance 1
    shared = rng.normal(0, 2.0, size=(1, S))          # variance 4, the same for every brain
    leftover = rng.normal(0, 3.0, size=(B, S))        # variance 9
    c = arena.components(5.0 + quality + shared + leftover)
    assert c["brain"] == pytest.approx(1.0, rel=0.2)
    assert c["scenario"] == pytest.approx(4.0, rel=0.3)
    assert c["leftover"] == pytest.approx(9.0, rel=0.05)
    assert c["r_shared"] == pytest.approx(0.1, abs=0.02)      # 1 / (1 + 9)
    assert c["r_alone"] == pytest.approx(1 / 14, abs=0.02)    # 1 / (1 + 4 + 9)
    assert arena.tests_for(0.5) == pytest.approx(4.0)         # Spearman-Brown: 4 tests -> 0.8
    assert arena.tests_for(0.0) == float("inf")


def test_the_fit_finds_a_known_curve():
    t = np.array([1.0, 2.0, 3.0, 4.0, 5.0]) * 20_000
    y = 2.4 - 0.6 * np.exp(-t / 30_000)
    f = arena.fit(t, y)
    assert f["y_inf"] == pytest.approx(2.4, abs=0.01)
    assert f["tau"] == pytest.approx(30_000, rel=0.05)
    assert not f["edge"]
