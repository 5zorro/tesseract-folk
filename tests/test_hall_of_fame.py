"""Hall-of-fame track record (5zorro, plan-m2 research slice R5)."""
import json

import pytest

from sim import Config, Simulation
from sim.nursery import load_brain_pool, seed_brains
from sim.snapshot import load_snapshot, save_snapshot

SMALL = dict(size=16, initial_npcs=20, min_population=15, seed=3, hall_of_fame_track_record=True)


def sim_with_population_rate(rate=2.0, **kw):
    """A world whose living NPCs collapse `rate` times per 1,000 ticks."""
    sim = Simulation(Config(**{**SMALL, **kw}), log_every=10**9)
    for n in sim.npcs:
        n.lifetime, n.collapses = 1000, int(rate)
    return sim


def entry(sim, id, lives, excess_sum, copies=0.0, copy_excess_sum=0.0):
    return {"fitness": 0.0, "generation": 0, "brain": sim.npcs[0].brain, "rate": 0.0,
            "lineage": -1.0, "id": id, "lives": lives, "excess_sum": excess_sum,
            "copies": copies, "copy_excess_sum": copy_excess_sum}


def finished_life(sim, source, collapses, lifetime=1000):
    npc = sim._make_npc(sim.npcs[0].brain, (0, 0), 1.0, 1)
    npc.source, npc.collapses, npc.lifetime = source, collapses, lifetime
    return npc


def test_a_proven_entry_outranks_one_lucky_life():
    sim = sim_with_population_rate()
    lucky = entry(sim, 1, lives=1, excess_sum=-2.0)        # one perfect life
    proven = entry(sim, 2, lives=10, excess_sum=-8.0)      # 0.8 better on average, 10 times
    assert sim._merit(proven) > sim._merit(lucky)
    assert sim._merit(entry(sim, 3, 1, 0.0)) == 0.0         # average is 0


def test_a_copys_life_joins_its_source_entrys_record():
    sim = sim_with_population_rate()
    sim.hall_of_fame = [entry(sim, 999, lives=1, excess_sum=-2.0)]
    sim._record_hall_of_fame(finished_life(sim, 999, collapses=1))   # 1 vs population 2: -1
    src = next(e for e in sim.hall_of_fame if e["id"] == 999)
    assert (src["lives"], src["copies"]) == (2, 1)
    assert src["excess_sum"] == pytest.approx(-3.0)
    assert src["copy_excess_sum"] == pytest.approx(-1.0)


def test_an_entry_whose_copies_do_worse_is_dropped():
    sim = sim_with_population_rate(hall_of_fame_min_copies=3)
    sim.hall_of_fame = [entry(sim, 999, lives=1, excess_sum=-2.0)]
    for _ in range(2):
        sim._record_hall_of_fame(finished_life(sim, 999, collapses=4))   # +2 each
    assert any(e["id"] == 999 for e in sim.hall_of_fame)                  # not judged yet
    sim._record_hall_of_fame(finished_life(sim, 999, collapses=4))
    assert not any(e["id"] == 999 for e in sim.hall_of_fame)
    assert sim.stats.window["hall_of_fame_dropped"] == 1


def test_off_means_no_track_record():
    sim = sim_with_population_rate(hall_of_fame_track_record=False)
    sim.hall_of_fame = [entry(sim, 999, lives=1, excess_sum=-2.0)]
    sim._record_hall_of_fame(finished_life(sim, 999, collapses=1))
    assert next(e for e in sim.hall_of_fame if e["id"] == 999)["lives"] == 1


def test_track_record_survives_a_snapshot_and_old_entries_load(tmp_path):
    sim = sim_with_population_rate()
    sim.hall_of_fame = [entry(sim, 999, lives=4, excess_sum=-3.0, copies=3, copy_excess_sum=-1.0)]
    save_snapshot(sim, tmp_path / "s")
    again = load_snapshot(tmp_path / "s")
    assert {k: v for k, v in again.hall_of_fame[0].items() if k != "brain"} == \
        {k: v for k, v in sim.hall_of_fame[0].items() if k != "brain"}
    state = json.loads((tmp_path / "s" / "state.json").read_text())
    for key in ("id", "lives", "excess_sum", "copies", "copy_excess_sum", "rate", "lineage"):
        del state["hall_of_fame"][0][key]                        # as saved before slice R5
    (tmp_path / "s" / "state.json").write_text(json.dumps(state))
    old = load_snapshot(tmp_path / "s").hall_of_fame[0]
    assert (old["id"], old["lives"], old["excess_sum"], old["copies"]) == (-1, 1.0, 0.0, 0.0)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_a_non_finite_entry_is_refused(tmp_path, bad):
    sim = sim_with_population_rate()
    sim.hall_of_fame = [entry(sim, 999, lives=1, excess_sum=-1.0)]
    save_snapshot(sim, tmp_path / "s")
    text = (tmp_path / "s" / "state.json").read_text().replace('"excess_sum": -1.0',
                                                               f'"excess_sum": {json.dumps(bad)}')
    (tmp_path / "s" / "state.json").write_text(text)
    with pytest.raises(ValueError, match="non-finite"):
        load_snapshot(tmp_path / "s")


def test_seeded_worlds_renumber_entries_and_point_copies_at_them(tmp_path):
    sim = sim_with_population_rate()
    sim.hall_of_fame = [entry(sim, 0, lives=2, excess_sum=-1.0)]   # id 0 clashes with an NPC
    save_snapshot(sim, tmp_path / "s")
    pool = load_brain_pool(tmp_path / "s")
    fresh = Simulation(Config(**SMALL), log_every=10**9)
    seed_brains(fresh, pool)
    npc_ids = {n.id for n in fresh.npcs}
    hof_ids = {e["id"] for e in fresh.hall_of_fame}
    assert not hof_ids & npc_ids
    assert all(n.source in {e["id"] for e in fresh.hall_of_fame} or n.source >= min(hof_ids)
               for n in fresh.npcs)


def test_a_harsh_run_builds_track_records():
    sim = Simulation(Config(size=16, initial_npcs=20, min_population=18, collapse_age_penalty=600,
                            hall_of_fame_track_record=True, seed=4), log_every=10**9)
    sim.run(6000)
    assert any(e["copies"] > 0 for e in sim.hall_of_fame)
