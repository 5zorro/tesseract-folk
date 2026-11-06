"""The anneal nursery's controller (scripts/anneal.py) on a tiny world."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from anneal import DEFAULTS, HUNGER, Anneal  # noqa: E402
from sim import Config, Simulation  # noqa: E402


def test_anneal_runs_both_phases_and_restores_the_rules():
    sim = Simulation(Config(size=10, initial_npcs=20, min_population=10, seed=3), log_every=50)
    normal = {k: getattr(sim.cfg, k) for k in HUNGER + ("adult_age", "old_age")}
    p = dict(DEFAULTS, threshold=25, check=50, settle=1, hold=3, phase1_max=0.5)
    a = Anneal(sim, 2000, p)
    assert sim.cfg.adult_age == 0 and not sim.clock.player_active
    assert sim.batch.par["nutrient_decay"][0] == normal["nutrient_decay"] * p["start_scale"]
    for _ in range(40):
        sim.run(50)
        a.check()
    assert a.phase == 2 and a.phase2_start <= 1000 + 50
    assert sim.clock.player_active and sim.cfg.adult_age == normal["adult_age"]
    assert sim.cfg.old_age == normal["old_age"]                 # the ramp ended at the normal lifespan
    for k in HUNGER:                                              # hunger held where it settled
        assert sim.cfg.__dict__[k] == normal[k] * a.settled
    assert {"tick", "population", "hunger", "diversity"} <= set(a.trace[0])


def test_ramp_only_raises_hunger_to_its_end():
    sim = Simulation(Config(size=10, initial_npcs=20, min_population=10, seed=3), log_every=50)
    p = dict(DEFAULTS, mode="ramp", check=50, ramp_end=1.5, phase1_max=0.5)
    a = Anneal(sim, 2000, p)
    for _ in range(40):
        sim.run(50)
        a.check()
    hunger = [r["hunger"] for r in a.trace]
    assert all(x <= y for x, y in zip(hunger, hunger[1:]))      # never falls
    assert a.phase2_start == 1000 and a.settled == 1.5
