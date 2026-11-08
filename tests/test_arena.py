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


def test_persist_marks_kept_entries_raced_and_adds_up_their_races():
    sim = Simulation(Config(**BASE, seed=0))
    sim.hall_of_fame = [{"id": 0, "brain": None, "lives": 4.0, "excess_sum": -2.0, "generation": 0, "raced": 1.0},
                        {"id": 1, "brain": None, "lives": 9.0, "excess_sum": 9.0, "generation": 0}]
    records = [{"stage": 2, "excess": [-1.0, -1.0]}, {"stage": 1, "excess": [0.5]}]
    arena.write_back(sim, records, keep=2, persist=True)
    first, second = sim.hall_of_fame
    assert first["raced"] == second["raced"] == 1.0
    assert (first["lives"], first["excess_sum"]) == (6.0, -4.0)      # raced before: this race adds on
    assert (second["lives"], second["excess_sum"]) == (1.0, 0.5)     # new to the race: its record
    arena.write_back(sim, records, keep=2)                            # the arena arm: unchanged rules
    assert "raced" in sim.hall_of_fame[0] and sim.hall_of_fame[0]["lives"] == 2.0


def test_resume_refuses_other_rules_than_the_checkpoint():
    """Review 2026-11-08: --start-round used to ignore a changed --hidden or --breed."""
    sim = Simulation(Config(**BASE, seed=0))
    rate = sim.cfg.metabolism_rate
    arena.check_resume(sim, {"dims": 2, "hidden": 4, "breed": {"metabolism_rate": rate * 1.0}})
    for args in ({"dims": 2, "hidden": 8, "breed": {}}, {"dims": 3, "hidden": 4, "breed": {}},
                 {"dims": 2, "hidden": 4, "breed": {"metabolism_rate": rate * 2}}):
        with pytest.raises(ValueError, match="other rules"):
            arena.check_resume(sim, args)


def test_the_luck_report_reads_every_racing_arm(tmp_path):
    """Review 2026-11-08: persist's race logs were left out of the luck report."""
    import json
    log = {"entries": [{"merit": m} for m in (1.0, 0.0, -1.0)],
           "grids": [{"players": [0, 1, 2], "raw": [[1.0, 2.0], [2.0, 3.5], [3.0, 4.0]]}]}
    for folder, name in (("arena-n1-r2", "race.json"), ("persist-n1-r2", "race.json"),
                         ("plain-n1-r2", "measure.json")):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / name).write_text(json.dumps(log))
    assert sorted(r["kind"] for r in arena.luck_rows(tmp_path)) == ["arena", "persist", "untested"]


def test_births_arms_score_collapses_minus_weighted_births(monkeypatch):
    """plan-m3 S3: collapses at the test rules, births at the birth-test rules."""
    seen = []

    def play(brains, base, seeds, ticks, births=False):
        seen.append((base["tag"], births))
        return np.full((len(brains), len(seeds)), 0.2 if births else 1.0)
    monkeypatch.setattr(arena, "play_scenarios", play)
    assert arena.scorer("persist", {"tag": "t"}, {"tag": "b"}, 100, 5.0) is None
    score = arena.scorer("births", {"tag": "t"}, {"tag": "b"}, 100, 5.0)
    assert np.allclose(score(["x", "y"], [1, 2, 3]), 1.0 - 5.0 * 0.2)
    assert seen == [("t", False), ("b", True)]


def test_crosses_are_unmutated_fresh_entries_of_two_parents():
    sim = Simulation(Config(**BASE, seed=0))
    parents = [{"id": k, "brain": sim.npcs[k].brain, "generation": k, "lives": 8.0, "excess_sum": -1.0,
                "raced": 1.0, "rate": 0.5, "fitness": 3.0} for k in range(3)]
    first_id = sim.next_id
    kids = arena.crosses(sim, parents, 6, nseed=100, rnd=2)
    assert [k["id"] for k in kids] == list(range(first_id, first_id + 6)) and sim.next_id == first_id + 6
    flat = lambda b: np.concatenate([x.ravel() for x in b._arrays()])        # noqa: E731
    pool = [flat(p["brain"]) for p in parents]
    for kid in kids:
        w = flat(kid["brain"])
        from_parent = np.array([np.isclose(w, p) for p in pool])            # each weight is some parent's
        assert from_parent.any(axis=0).all()
        assert "raced" not in kid and kid["lives"] == 0.0 and kid["excess_sum"] == 0.0
        assert kid["generation"] >= 1
    again = arena.crosses(Simulation(Config(**BASE, seed=0)), parents, 6, nseed=100, rnd=2)
    assert all(np.array_equal(flat(a["brain"]), flat(b["brain"])) for a, b in zip(kids, again))


def test_scenarios_count_births_per_founder_tick():
    base = {**BASE, "initial_npcs": 6}
    brain = Simulation(Config(**BASE, seed=0)).npcs[0].brain
    births = arena.play_scenarios([brain], base, [7, 8], 400, births=True)
    assert births.shape == (1, 2) and (births >= 0).all()
    assert np.array_equal(births, arena.play_scenarios([brain], base, [7, 8], 400, births=True))


@pytest.mark.parametrize("arm", ["births", "cross", "births-cross"])
def test_s3_arms_run_a_round_and_keep_raced_entries(arm, tmp_path, monkeypatch):
    monkeypatch.setattr(arena, "world", lambda shape: dict(BASE))
    args = {"dims": 2, "hidden": 4, "breed": {"old_age": 150}, "test": {}, "birth_test": {}, "birth_weight": 5.0,
            "rounds": 1, "round_ticks": 800, "stages": [1, 1], "keep": 2, "test_ticks": 200,
            "out": str(tmp_path), "start_round": 0}
    msgs = arena.nursery((arm, 100, args))
    sim = arena.load_snapshot(arena.checkpoint(tmp_path, arm, 100, 1))
    assert len(sim.hall_of_fame) == 2 and all(e.get("raced") == 1.0 for e in sim.hall_of_fame)
    assert ("crosses kept" in msgs[0]) == (arm in arena.CROSS)


def test_nursery_seeds_that_would_share_scenarios_are_refused():
    """Review 2026-11-08: seeds 5 or 10 apart repeat each other's scenario seeds."""
    assert not arena.seed_clash([100, 101, 102, 103])
    assert arena.seed_clash([100, 105]) and arena.seed_clash([100, 110])
    clash = [arena.scenario_seed(100, r + arena.CROSS_SALT, 0) for r in range(1, 36)]
    assert set(clash) & {arena.scenario_seed(105, r, 0) for r in range(1, 36)}      # why it's refused
