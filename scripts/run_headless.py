"""Run the simulation without graphics and print the stats table.

Examples:
    python scripts/run_headless.py --ticks 5000
    python scripts/run_headless.py --until-stable --save snapshots/baseline
    python scripts/run_headless.py --load snapshots/baseline --ticks 2000
    python scripts/run_headless.py --dims 4 --size 10 --ticks 500

Nursery (evolve under harsh rules, then start fresh worlds from the best brains):
    python scripts/run_headless.py --set collapse_age_penalty=600 --ticks 20000 --save snapshots/nursery-1
    python scripts/run_headless.py --brains-from snapshots/nursery-1 --set collapse_age_penalty=600 \\
        --ticks 20000 --save snapshots/nursery-2
    python scripts/run_headless.py --brains-from snapshots/nursery-2 --seed 7 --ticks 5000

4D nursery (radius 2, or every 4D cell grows every food):
    python scripts/run_headless.py --dims 4 --size 10 --set food_patch_radius=2.0,collapse_age_penalty=600 \
        --ticks 20000 --save snapshots/nursery-4d-1
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim import Config, Simulation  # noqa: E402
from sim.config import parse_overrides  # noqa: E402
from sim.nursery import load_brain_pool, seed_brains  # noqa: E402
from sim.snapshot import load_snapshot, save_snapshot  # noqa: E402
from sim.stats import CAUSES  # noqa: E402

COLUMNS = [
    ("tick", 7), ("population", 5), ("max_generation", 5), ("births", 6), ("deaths", 6),
    ("collapses", 6), ("spawns", 6), ("gives", 6), ("diet_diversity", 6),
    ("prayers_answered", 6), ("smitings", 6), ("secrets_shared", 6), ("total_mass", 10),
]
HEADERS = ["tick", "pop", "gen", "birth", "death", "clpse", "spawn", "give",
           "diet", "pray", "smite", "share", "mass"]


def fmt(row: dict) -> str:
    cells = []
    for (key, width) in COLUMNS:
        v = row.get(key, 0)
        cells.append(f"{v:>{width}.2f}" if isinstance(v, float) else f"{v:>{width}}")
    return " ".join(cells)


def cause_line(label: str, prefix: str, history: list[dict]) -> str:
    counts = {c: sum(h.get(f"{prefix}_{c}", 0) for h in history) for c in CAUSES}
    total = sum(counts.values())
    if total == 0:
        return f"{label}: none"
    parts = [f"{c} {n} ({100 * n / total:.0f}%)"
             for c, n in sorted(counts.items(), key=lambda kv: -kv[1]) if n]
    return f"{label} ({total}): " + ", ".join(parts)


def print_summary(sim) -> None:
    """The M1 readout (what knocks NPCs down, whether later generations
    collapse less often) and M2's travel line (docs/plan-m2-diet-travel.md)."""
    print(cause_line("Collapse causes", "collapse", sim.stats.history))
    print(cause_line("Death causes", "death", sim.stats.history))
    rates = sim.stats.collapse_rate_by_generation()
    lifetimes = sim.stats.generation_lifetime
    print("Collapses per 1,000 NPC-ticks, by generation: " + ", ".join(
        f"g{g} {r:.1f} (n={lifetimes[g]})" for g, r in rates.items()))
    travel = sim.stats.travel_summary()
    if travel["lives"]:
        print(f"Travel (M2), over {travel['lives']} completed lives of 500+ ticks: "
              f"{travel['zones']:.1f} zones eaten in per life, "
              f"{travel['zone_types']:.1f} of {sim.cfg.n_food_types} food types' zones, "
              f"{travel['switch_rate']:.1f} zone switches per 1,000 NPC-ticks")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ticks", type=int, default=3000)
    ap.add_argument("--dims", type=int, default=None)
    ap.add_argument("--size", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--log-every", type=int, default=250)
    ap.add_argument("--until-stable", action="store_true",
                    help="keep running until the population settles (ignores --ticks)")
    ap.add_argument("--max-ticks", type=int, default=100_000)
    ap.add_argument("--save", type=str, default=None, help="snapshot folder to write at the end")
    ap.add_argument("--load", type=str, default=None,
                    help="snapshot folder to resume exactly (same world, same rules)")
    ap.add_argument("--brains-from", type=str, default=None,
                    help="start a fresh world from this snapshot's best brains (the nursery)")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE[,...]",
                    help="Config override for a fresh world (repeatable)")
    args = ap.parse_args()

    if args.load and (args.brains_from or args.set):
        ap.error("--load resumes a world as saved; use --brains-from to change rules or seed")
    if args.load:
        sim = load_snapshot(args.load, log_every=args.log_every)
    else:
        cfg = Config()
        for name in ("dims", "size", "seed"):
            if getattr(args, name) is not None:
                setattr(cfg, name, getattr(args, name))
        try:
            for spec in args.set:
                for key, value in parse_overrides(spec).items():
                    setattr(cfg, key, value)
        except ValueError as e:
            ap.error(str(e))
        sim = Simulation(cfg, log_every=args.log_every)
        if args.brains_from:
            pool = load_brain_pool(args.brains_from)
            try:
                seed_brains(sim, pool)
            except ValueError as e:
                ap.error(str(e))
            print(f"Seeded {len(sim.npcs)} NPCs from {len(pool)} brains in {args.brains_from} "
                  f"(best fitness {pool[0]['fitness']:.0f}, generations "
                  f"{min(e['generation'] for e in pool)}-{max(e['generation'] for e in pool)}).")

    print(f"dims={sim.cfg.dims} size={sim.cfg.size} inputs={sim.n_inputs} "
          f"actions={sim.n_actions} brain_params={sim.npcs[0].brain.n_params if sim.npcs else 0}")
    print(" ".join(f"{h:>{w}}" for h, (_, w) in zip(HEADERS, COLUMNS)))

    start_mass = sim.total_mass()
    start = time.time()
    seen = len(sim.stats.history)
    target = args.max_ticks if args.until_stable else args.ticks
    for _ in range(target):
        sim.step()
        if len(sim.stats.history) > seen:
            seen = len(sim.stats.history)
            print(fmt(sim.stats.history[-1]), flush=True)
            if args.until_stable and sim.is_stable():
                print(f"Stable at tick {sim.tick}.")
                break
    else:
        if args.until_stable:
            print(f"Did not stabilize within {args.max_ticks} ticks: "
                  + "; ".join(sim.stability_problems()) + ".")

    elapsed = time.time() - start
    drift = sim.total_mass() - start_mass
    print(f"Done in {elapsed:.1f}s. Mass drift {drift:.2e} (should be ~0).")
    print_summary(sim)
    if args.save:
        print(f"Saved snapshot to {save_snapshot(sim, args.save)}")
        if args.until_stable and not sim.is_stable():
            print("Warning: the world never stabilized, so this is not a real baseline.")


if __name__ == "__main__":
    main()
