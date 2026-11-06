"""Only doing nothing counts as idle (5zorro, 2026-11-02)."""
import json

from sim import Config, Simulation
from sim.snapshot import load_snapshot, save_snapshot

SMALL = dict(size=16, initial_npcs=20, min_population=10, two_eat_actions=False)   # uses `eat`


def act(sim, npc, name):
    sim._act(npc, sim.actions.index(name), sim._spatial_index(), [])


def fed_npc(sim):
    npc = sim.npcs[0]
    sim.world.food_at(npc.pos)[:] = 2.0
    npc.idle_streak = 4
    return npc


def test_eating_resets_the_idle_streak():
    sim = Simulation(Config(**SMALL), log_every=1000)
    npc = fed_npc(sim)
    act(sim, npc, "eat")
    assert npc.idle_streak == 0


def test_staying_or_trying_without_effect_is_still_idle():
    sim = Simulation(Config(**SMALL), log_every=1000)
    npc = fed_npc(sim)
    act(sim, npc, "stay")
    assert npc.idle_streak == 5
    act(sim, npc, "pray")                  # ignored prayer: nothing happened
    act(sim, npc, "give")                  # empty hands
    assert npc.idle_streak == 7
    sim.world.food_at(npc.pos)[:] = 0.0
    npc.inventory[:] = 0.0
    act(sim, npc, "eat")                   # nothing to eat
    assert npc.idle_streak == 8


def test_flag_off_keeps_the_old_rule():
    sim = Simulation(Config(**SMALL, busy_resets_idle=False), log_every=1000)
    npc = fed_npc(sim)
    act(sim, npc, "eat")
    assert npc.idle_streak == 5


def test_snapshots_from_before_the_rule_keep_the_old_rule(tmp_path):
    sim = Simulation(Config(**SMALL, busy_resets_idle=False), log_every=1000)
    path = save_snapshot(sim, tmp_path / "old")
    state = json.loads((path / "state.json").read_text())
    del state["config"]["busy_resets_idle"]
    (path / "state.json").write_text(json.dumps(state))
    assert load_snapshot(path).cfg.busy_resets_idle is False


def test_food_grows_only_in_patches_by_default():
    # Patches are Gaussian, so far cells hold a trace; "bare" means under 1% of a bite.
    bare = 0.01 * Config().bite_size
    sim = Simulation(Config(), populate=False)
    assert (sim.world.capacity < bare).any()
    thin = Simulation(Config(food_baseline_fraction=0.05), populate=False)
    assert not (thin.world.capacity < bare).any()
