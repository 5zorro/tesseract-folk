"""Research scripts: reruns reuse finished runs by file name, and a rerun with
other settings must not silently reuse them (review 2026-11-08); the hunger
search's bisection."""
from types import SimpleNamespace

import pytest

import scripts.hunger_search as hunger_search
import scripts.variation_ladder as variation_ladder


def test_hunger_search_names_runs_by_brain_size(monkeypatch):
    monkeypatch.setattr(hunger_search, "HIDDEN", 16)
    default = hunger_search.csv_path(4, 0.5).name
    monkeypatch.setattr(hunger_search, "HIDDEN", 32)
    assert default == "hdist-4d-soil0.1-h0.5.csv"          # 16 units: no size tag; soil since 2026-11-08
    assert hunger_search.csv_path(4, 0.5).name == "hdist-4d-u32-soil0.1-h0.5.csv"
    monkeypatch.setattr(hunger_search, "KEYS", ("metabolism_rate",))
    assert hunger_search.csv_path(4, 0.5).name == "hdist-4d-body-u32-soil0.1-h0.5.csv"


def args(**kw):
    return SimpleNamespace(**{"rounds": 6, "round_ticks": 50_000, "play_every": 2,
                              "nursery_seeds": [100, 101], **kw})


def rows(rounds, seeds, round_ticks=50_000):
    return [{"arm": "plain", "round": r, "nursery": n, "ticks": r * round_ticks} for r in rounds for n in seeds]


def test_variation_cells_refuse_other_settings(tmp_path):
    path = tmp_path / "var-4d-m1.0-h16.csv"
    variation_ladder.check_settings(path, rows([2, 4, 6], [100, 101]), args())
    cases = [(rows([2, 4, 6], [100, 101]), args(rounds=8)),                 # asked for more rounds
             (rows([2, 4, 6], [100]), args()),                              # other nursery seeds
             (rows([2, 4, 6], [100, 101], 20_000), args()),                 # other round length
             (rows([1, 2, 3, 4, 5, 6], [100, 101]), args())]                # other --play-every
    for found, wanted in cases:
        with pytest.raises(SystemExit, match="other settings"):
            variation_ladder.check_settings(path, found, wanted)


def test_variation_cells_name_a_non_default_hunger():
    assert variation_ladder.cell_name(4, 1.0, 16) == "var-4d-m1.0-h16-soil0.1"   # runs before 2026-11-08: no tag
    other = variation_ladder.cell_name(4, 1.0, 16, "nutrient_decay=0.003")
    assert other.startswith("var-4d-m1.0-h16-") and other != variation_ladder.cell_name(4, 1.0, 16)


def test_hunger_search_bisects_between_the_lowest_pass_and_the_fail_below():
    rows = lambda *ls: [{"level": lv, "passes": ok} for lv, ok in ls]  # noqa: E731
    assert hunger_search.next_level(rows((0.5, False), (0.75, True), (1.0, True)), 0.02) == 0.625
    assert hunger_search.next_level(rows((0.5, False), (0.75, False), (1.0, True)), 0.02) == 0.875
    assert hunger_search.next_level(rows((0.5, False), (1.0, False)), 0.02) is None        # nothing passes
    assert hunger_search.next_level(rows((0.75, True), (1.0, True)), 0.02) is None         # no fail below
    assert hunger_search.next_level(rows((0.74, False), (0.75, True)), 0.02) is None       # gap under min_gap


def test_late_population_judges_only_the_late_samples():
    import math
    from scripts.sweep import late_population
    from sim import Config
    cfg = Config(min_population=30, max_population=250)
    hist = [{"tick": t, "population": p, "births": b, "spawns": s}
            for t, p, b, s in [(250, 30, 0, 9), (500, 30, 1, 5), (750, 40, 4, 0), (1000, 250, 6, 0)]]
    out = late_population(hist, 500, cfg)
    assert (out["late_births"], out["late_spawns"]) == (10, 0)
    assert out["pop_mean"] == 145.0 and (out["at_floor"], out["at_cap"]) == (0.0, 0.5)
    assert math.isnan(late_population(hist, 1000, cfg)["pop_mean"])


def test_m3_verdict_needs_births_off_rails_and_steady():
    import scripts.m3_ladder as m3
    a = SimpleNamespace(max_spawn_fraction=0.1, rail_share=0.05, max_cv=0.15)
    good = {"late_births": 100, "late_spawns": 10, "at_floor": 0.0, "at_cap": 0.05, "pop_cv": 0.1}
    assert all(m3.verdict(good, a).values())
    assert not m3.verdict({**good, "late_spawns": 11}, a)["births"]
    assert not m3.verdict({**good, "late_births": 0, "late_spawns": 0}, a)["births"]
    assert not m3.verdict({**good, "at_cap": 0.2}, a)["off rails"]
    assert not m3.verdict({**good, "pop_cv": 0.15}, a)["steady"]


def test_m3_settings_record_overrides_only_when_given():
    import scripts.m3_ladder as m3
    a = SimpleNamespace(seeds=2, ticks=2000, dims=[4], set="", hunger=None)
    assert "set" not in m3.settings(a)                    # older sidecars still match
    assert m3.settings(a)["hunger"] == {"4": 0.36}
    assert m3.settings(a)["physics"] == {"soil_diffusion": 0.1}    # files from before 0.1 don't match
    a.set = "poop_diffusion=0.1"
    assert m3.settings(a)["set"] == {"poop_diffusion": 0.1}
    a.hunger = [0.5, 0.75]
    assert m3.settings(a)["hunger"] == {"4": [0.5, 0.75]} and m3.levels(a, 4) == [0.5, 0.75]


def test_m3_short_labels_keep_nursery_and_round():
    import scripts.m3_ladder as m3
    assert m3.short("snapshots-x") == "snapshots-x"
    assert m3.short("births-cross-n100-r35") == "bc-n100-r35"
    assert m3.short("persist-n100-r35") == "persist-n100-r35"
    assert m3.short("d2-s32-r4-h16-metabolism_rate0.01-nutrient_decay0.003-n100") == "n100"


def test_trace_soil_steps_to_the_nearest_core_wrap_and_cap():
    import numpy as np
    import scripts.trace_soil as tr
    core = np.zeros((10, 10), dtype=bool)
    core[0, 0] = True
    d = tr.steps_to(core)
    assert d[0, 0] == 0 and d[0, 1] == 1 and d[9, 9] == 2          # around the wrap
    assert d.max() == tr.BINS - 1 and d[5, 5] == tr.BINS - 1        # capped


def test_result_names_carry_physics_changed_since_older_runs(monkeypatch):
    """Review 2026-11-09: results made under soil mining were reused by name."""
    import scripts.ladder as ladder
    assert ladder.physics_tag() == "-soil0.1"
    assert hunger_search.csv_path(4, 0.36).name == "hdist-4d-soil0.1-h0.36.csv"
    monkeypatch.setattr(ladder, "PHYSICS", {"soil_diffusion": 0.1})      # as if nothing changed
    assert ladder.physics_tag() == "" and ladder.physics_changes() == {}


def test_probe_memory_holds_memory_at_zero_and_restores():
    import numpy as np
    import scripts.probe_memory as probe
    from sim import Config, Simulation
    from sim.simulation import Batch
    original = Batch.decide_all
    sim = Simulation(Config(dims=2, size=12, seed=3, initial_npcs=6))
    with probe.memory_held_at_zero():
        for _ in range(3):
            sim.step()
        assert sim.npcs and np.all(sim.pop.memory[sim.pop.live()] == 0)
    assert Batch.decide_all is original
    sim.step()
    assert np.any(sim.pop.memory[sim.pop.live()] != 0)          # trained feedback is back


def test_probe_memory_sensitivity_is_zero_for_an_ignored_sense():
    import numpy as np
    import scripts.probe_memory as probe
    from sim import Config, Simulation
    sim = Simulation(Config(dims=2, size=12, seed=4, initial_npcs=8))
    layout, P = sim.sense_layout(), sim.pop
    live = P.live()
    P.w1[live, :, layout["memory"]] = 0.0                     # nobody reads memory
    obs = sim.batch.sense_slots(live)
    got = probe.sensitivity(sim.batch, live, obs, layout, np.random.default_rng(0))
    assert got["memory"] == 0.0 and "bias" not in got
    assert max(got.values()) > 0
    assert np.allclose(probe.action_probs(sim.batch, live, obs).sum(axis=1), 1.0)


def test_probe_memory_lag_correlation():
    import math
    import numpy as np
    import scripts.probe_memory as probe
    a = np.arange(10.0)
    assert probe.lag_correlation([(a, a * 2)]) == pytest.approx(1.0)
    assert math.isnan(probe.lag_correlation([]))


def test_probe_memory_state_tells_a_fixed_bias_from_a_held_state():
    import numpy as np
    import scripts.probe_memory as probe
    fixed = [np.full((40, 2), v) for v in (-0.9, 0.1, 0.8)]   # one value per NPC
    got = probe.memory_state(fixed)
    assert got["within"] < 1e-9 and got["between"] > 0.5
    walk = [np.cumsum(np.random.default_rng(s).normal(0, 0.1, (40, 2)), axis=0) for s in range(5)]
    held = probe.memory_state(walk)
    assert held["within"] > 0 and held["lag1"] > 0.5


def test_probe_memory_follows_npcs_by_world_and_id():
    """Ids repeat across a batch's worlds; following by id alone interleaved
    worlds and faked a 2-tick clock (MR0, 2026-11-10)."""
    import scripts.probe_memory as probe
    from sim import Config, Simulation
    from sim.simulation import Batch
    sims = [Simulation(Config(dims=2, size=12, seed=s, initial_npcs=5)) for s in (1, 2)]
    batch = Batch(sims)
    P, live = batch.pop, batch.pop.live()
    keys = probe.npc_keys(P, live)
    assert len(set(keys)) == len(keys) == 10 and len({k[1] for k in keys}) == 5   # ids repeat
    follow = {k: [] for k in keys}
    for _ in range(4):
        batch.step()
        probe.record(follow, batch.pop, batch.pop.live())
    assert all(len(v) <= 4 for v in follow.values()) and max(len(v) for v in follow.values()) == 4


def test_mr1_ladder_trains_under_nursery_rules_and_refuses_other_runs(tmp_path):
    import json
    import scripts.mr1_ladder as mr1
    from scripts.ladder import NURSERY_RULES
    rules = mr1.nursery_rules(4, 3, 101, {})
    assert rules["reaction_queue"] == 3 and rules["seed"] == 101
    assert all(rules[k] == v for k, v in NURSERY_RULES.items())
    path = mr1.trained_path(tmp_path, "snapshots/x/persist-n101-r35", 3, 500)
    assert path.name.startswith("persist-n101-r35-q3-t500")
    assert not mr1.reusable(path, rules, "src", 500)               # nothing there yet
    path.mkdir()
    (path / "state.json").write_text(json.dumps({"config": rules, "tick": 500}))
    (path / "mr1.json").write_text(json.dumps({"source": "src"}))
    assert mr1.reusable(path, rules, "src", 500)
    with pytest.raises(ValueError):
        mr1.reusable(path, rules, "other source", 500)
    with pytest.raises(ValueError):
        mr1.reusable(path, {**rules, "reaction_queue": 1}, "src", 500)
