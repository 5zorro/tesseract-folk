"""Probe (M2 slice 3g): with two eat actions, do brains choose by situation?

Seeds play worlds from two-eat nurseries (scripts/ladder.py --set
two_eat_actions=true) and logs every decision by what is in the NPC's cell:
crumbs only; a full bite of the food it needs most; a crumb of the needed food
beside a full bite of another; only other food. If brains chose by situation,
eat_most would rise where only another food offers a full bite. 2026-11-05:
the shares were flat in every situation (a fixed habit per dimension).

    python scripts/probe_eat_choice.py --ladder snapshots/ladder2
    python scripts/probe_eat_choice.py --set scent_min_food=0.2   # nurseries trained with these rules too
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim import Config, Simulation  # noqa: E402
from sim.config import parse_overrides  # noqa: E402
from sim.nursery import load_brain_pool, seed_brains  # noqa: E402
from ladder import WORLD_SETS, nursery_path  # noqa: E402

TICKS = 2000


def situation(sim, npc) -> str:
    here = sim.world.food_at(npc.pos)
    bite = sim.cfg.bite_size
    need = int(np.argmin(npc.nutrients))
    need_food = here[sim.world.rich == need].max()
    if here.max() < 0.25 * bite:
        return "crumbs only"
    if need_food >= bite:
        return "full bite of the needed food"
    if need_food > 1e-9:
        return "needed food a crumb, another a full bite"
    return "only other food"


def run(job: tuple) -> tuple[int, dict]:
    dims, nseed, seed, ladder, rules = job
    size, radius = WORLD_SETS["time"][dims]
    rules = {**rules, "two_eat_actions": True}
    sim = Simulation(Config(dims=dims, size=size, food_patch_radius=radius, hidden_units=8,
                            seed=seed, **rules), log_every=10**9)
    shape = (dims, size, radius, 8, tuple(sorted(rules.items())))
    seed_brains(sim, load_brain_pool(nursery_path(Path(ladder), shape, nseed)))
    most, need = sim.actions.index("eat_most"), sim.actions.index("eat_need")
    counts: dict = {}
    decide = sim._decide

    def logged(npc, obs, *rest):
        action = decide(npc, obs, *rest)
        c = counts.setdefault(situation(sim, npc), [0, 0, 0])
        c[0] += 1
        c[1] += action == most
        c[2] += action == need
        return action

    sim._decide = logged
    sim.run(TICKS)
    return dims, counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ladder", default="snapshots/ladder2")
    ap.add_argument("--dims", type=int, nargs="+", default=[2, 3, 4])
    ap.add_argument("--nursery-seeds", type=int, nargs="+", default=[100, 101, 102])
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE[,...]")
    args = ap.parse_args()
    rules = {}
    for spec in args.set:
        rules.update(parse_overrides(spec))
    jobs = [(d, n, s, args.ladder, rules) for d in args.dims for n in args.nursery_seeds for s in (0, 1)]
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(run, jobs))
    for dims in args.dims:
        total: dict = {}
        for d, counts in results:
            if d == dims:
                for k, v in counts.items():
                    t = total.setdefault(k, [0, 0, 0])
                    for i in range(3):
                        t[i] += v[i]
        print(f"{dims}D: share of decisions choosing eat_most / eat_need, by what is in the cell")
        for k, (n, most, need) in sorted(total.items()):
            print(f"   {k:<42} n={n:7d}  eat_most {most / n:5.1%}  eat_need {need / n:5.1%}")


if __name__ == "__main__":
    main()
