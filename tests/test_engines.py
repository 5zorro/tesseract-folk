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
        "track record": dict(hall_of_fame_track_record=True, hall_of_fame_min_copies=2),
    "smiting": dict(smiting=True, smite_damage=0.2, piety_threshold=0.1),
    "harsh, no scent": dict(food_scent=False, collapse_age_penalty=100, food_growth_rate=0.005),
    "one eat, lineage off": dict(mutation_lineage=False, mutations_per_birth=0.0, two_eat_actions=False),
    "fitness-ranked hall of fame": dict(hall_of_fame_track_record=False),
    "linear brains": dict(hidden_units=0),
    "crossover top-ups": dict(topup_crossover=True, hall_of_fame_min_copies=2),
    "craving sense": dict(craving_sense=True, dims=3, size=6),
    "craving, no scent": dict(craving_sense=True, food_scent=False),
    "mate sense": dict(mate_sense=True),
    "fewer actions": dict(actions_off="pick_up+give+pray+worship+share"),
    "extra stay actions": dict(extra_stay_actions=5),
    "mate sense, 3d": dict(mate_sense=True, dims=3, size=6),
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


# ---------------------------------------------------------------- G3: batches
from sim.simulation import Batch  # noqa: E402

MIXED = [dict(seed=1), dict(seed=2), dict(seed=1, metabolism_rate=0.012, bite_size=0.3),
         dict(seed=3, smiting=True, piety_threshold=0.1, stink_decay=0.05),
         dict(seed=4, hall_of_fame_track_record=True, food_growth_rate=0.01, old_age=200)]


@pytest.mark.parametrize("extra", [{}, dict(dims=4, size=5), dict(two_eat_actions=True, food_scent=False)])
def test_a_batch_matches_its_worlds_run_alone(extra):
    cfgs = [Config(**{**BUSY, **extra, **v}) for v in MIXED]
    alone = [Simulation(c, log_every=50) for c in cfgs]
    together = [Simulation(c, log_every=50) for c in cfgs]
    batch = Batch(together)
    ctrl = ScriptedController()
    for _ in range(300):
        for sims in (alone, together):          # controllers in one world too
            sims[1].overrides = {n.id: ctrl for n in sims[1].npcs if n.id % 3 == 0}
        for sim in alone:
            sim.step()
        batch.step()
    for a, b in zip(alone, together):
        assert_same(snapshot(a), snapshot(b))
        assert a.total_mass() == b.total_mass()


def test_batches_need_matching_shapes_and_ticks():
    a, b = Simulation(Config(**BUSY)), Simulation(Config(**{**BUSY, "dims": 3, "size": 6}))
    with pytest.raises(ValueError, match="dims"):
        Batch([a, b])
    c = Simulation(Config(**{**BUSY, "seed": 99}))
    c.run(3)
    with pytest.raises(ValueError, match="same tick"):
        Batch([a, c])


def test_a_stale_view_cant_read_another_worlds_npc():
    """Ids repeat across a batch's worlds, so a view checks its world too."""
    a, b = Simulation(Config(**BUSY)), Simulation(Config(**{**BUSY, "seed": 12}))
    batch = Batch([a, b])
    gone = a.npcs[-1]
    record = b.pop.record(b.npcs[0]._slot)
    record.id = gone.id                               # same id, other world
    batch.pop.alive[gone._slot] = False
    assert batch.pop.add(record, 1) == gone._slot      # it takes the freed slot
    with pytest.raises(LookupError, match="gone"):
        gone.body


def test_set_rule_changes_one_world_mid_run():
    """A rule changed mid-run (Simulation.set_rule) acts like a world built with it."""
    base = dict(BUSY, seed=5)
    a, b = Simulation(Config(**base), log_every=50), Simulation(Config(**base), log_every=50)
    ref = ReferenceSimulation(Config(**base), log_every=50)
    batch_mates = [Simulation(Config(**dict(base, seed=s)), log_every=50) for s in (6, 7)]
    from sim.simulation import Batch
    Batch([a, *batch_mates])
    for sim in (a, b, ref):
        sim.run(40)
    for sim in (a, b):
        sim.set_rule("nutrient_decay", 0.02)
        sim.set_rule("old_age", 120)
    ref.cfg.nutrient_decay, ref.cfg.old_age = 0.02, 120
    assert batch_mates[0].batch.par["nutrient_decay"][1] == batch_mates[0].cfg.nutrient_decay != 0.02
    for sim in (a, b, ref):
        sim.run(80)
    assert_same(snapshot(ref), snapshot(b))
    assert_same(snapshot(b), snapshot(a))
    with pytest.raises(ValueError):
        a.set_rule("hidden_units", 4)
    with pytest.raises(ValueError):
        a.set_rule("precision", "float32")
