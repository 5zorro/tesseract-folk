"""Probe (M1 plan, slice 6 diagnosis): why does each NPC's lowest nutrient sit around 0.34?

Runs gentle play worlds (nursery-4 brains, and the scripted forager) and, in the
last quarter, records per NPC-tick: nutrient spread, which nutrient is lowest,
actions taken, what eating achieved, and whether the needed food was nearby.
It wraps private Simulation methods, so it may need updating when they change.

    python scripts/probe_nutrients.py      (~1 minute, 6 processes; needs snapshots/nursery-4)
"""
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sim import Config, Simulation                      # noqa: E402
from sim.controllers import ScriptedController           # noqa: E402
from sim.nursery import load_brain_pool, seed_brains     # noqa: E402

TICKS, FROM = 10000, 7500


def run(args):
    variant, seed = args
    sim = Simulation(Config(seed=seed), log_every=10**9)
    if variant == "nursery-4":
        seed_brains(sim, load_brain_pool(ROOT / "snapshots" / "nursery-4"))
    scripted = ScriptedController() if variant == "scripted" else None
    w, cfg = sim.world, sim.cfg
    acts, eats = Counter(), Counter()
    rec = {"sorted": [], "argmin": Counter(), "below01": 0, "below04": 0, "n": 0,
           "food_here": 0, "need_here": 0, "need_near": 0, "idle": 0,
           "gain": [], "sat_eaten": [], "start_collapses": 0}
    orig_act, orig_eat = sim._act, sim._eat

    def act(npc, action, index, births):
        if sim.tick > FROM:
            acts[sim.actions[action]] += 1
            n = npc.nutrients
            rec["n"] += 1
            rec["sorted"].append(np.sort(n))
            low = int(np.argmin(n))
            rec["argmin"][low] += 1
            rec["below01"] += n.min() < 0.1
            rec["below04"] += n.min() < 0.4
            rec["idle"] += npc.idle_streak > cfg.idle_grace_ticks
            here = w.food_at(npc.pos)
            rec["food_here"] += here.sum() > 0.05
            # food type richest in the lowest nutrient (profiles: type t rich in t % n)
            need = [t for t in range(cfg.n_food_types) if w.profiles[t].argmax() == low]
            rec["need_here"] += here[need].sum() > 0.05
            rec["need_near"] += any(w.food_at(c)[need].sum() > 0.05 for c in w.adjacent(npc.pos))
        orig_act(npc, action, index, births)

    def eat(npc):
        if sim.tick <= FROM:
            return orig_eat(npc)
        before = npc.nutrients.copy()
        eaten_before = npc.eaten.copy()
        sat_before = npc.satiation.copy()
        orig_eat(npc)
        got = npc.eaten - eaten_before
        if got.sum() <= 0:
            eats["nothing to eat"] += 1
            return
        t = int(np.argmax(got))
        eats["ate"] += 1
        eats["ate the lowest nutrient's food"] += w.profiles[t].argmax() == int(np.argmin(before))
        rec["gain"].append(float((npc.nutrients - before).sum()))
        rec["sat_eaten"].append(float(sat_before[t]))
    sim._act, sim._eat = act, eat

    for _ in range(TICKS):
        if scripted is not None:
            sim.overrides = {n.id: scripted for n in sim.npcs}
        sim.step()
    food = w.food.sum(axis=tuple(range(1, w.food.ndim))) / w.capacity.sum(axis=tuple(range(1, w.food.ndim)))
    return variant, seed, acts, eats, rec, food, len(sim.npcs)


def main():
    jobs = [(v, s) for v in ("nursery-4", "scripted") for s in range(3)]
    with ProcessPoolExecutor(6) as ex:
        results = list(ex.map(run, jobs))
    for variant in ("nursery-4", "scripted"):
        acts, eats, argmin = Counter(), Counter(), Counter()
        agg = Counter()
        sorted_n, gain, sat, foods = [], [], [], []
        for v, seed, a, e, r, food, pop in results:
            if v != variant:
                continue
            acts += a; eats += e; argmin += r["argmin"]
            for k in ("below01", "below04", "n", "food_here", "need_here", "need_near", "idle"):
                agg[k] += r[k]
            sorted_n += r["sorted"]; gain += r["gain"]; sat += r["sat_eaten"]
            foods.append(food)
            print(f"  {variant} seed {seed}: lowest-nutrient type {dict(r['argmin'])}, "
                  f"food stock / capacity per type {np.round(food, 2)}, pop {pop}")
        n = agg["n"]
        s = np.mean(sorted_n, axis=0)
        print(f"\n== {variant} (3 seeds, ticks {FROM}-{TICKS}, {n} NPC-ticks)")
        print(f"nutrients sorted low/mid/high: {np.round(s, 2)}")
        print(f"lowest < 0.1 (starving): {agg['below01']/n:.0%}   lowest < 0.4 (no healing): {agg['below04']/n:.0%}")
        print(f"idle beyond grace: {agg['idle']/n:.0%}")
        print(f"standing on any food: {agg['food_here']/n:.0%}   on food for the lowest nutrient: "
              f"{agg['need_here']/n:.0%}   next to it: {agg['need_near']/n:.0%}")
        matched = eats["ate the lowest nutrient's food"]
        print("actions: " +", ".join(f"{k} {c/n:.0%}" for k, c in acts.most_common()))
        print(f"eat attempts: {sum(eats[k] for k in ('ate', 'nothing to eat'))/n:.1%} of ticks; "
              f"nothing to eat {eats['nothing to eat']}, ate {eats['ate']}, "
              f"of which the lowest nutrient's food {matched}")
        if gain:
            print(f"nutrition per bite: {np.mean(gain):.3f} (max possible 0.165); "
                  f"satiation of the eaten type: {np.mean(sat):.2f}")
        need = 3 * Config().nutrient_decay
        print(f"bites needed per tick to break even at zero satiation: {need/0.165:.3f}; "
              f"bites taken per NPC-tick: {eats['ate']/n:.3f}")


if __name__ == "__main__":
    main()
