"""How hard is it to find a mate in each dimension? (5zorro, 2026-11-06: "there
is probably a lot of distance between every 4D creature and other creatures...
there may be a lot more population density needed for the breeding?")

The food trip has its own measure (scripts/travel_time.py); this is the one for
mates. Play worlds matched on travel time (`ladder.py --worlds time`), started
from the ladder's nursery brains, report per dimension:

- density: NPCs per cell, and the chance a random NPC sits within reach
  (same cell or one step: 1 + 2 x dims cells) of at least one other, both as
  predicted for NPCs scattered at random and as measured;
- the distance (wrapped steps) to the nearest other NPC;
- mate attempts per 1,000 NPC-ticks, and why they fail: not eligible (too
  young, too thin, health 0.5 or less, cooling down), no one within reach, someone within reach but not
  ready or not eligible; and births per 1,000 NPC-ticks.

    python scripts/probe_mating.py
    python scripts/probe_mating.py --brains snapshots/ladder3 --ticks 5000
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim import Config, Simulation  # noqa: E402
from sim.nursery import load_brain_pool, seed_brains  # noqa: E402
from sim.simulation import Batch  # noqa: E402
from ladder import WORLD_SETS  # noqa: E402
from sweep import RESEARCH_DEFAULTS  # noqa: E402


def wrapped(a: np.ndarray, size: int) -> np.ndarray:
    d = np.abs(a) % size
    return np.minimum(d, size - d)


def job(args: tuple) -> dict:
    dims, seed, ticks, brains = args
    size, radius = WORLD_SETS["time"][dims]
    sim = Simulation(Config(**{**RESEARCH_DEFAULTS, "dims": dims, "size": size,
                               "food_patch_radius": radius, "seed": seed}), log_every=250)
    folder = Path(brains) / f"d{dims}-s{size}-r{radius:g}-h16-n100" if brains else None
    if folder is not None and folder.exists():          # else scratch (e.g. no 2D nursery there)
        seed_brains(sim, load_brain_pool(folder))
    b, mate = sim.batch, sim.actions.index("mate")
    why: Counter = Counter()
    orig = Batch.decide_all

    def counting(self, order, *a, **k):
        acts = orig(self, order, *a, **k)
        P = self.pop
        alive = order[P.alive[order]]
        pos = P.pos[alive]
        ready = P.mate_ready_until[alive] >= self.tick
        eligible = np.array([self._can_mate(s, sim.cfg) for s in alive.tolist()], dtype=bool)
        for i in np.flatnonzero(acts[P.alive[order]] == mate):
            steps = wrapped(pos - pos[i], size).sum(axis=1)
            near = (steps <= 1) & (np.arange(alive.size) != i)
            if not eligible[i]:
                s = alive[i]
                if P.age[s] < sim.cfg.adult_age:
                    why["not eligible: too young"] += 1
                elif P.body[s] < sim.cfg.reproduce_min_mass:
                    why["not eligible: too thin"] += 1
                elif P.health[s] <= 0.5:
                    why["not eligible: unwell"] += 1
                else:
                    why["not eligible: cooling down"] += 1
            elif not near.any():
                why["no one within reach"] += 1
            elif not (near & ready & eligible).any():
                why["neighbor not ready or not eligible"] += 1
            else:
                why["partner ready"] += 1
        return acts
    Batch.decide_all = counting

    cells = size ** dims
    reach = 1 + 2 * dims
    npc_ticks = births0 = 0
    within, nearest, predicted = [], [], []
    for t in range(ticks):
        b.step()
        P = sim.pop
        live = P.live(sim.index)
        n = live.size
        npc_ticks += n
        if t % 25 == 0 and n > 1:
            pos = P.pos[live]
            steps = wrapped(pos[:, None, :] - pos[None, :, :], size).sum(axis=2)
            np.fill_diagonal(steps, 10**9)
            within.append(float((steps.min(axis=1) <= 1).mean()))
            nearest.append(float(steps.min(axis=1).mean()))
            predicted.append(1.0 - (1.0 - reach / cells) ** (n - 1))
    births = sum(h.get("births", 0) for h in sim.stats.history)
    Batch.decide_all = orig
    return {"dims": dims, "density": npc_ticks / ticks / cells, "pop": npc_ticks / ticks,
            "within_pred": float(np.mean(predicted)), "within": float(np.mean(within)),
            "nearest": float(np.mean(nearest)), "npc_ticks": npc_ticks, "births": births, "why": why}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", default=[2, 3, 4])
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--ticks", type=int, default=5000)
    ap.add_argument("--brains", default="snapshots/ladder3",
                    help="ladder nursery folder (h16, nursery seed 100); '' = scratch brains")
    args = ap.parse_args()
    jobs = [(d, s, args.ticks, args.brains) for d in args.dims for s in range(args.seeds)]
    with ProcessPoolExecutor(len(jobs)) as pool:
        results = list(pool.map(job, jobs))
    print(f"{'dims':>4} {'pop':>5} {'NPC/cell':>8} {'reach?':>6} {'(random)':>8} {'nearest':>7} "
          f"{'mate/1k':>7} {'births/1k':>9}  mate attempts that: (share)")
    for d in args.dims:
        rs = [r for r in results if r["dims"] == d]
        why = sum((r["why"] for r in rs), Counter())
        nt = sum(r["npc_ticks"] for r in rs)
        tries = sum(why.values())
        shares = ", ".join(f"{k} {v / tries:.0%}" for k, v in why.most_common()) if tries else "none"
        print(f"{d:>4} {np.mean([r['pop'] for r in rs]):5.0f} {np.mean([r['density'] for r in rs]):8.4f} "
              f"{np.mean([r['within'] for r in rs]):6.1%} {np.mean([r['within_pred'] for r in rs]):8.1%} "
              f"{np.mean([r['nearest'] for r in rs]):7.2f} {1000 * tries / nt:7.1f} "
              f"{1000 * sum(r['births'] for r in rs) / nt:9.2f}  {shares}")


if __name__ == "__main__":
    main()
