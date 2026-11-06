"""Probe (M2 slice 3e follow-up): is there enough food, in the right places, in each dimension?

For the travel-time-matched worlds (scripts/ladder.py --worlds time) it reports,
from the start and over a scratch run:
- clumps: how many bites (bite_size) each food patch holds at full capacity,
- where the mass sits: soil in cells that can grow a bite of some food vs soil
  stranded in cells that can't (and poop there),
- what NPCs do: share of ground bites taken inside a zone core, pick-ups, and
  bites eaten from inventory.
One-off diagnostic; copy it for the next probe. `--set KEY=VALUE` changes the rules.
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim import Config  # noqa: E402
# This probe hooks per-NPC methods (_decide, _act, _eat...), which only the
# reference engine calls; it gives the same results as the array engine.
from sim.reference import ReferenceSimulation as Simulation  # noqa: E402
from sim.config import parse_overrides  # noqa: E402
from ladder import WORLD_SETS  # noqa: E402

TICKS, SEEDS = 4000, (0, 1, 2)


def probe(job):
    dims, seed, rules = job
    size, radius = WORLD_SETS["time"][dims]
    sim = Simulation(Config(dims=dims, size=size, food_patch_radius=radius, seed=seed, **rules),
                     log_every=1000)
    cfg, w = sim.cfg, sim.world
    grows = (w.capacity >= cfg.bite_size).any(axis=0)          # can grow a bite of something
    # Bites per clump: capacity inside each patch's own cells, at full growth.
    clump = [w.capacity[t][w.zones[t] == i].sum() / cfg.bite_size
             for t in range(cfg.n_food_types) for i in range(cfg.food_patches_per_type)]
    counts = {"ground": 0, "in_core": 0, "inventory": 0, "pickups": 0, "ground_mass": 0.0, "crumbs": 0}
    eat, pick = sim._eat, sim._pick_up

    def eat_counted(npc):
        before_inv, before_body = npc.inventory.sum(), npc.body
        before_zone = npc.zones_eaten.copy(), npc.last_zone, npc.zone_switches
        ok = eat(npc)
        if ok:
            if npc.inventory.sum() < before_inv - 1e-12:
                counts["inventory"] += 1
            else:
                counts["ground"] += 1
                counts["ground_mass"] += npc.body - before_body
                counts["crumbs"] += (npc.body - before_body) < 0.25 * cfg.bite_size
                if npc.last_zone != before_zone[1] or npc.zones_eaten != before_zone[0] \
                        or (npc.last_zone is not None and w.zone_at(npc.last_zone[0], npc.pos) == npc.last_zone[1]):
                    counts["in_core"] += 1
        return ok

    def pick_counted(npc):
        ok = pick(npc)
        counts["pickups"] += ok
        return ok

    sim._eat, sim._pick_up = eat_counted, pick_counted
    snaps = []
    for t in range(TICKS + 1):
        if t % 1000 == 0:
            snaps.append((t, float(w.food.sum()), float(w.soil[grows].sum()), float(w.soil[~grows].sum()),
                          float(w.poop[~grows].sum()), len(sim.npcs)))
        if t < TICKS:
            sim.step()
    return dims, seed, float(grows.mean()), clump, snaps, counts


def main():
    rules = {}
    for i, arg in enumerate(sys.argv):
        if arg == "--set":
            rules.update(parse_overrides(sys.argv[i + 1]))
    jobs = [(d, s, rules) for d in sorted(WORLD_SETS["time"]) for s in SEEDS]
    with ProcessPoolExecutor(max_workers=len(jobs)) as pool:
        results = list(pool.map(probe, jobs))
    for dims in sorted(WORLD_SETS["time"]):
        rs = [r for r in results if r[0] == dims]
        size, radius = WORLD_SETS["time"][dims]
        clumps = np.concatenate([r[3] for r in rs])
        print(f"\n{dims}D (size {size}, radius {radius}): {rs[0][4][0][5]} NPCs, "
              f"{np.mean([r[2] for r in rs]):.0%} of cells can grow a bite")
        print(f"  bites per clump at full growth: median {np.median(clumps):.0f} "
              f"(min {clumps.min():.0f}, max {clumps.max():.0f})")
        print("  tick   food   soil where food grows   soil stranded   poop stranded   pop")
        for i in range(len(rs[0][4])):
            row = np.mean([r[4][i] for r in rs], axis=0)
            print(f"  {row[0]:5.0f} {row[1]:6.0f} {row[2]:14.0f} {row[3]:16.0f} {row[4]:14.0f} {row[5]:6.0f}")
        c = {k: sum(r[5][k] for r in rs) for k in rs[0][5]}
        print(f"  ground bites in a zone core: {c['in_core'] / max(c['ground'], 1):.0%}; "
              f"pick-ups {c['pickups'] / len(rs):.0f} per run; bites from inventory "
              f"{c['inventory'] / max(c['ground'] + c['inventory'], 1):.0%}")
        print(f"  mean ground bite: {c['ground_mass'] / max(c['ground'], 1) / 0.2:.0%} of a full bite; "
              f"crumbs (under a quarter bite): {c['crumbs'] / max(c['ground'], 1):.0%}")


if __name__ == "__main__":
    main()
