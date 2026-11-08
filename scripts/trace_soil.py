"""Trace soil mining in M3's play worlds (plan-m3 slices S3 and S3b).

NPCs eat in the rich patch cores and poop everywhere, so the cores lose their
soil and food stops regrowing there (food grows from its own cell's soil). This
runs one nursery's worlds at M3's settings (`scripts/m3_ladder.py`: the
dimension's M2 world at its M2 hunger) under each variant, and reports per
1,000 ticks, averaged over seeds: mean soil in the cores (cells in any food
type's zone) and outside, core food as a share of capacity, population,
births and top-ups.

Also where NPCs are (5zorro, 2026-11-08: "is there a higher density along
these routes and low density on the rest of the map, or is there an even
density?"): NPC positions every 10 ticks over the second half of the run,
binned by steps to the nearest core cell (0 = in a core). Each bin's share of
NPC-ticks against its share of cells (an even spread gives equal shares), and
the fewest cells holding half the NPC-ticks (50% of cells if even).

    python scripts/trace_soil.py                                   # births-n101, variants below
    python scripts/trace_soil.py --variant default --variant soil_diffusion=0 --seeds 2
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
from ladder import WORLD_SETS, world  # noqa: E402
from m3_ladder import HIDDEN, HUNGER, LOG_EVERY, ROOT, hunger_rules  # noqa: E402
from sweep import RESEARCH_DEFAULTS  # noqa: E402

VARIANTS = ["soil_diffusion=0", "poop_diffusion=0.3,soil_diffusion=0", "soil_diffusion=0.01", "soil_diffusion=0.03",
            "soil_diffusion=0.1", "soil_diffusion=0.3", "poop_diffusion=0.3,soil_diffusion=0.1"]
EVERY = 1000
SAMPLE = 10                 # ticks between position samples
BINS = 4                    # steps to the nearest core: 0, 1, 2, 3 or more


def steps_to(mask: np.ndarray) -> np.ndarray:
    """Each cell's steps (axis moves, wrapping) to the nearest True cell, capped at BINS - 1."""
    out = np.full(mask.shape, BINS - 1)
    reached = mask.copy()
    for d in range(BINS - 1):
        out[reached & (out == BINS - 1)] = d
        grown = reached.copy()
        for axis in range(mask.ndim):
            grown |= np.roll(reached, 1, axis) | np.roll(reached, -1, axis)
        reached = grown
    out[mask] = 0
    return out


def job(task: tuple) -> dict:
    dims, source, variant, seed, ticks = task
    extra = {} if variant == "default" else parse_overrides(variant)
    cfg = Config(**{**RESEARCH_DEFAULTS, **world((dims, *WORLD_SETS["time"][dims], HIDDEN, ())),
                    **hunger_rules(HUNGER[dims]), **extra, "seed": seed})
    sim = Simulation(cfg, log_every=LOG_EVERY)
    if source != "scratch":
        seed_brains(sim, load_brain_pool(ROOT / source))
    w = sim.world
    core = (w.zones >= 0).any(axis=0)
    cap = w.capacity.sum(axis=0)
    dist = steps_to(core).ravel()
    visits = np.zeros(core.size)
    rows = []
    for t in range(EVERY, ticks + 1, EVERY):
        for _ in range(EVERY // SAMPLE):
            sim.batch.run(SAMPLE)
            if sim.tick > ticks // 2:
                pos = sim.pop.pos[sim.pop.live(sim.index)]
                if len(pos):
                    visits += np.bincount(np.ravel_multi_index(tuple(pos.T), w.shape), minlength=core.size)
        late = [h for h in sim.stats.history if t - EVERY < h["tick"] <= t]
        rows.append({"tick": t, "core soil": float(w.soil[core].mean()), "outside soil": float(w.soil[~core].mean()),
                     "core food": float(w.food.sum(axis=0)[core].sum() / cap[core].sum()),
                     "pop": len(sim.npcs), "births": sum(h.get("births", 0) for h in late),
                     "top-ups": sum(h.get("spawns", 0) for h in late)})
    total = max(visits.sum(), 1.0)
    density = {"cells": [float(np.mean(dist == b)) for b in range(BINS)],
               "npcs": [float(visits[dist == b].sum() / total) for b in range(BINS)],
               "half": float(np.searchsorted(np.cumsum(np.sort(visits)[::-1]), total / 2) + 1) / core.size}
    return {"variant": variant, "seed": seed, "rows": rows, "core cells": int(core.sum()), "density": density}


def report(results: list[dict], show: list[int]) -> None:
    keys = ("core soil", "outside soil", "core food", "pop", "births", "top-ups")
    print(f"\nPer {EVERY:,} ticks, means over seeds ({results[0]['core cells']} core cells). "
          "Births and top-ups are counts in the 1,000 ticks before.")
    for variant in dict.fromkeys(r["variant"] for r in results):
        rs = [r for r in results if r["variant"] == variant]
        print(f"\n== {variant}")
        print(f"{'tick':>7} " + " ".join(f"{k:>12}" for k in keys))
        for i, row in enumerate(rs[0]["rows"]):
            if row["tick"] not in show:
                continue
            m = {k: np.mean([r["rows"][i][k] for r in rs]) for k in keys}
            print(f"{row['tick']:>7} " + " ".join(f"{m[k]:12.3f}" if k.endswith(("soil", "food"))
                                                  else f"{m[k]:12.1f}" for k in keys))
        cells = np.mean([r["density"]["cells"] for r in rs], axis=0)
        npcs = np.mean([r["density"]["npcs"] for r in rs], axis=0)
        half = np.mean([r["density"]["half"] for r in rs])
        bins = [f"{b} step{'s' if b != 1 else ''}" for b in range(BINS - 1)] + [f"{BINS - 1}+ steps"]
        print("  where NPCs are (second half), by steps to the nearest core: "
              + ", ".join(f"{b}: {n:.0%} of NPCs on {c:.0%} of cells" for b, n, c in zip(bins, npcs, cells)))
        print(f"  half the NPC-ticks fall on {half:.1%} of cells (50% if even)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, default=4, choices=sorted(HUNGER))
    ap.add_argument("--source", default="snapshots/s3/births-n101-r35", help="nursery folder, or scratch")
    ap.add_argument("--variant", action="append", default=None, help="'default' (today's rules) or K=V,... (repeatable)")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--ticks", type=int, default=30_000)
    ap.add_argument("--jobs", type=int, default=None)
    a = ap.parse_args()
    variants = a.variant or VARIANTS
    for v in variants:
        if v != "default":
            parse_overrides(v)                      # fail before the pool starts
    if a.source != "scratch" and not (ROOT / a.source / "state.json").exists():
        ap.error(f"no nursery at {a.source}")
    tasks = [(a.dims, a.source, v, s, a.ticks) for v in variants for s in range(a.seeds)]
    with ProcessPoolExecutor(a.jobs) as pool:
        results = list(pool.map(job, tasks))
    show = sorted({t for t in (1000, 2000, 3000, 5000, 7500, 10_000, 15_000, 20_000, 25_000, 30_000)
                   if t <= a.ticks} | {a.ticks // EVERY * EVERY})
    report(results, show)


if __name__ == "__main__":
    main()
