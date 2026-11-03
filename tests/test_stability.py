"""The stability check behind --until-stable (M1 slice 3).

Uses synthetic stats histories so each rule is tested on its own.
"""
from sim import Config, Simulation


def sim_with_history(pops, births=0, spawns=0, **cfg):
    base = dict(size=16, initial_npcs=20, min_population=10, stable_window=10)
    base.update(cfg)
    sim = Simulation(Config(**base), log_every=1000)
    sim.stats.history = [{"population": p, "births": births, "spawns": spawns} for p in pops]
    return sim


def test_healthy_population_from_real_births_is_stable():
    sim = sim_with_history([40, 41, 39, 40, 42, 40, 39, 41, 40, 40], births=5)
    assert sim.stability_problems() == []
    assert sim.is_stable()


def test_population_held_on_the_floor_by_top_ups_is_not_stable():
    # The old check passed this: zero variation plus a stray birth.
    sim = sim_with_history([10] * 10, births=0, spawns=3)
    sim.stats.history[4]["births"] = 1
    problems = " | ".join(sim.stability_problems())
    assert not sim.is_stable()
    assert "top-up floor" in problems and "too many top-ups" in problems


def test_top_ups_are_allowed_up_to_the_configured_fraction_of_births():
    pops = [40] * 10
    assert sim_with_history(pops, births=2, spawns=0).is_stable()      # 20 births, 0 spawns
    ok = sim_with_history(pops, births=2, spawns=0, stable_max_spawn_fraction=0.1)
    ok.stats.history[0]["spawns"] = 2                                   # 2 <= 0.1 * 20
    assert ok.is_stable()
    ok.stats.history[1]["spawns"] = 1                                   # 3 > 0.1 * 20
    assert not ok.is_stable()


def test_volatile_population_is_not_stable():
    sim = sim_with_history([20, 60] * 5, births=5)
    assert any("varies too much" in p for p in sim.stability_problems())


def test_no_births_is_not_stable():
    sim = sim_with_history([40] * 10, births=0)
    assert "no births" in sim.stability_problems()


def test_too_few_samples_and_extinction_are_reported():
    assert "samples so far" in sim_with_history([40] * 3, births=5).stability_problems()[0]
    assert sim_with_history([0] * 10).stability_problems() == ["population is extinct"]
