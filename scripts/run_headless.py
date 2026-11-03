"""Run the simulation without graphics and print the stats table.

Examples:
    python scripts/run_headless.py --ticks 5000
    python scripts/run_headless.py --until-stable --save snapshots/baseline
    python scripts/run_headless.py --load snapshots/baseline --ticks 2000
    python scripts/run_headless.py --dims 4 --size 10 --ticks 500
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim import Config, Simulation  # noqa: E402
from sim.snapshot import load_snapshot, save_snapshot  # noqa: E402

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
    ap.add_argument("--load", type=str, default=None, help="snapshot folder to start from")
    args = ap.parse_args()

    if args.load:
        sim = load_snapshot(args.load, log_every=args.log_every)
    else:
        cfg = Config()
        for name in ("dims", "size", "seed"):
            if getattr(args, name) is not None:
                setattr(cfg, name, getattr(args, name))
        sim = Simulation(cfg, log_every=args.log_every)

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
            print(f"Did not stabilize within {args.max_ticks} ticks.")

    elapsed = time.time() - start
    drift = sim.total_mass() - start_mass
    print(f"Done in {elapsed:.1f}s. Mass drift {drift:.2e} (should be ~0).")
    if args.save:
        print(f"Saved snapshot to {save_snapshot(sim, args.save)}")


if __name__ == "__main__":
    main()
