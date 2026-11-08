"""Why M3's worlds fall to the floor (plan-m3 S1 follow-up, 5zorro 2026-11-08:
"why do you think it fell?").

Runs M3's worlds (`scripts/m3_ladder.py`: each dimension's M2 nurseries and
scratch, at its M2 hunger) and reports per source:

- **mating:** mate attempts per 1,000 NPC-ticks and why they fail (too young,
  too thin, unwell, cooling down, no one within reach, neighbor not ready),
  births per 1,000 NPC-ticks;
- **who replaces whom:** finished lives by origin (founders, births, top-up
  copies): lifetime, collapses per 1,000 ticks, share reaching adult age,
  children per life. Births only sustain a world if born NPCs live to have
  children of their own;
- **5zorro's crossover idea:** do children of more different parents do worse?
  Parent distance = RMS weight difference at the birth, children split in
  thirds by it.

    python scripts/probe_births.py                      # 2D-4D, 3 seeds x 15,000 ticks
    python scripts/probe_births.py --dims 4 --seeds 2 --ticks 8000
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
from sim.brain import Brain  # noqa: E402
from sim.nursery import load_brain_pool, seed_brains  # noqa: E402
from sim.simulation import Batch  # noqa: E402
from ladder import WORLD_SETS, world  # noqa: E402
from m3_ladder import HIDDEN, HUNGER, ROOT, hunger_rules, sources  # noqa: E402

ORIGINS = {"": "founder", "birth": "birth", "copy": "top-up", "cross": "top-up", "trial": "trial"}


def flat(brain: Brain) -> np.ndarray:
    return np.concatenate([a.ravel() for a in brain._arrays()])


def job(task: tuple) -> dict:
    """One world: counts, finished lives (with ids) and each child's parent distance."""
    dims, source, seed, ticks = task
    cfg = Config(**{**world((dims, *WORLD_SETS["time"][dims], HIDDEN, ())), **hunger_rules(HUNGER[dims]),
                    "seed": seed})
    if cfg.topup_crossover:     # its crossovers would be taken for births' (the pending list below)
        raise ValueError("probe_births assumes topup_crossover is off")
    sim = Simulation(cfg, log_every=250)
    if source != "scratch":
        seed_brains(sim, load_brain_pool(ROOT / source))
    why: Counter = Counter()
    distance: dict[int, float] = {}
    pending: list[float] = []
    lives: list[dict] = []
    mate = sim.actions.index("mate")

    decide, crossover, make, record = Batch.decide_all, Brain.crossover, sim._make_npc, sim.stats.record_life

    def counting(self, order, *a, **k):
        acts = decide(self, order, *a, **k)
        P = self.pop
        alive = order[P.alive[order]]
        tries = np.flatnonzero(acts[P.alive[order]] == mate)
        if tries.size:
            pos = P.pos[alive]
            ready = P.mate_ready_until[alive] >= self.tick
            eligible = np.array([self._can_mate(s, cfg) for s in alive.tolist()], dtype=bool)
            for i in tries:
                s = alive[i]
                d = np.abs(pos - pos[i]) % cfg.size
                near = (np.minimum(d, cfg.size - d).sum(axis=1) <= 1) & (np.arange(alive.size) != i)
                if P.age[s] < cfg.adult_age:
                    why["too young"] += 1
                elif P.body[s] < cfg.reproduce_min_mass:
                    why["too thin"] += 1
                elif P.health[s] <= 0.5:
                    why["unwell"] += 1
                elif not eligible[i]:
                    why["cooling down"] += 1
                elif not near.any():
                    why["no one in reach"] += 1
                elif not (near & ready & eligible).any():
                    why["neighbor not ready"] += 1
                else:
                    why["partner ready"] += 1
        return acts

    def crossing(a, b, rng):
        pending.append(float(np.sqrt(np.mean((flat(a) - flat(b)) ** 2))))
        return crossover(a, b, rng)

    def making(*a, **k):
        npc = make(*a, **k)
        if pending:                                   # _mate: crossover, then this child
            distance[npc.id] = pending.pop()
        return npc

    def recording(npc, tick):
        record(npc, tick)
        lives.append({**sim.stats.lives[-1], "id": npc.id})

    Batch.decide_all, Brain.crossover = counting, staticmethod(crossing)
    sim._make_npc, sim.stats.record_life = making, recording
    try:
        npc_ticks = 0
        for _ in range(ticks):
            sim.batch.step()
            npc_ticks += len(sim.npcs)
    finally:
        Batch.decide_all, Brain.crossover = decide, staticmethod(crossover)
    births = sum(h.get("births", 0) for h in sim.stats.history)
    return {"dims": dims, "source": source, "seed": seed, "why": why, "npc_ticks": npc_ticks,
            "births": births, "lives": lives, "distance": distance, "adult_age": cfg.adult_age}


def label(source: str) -> str:
    name = Path(source).name
    return name if len(name) <= 16 else name.rsplit("-", 1)[-1]


def report(results: list[dict]) -> None:
    keys = list(dict.fromkeys((r["dims"], r["source"]) for r in results))
    print("\nMating (per 1,000 NPC-ticks; failure reasons as shares of attempts)")
    print(f"{'dims':>4} {'source':>16} {'tries':>6} {'births':>6}  why attempts fail")
    for dims, source in keys:
        rs = [r for r in results if (r["dims"], r["source"]) == (dims, source)]
        why = sum((r["why"] for r in rs), Counter())
        nt, tries = sum(r["npc_ticks"] for r in rs), sum(why.values())
        shares = ", ".join(f"{k} {v / tries:.0%}" for k, v in why.most_common()) if tries else "none"
        print(f"{dims:>4} {label(source):>16} {1000 * tries / nt:6.1f} {1000 * sum(r['births'] for r in rs) / nt:6.2f}"
              f"  {shares}")
    print("\nFinished lives by origin (lives, mean lifetime, collapses per 1,000 ticks, share reaching adult age,"
          "\nchildren per life)")
    print(f"{'dims':>4} {'source':>16} {'origin':>8} {'lives':>6} {'life':>6} {'clpse':>6} {'adult':>6} {'kids':>5}")
    for dims, source in keys:
        rs = [r for r in results if (r["dims"], r["source"]) == (dims, source)]
        adult = rs[0]["adult_age"]
        lives = [l for r in rs for l in r["lives"]]
        for origin in ("founder", "birth", "top-up"):
            ls = [l for l in lives if ORIGINS.get(l["origin"], l["origin"]) == origin]
            if not ls:
                continue
            life = np.array([l["lifetime"] for l in ls], dtype=float)
            col = np.array([l["collapses"] for l in ls], dtype=float)
            print(f"{dims:>4} {label(source):>16} {origin:>8} {len(ls):>6} {life.mean():6.0f} "
                  f"{1000 * col.sum() / max(life.sum(), 1):6.2f} {np.mean(life >= adult):6.0%} "
                  f"{np.mean([l['offspring'] for l in ls]):5.2f}")
    print("\nChildren by parent distance (RMS weight difference). Nursery worlds only (scratch brains are"
          "\nrandom: far apart and worse anyway), thirds taken within each nursery, then pooled; finished"
          "\nlives: n, median distance, collapses per 1,000 ticks, children per life")
    for dims in sorted({r["dims"] for r in results}):
        thirds: dict[str, list] = {"near": [], "middle": [], "far": []}
        for source in dict.fromkeys(r["source"] for r in results if r["dims"] == dims and r["source"] != "scratch"):
            kids = sorted(((r["distance"][l["id"]], l) for r in results if (r["dims"], r["source"]) == (dims, source)
                           for l in r["lives"] if l["origin"] == "birth" and l["id"] in r["distance"]),
                          key=lambda x: x[0])
            if len(kids) < 9:
                continue
            for name, part in zip(thirds, np.array_split(np.arange(len(kids)), 3)):
                thirds[name].extend(kids[i] for i in part)
        if not thirds["near"]:
            print(f"  {dims}D: too few finished children in any nursery")
            continue
        for name, ks in thirds.items():
            life = np.array([l["lifetime"] for _, l in ks], dtype=float)
            col = np.array([l["collapses"] for _, l in ks], dtype=float)
            print(f"  {dims}D {name:>6}: n {len(ks):4} distance {np.median([d for d, _ in ks]):.3f} "
                  f"clpse {1000 * col.sum() / max(life.sum(), 1):5.2f} "
                  f"kids {np.mean([l['offspring'] for _, l in ks]):4.2f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", default=[2, 3, 4], choices=sorted(HUNGER))
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--ticks", type=int, default=15_000)
    ap.add_argument("--jobs", type=int, default=None)
    a = ap.parse_args()
    tasks = [(d, s, seed, a.ticks) for d in a.dims for s in sources(d) for seed in range(a.seeds)]
    tasks.sort(key=lambda t: -t[0])
    with ProcessPoolExecutor(a.jobs) as pool:
        results = list(pool.map(job, tasks))
    results.sort(key=lambda r: (r["dims"], r["source"] == "scratch", r["source"], r["seed"]))
    report(results)


if __name__ == "__main__":
    main()
