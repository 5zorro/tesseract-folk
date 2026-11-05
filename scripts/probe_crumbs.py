"""Probe (M2 slice 3f): do brains already skip crumbs when a meal is near?

Logs every brain decision with how much food is in the NPC's cell (the most of
any type) and reports how often each kind of brain chooses `eat`, by bucket:
crumb (< a quarter bite), partial (< a full bite), full bite or more. Brains
that learned "skip crumbs, follow the smell" eat crumbs less than scratch does.
One-off diagnostic. `--set KEY=VALUE` runs it under other rules (nurseries
from `scripts/ladder.py --worlds time --hidden 8 --set ...`).
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim import Config, Simulation  # noqa: E402
from sim.config import parse_overrides  # noqa: E402
from sim.nursery import load_brain_pool, seed_brains  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ladder import WORLD_SETS, nursery_path  # noqa: E402

LADDER = Path("snapshots/ladder")

TICKS, SEEDS = 3000, (0, 1)


def cases(rules: tuple) -> list:
    """label, Config kwargs, nursery folder (None = scratch); nurseries from ladder.py."""
    out = [("2D scratch", dict(dims=2, size=32), None)]
    out.append(("2D nursery-8", dict(dims=2, size=32), "snapshots/nursery-8") if not rules else
               ("2D nursery", dict(dims=2, size=32, hidden_units=8),
                str(nursery_path(LADDER, (2, 32, 4.0, 8, rules), 100))))
    for dims in (3, 4):
        size, radius = WORLD_SETS["time"][dims]
        kw = dict(dims=dims, size=size, food_patch_radius=radius, hidden_units=8)
        out += [(f"{dims}D scratch", kw, None),
                (f"{dims}D nursery", kw, str(nursery_path(LADDER, (dims, size, radius, 8, rules), 100)))]
    return [(l, {**kw, **dict(rules)}, n) for l, kw, n in out]


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
    rules = {}
    for i, arg in enumerate(sys.argv):
        if arg == "--set":
            rules.update(parse_overrides(sys.argv[i + 1]))
    CASES = cases(tuple(sorted(rules.items())))
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
