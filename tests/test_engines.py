"""The array engine (simulation.py) against the per-NPC reference engine
(reference.py): same seed, same rules, so every number must match exactly
(docs/plan-gpu-backend.md, G2). Worlds are small and lives short, so births,
deaths, collapses, top-ups, prayers and shared secrets all happen."""
import numpy as np
import pytest

from sim import Config, Simulation
from sim.controllers import ScriptedController
from sim.nursery import entry_to_dict
from sim.reference import ReferenceSimulation

BUSY = dict(size=12, initial_npcs=30, min_population=24, max_population=60, seed=11,
            adult_age=60, old_age=250, reproduce_min_mass=1.0, mate_cooldown=30,
            secret_interval=10, worship_piety_gain=0.3, prayer_cooldown=5, hidden_units=6)

CASES = {
    "2d": {},
    "4d": dict(dims=4, size=5),
    "1d": dict(dims=1, size=60),
    "two eat": dict(two_eat_actions=True),
    "track record": dict(hall_of_fame_track_record=True, hall_of_fame_min_copies=2),
    "smiting": dict(smiting=True, smite_damage=0.3, piety_threshold=0.1),
    "harsh, no scent": dict(food_scent=False, collapse_age_penalty=100, food_growth_rate=0.005),
    "one eat, lineage off": dict(mutation_lineage=False, mutations_per_birth=0.0),
}


def snapshot(sim) -> dict:
    w = sim.world
    return {
        "tick": sim.tick, "next_id": sim.next_id,
        "npcs": sorted((n.to_dict() for n in sim.npcs), key=lambda d: d["id"]),
        "world": [a.tobytes() for a in (w.food, w.scent, w.stink, w.soil, w.poop)],
        "deity": sim.deity.to_dict(),
        "hall_of_fame": [entry_to_dict(e) for e in sim.hall_of_fame],
        "window": dict(sim.stats.window), "history": sim.stats.history, "lives": sim.stats.lives,
        "gen_lifetime": dict(sim.stats.generation_lifetime),
        "gen_collapses": dict(sim.stats.generation_collapses),
    }


def assert_same(a: dict, b: dict) -> None:
    for key in a:
        if key == "npcs":
            assert [d["id"] for d in a[key]] == [d["id"] for d in b[key]], f"tick {a['tick']}: NPC ids differ"
            for x, y in zip(a[key], b[key]):
                for field in x:
                    assert x[field] == y[field], f"tick {a['tick']}: NPC {x['id']} {field} differs"
        else:
            assert a[key] == b[key], f"tick {a['tick']}: {key} differs"


@pytest.mark.parametrize("case", CASES)
def test_engines_agree_exactly(case):
    cfg = Config(**{**BUSY, **CASES[case]})
    ref, arr = ReferenceSimulation(cfg, log_every=50), Simulation(cfg, log_every=50)
    assert_same(snapshot(ref), snapshot(arr))
    for _ in range(6):
        ref.run(50)
        arr.run(50)
        assert_same(snapshot(ref), snapshot(arr))
    totals = arr.stats.history
    assert sum(h["births"] for h in totals) > 0 and sum(h["deaths"] for h in totals) > 0, \
        "the case should exercise births and deaths"


def test_engines_agree_with_controllers():
    cfg = Config(**BUSY)
    ref, arr = ReferenceSimulation(cfg, log_every=50), Simulation(cfg, log_every=50)
    ctrl = ScriptedController()
    for _ in range(200):
        for sim in (ref, arr):        # every other NPC (by id) on the scripted controller
            sim.overrides = {n.id: ctrl for n in sim.npcs if n.id % 2 == 0}
        ref.step()
        arr.step()
    assert_same(snapshot(ref), snapshot(arr))


def test_slot_layout_doesnt_matter():
    """Reloading everyone in reverse puts NPCs in other slots; nothing may change."""
    cfg = Config(**BUSY)
    a, b = Simulation(cfg, log_every=50), Simulation(cfg, log_every=50)
    for _ in range(10):
        b.npcs = list(reversed(b.npcs))
        a.run(30)
        b.run(30)
    assert_same(snapshot(a), snapshot(b))
    assert not np.array_equal(a.pop.id[a.pop.live()], b.pop.id[b.pop.live()])
