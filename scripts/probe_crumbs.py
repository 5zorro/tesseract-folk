"""Probe (M2 slice 3f): do brains already skip crumbs when a meal is near?

Logs every brain decision with how much food is in the NPC's cell (the most of
any type) and reports how often each kind of brain chooses `eat`, by bucket:
crumb (< a quarter bite), partial (< a full bite), full bite or more. Brains
that learned "skip crumbs, follow the smell" eat crumbs less than scratch does.
One-off diagnostic.
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim import Config, Simulation  # noqa: E402
from sim.nursery import load_brain_pool, seed_brains  # noqa: E402

TICKS, SEEDS = 3000, (0, 1)
CASES = [  # label, world, nursery (None = scratch)
    ("2D scratch", dict(dims=2, size=32), None),
    ("2D nursery-8", dict(dims=2, size=32), "snapshots/nursery-8"),
    ("3D scratch", dict(dims=3, size=14, food_patch_radius=1.88, hidden_units=8), None),
    ("3D nursery", dict(dims=3, size=14, food_patch_radius=1.88, hidden_units=8),
     "snapshots/ladder/d3-s14-r1.88-h8-n100"),
    ("4D scratch", dict(dims=4, size=10, food_patch_radius=1.23, hidden_units=8), None),
    ("4D nursery", dict(dims=4, size=10, food_patch_radius=1.23, hidden_units=8),
     "snapshots/ladder/d4-s10-r1.23-h8-n100"),
]
BUCKETS = ("crumb", "partial", "full")


def probe(job):
    label, kw, nursery, seed = job
    sim = Simulation(Config(**kw, seed=seed), log_every=1000)
    if nursery:
        seed_brains(sim, load_brain_pool(nursery))
    eat = sim.actions.index("eat")
    bite = sim.cfg.bite_size
    seen = {b: 0 for b in BUCKETS}
    ate = {b: 0 for b in BUCKETS}
    decide = sim._decide

    def logged(npc, obs, *rest):
        action = decide(npc, obs, *rest)
        most = float(sim.world.food_at(npc.pos).max())
        b = "crumb" if most < 0.25 * bite else "partial" if most < bite else "full"
        seen[b] += 1
        ate[b] += action == eat
        return action

    sim._decide = logged
    sim.run(TICKS)
    return label, seen, ate


def main():
    jobs = [(l, kw, n, s) for l, kw, n in CASES for s in SEEDS]
    with ProcessPoolExecutor(max_workers=len(jobs)) as pool:
        results = list(pool.map(probe, jobs))
    print("Share of decisions that choose `eat`, by food in the NPC's cell (and share of time there)")
    print(f"{'':14} " + "  ".join(f"{b:>18}" for b in BUCKETS))
    for label, _, _ in CASES:
        rs = [r for r in results if r[0] == label]
        seen = {b: sum(r[1][b] for r in rs) for b in BUCKETS}
        ate = {b: sum(r[2][b] for r in rs) for b in BUCKETS}
        total = sum(seen.values())
        print(f"{label:14} " + "  ".join(
            f"{ate[b] / max(seen[b], 1):6.0%} eat ({seen[b] / total:4.0%})" for b in BUCKETS))


if __name__ == "__main__":
    main()
