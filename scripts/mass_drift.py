"""How well is mass conserved over a long run, and which phase of a tick leaks?

Runs one world per (dims, precision) and prints total mass relative to the
start at checkpoints. With --ledger, also books the mass change of every phase
of a tick (summed in float64 around each phase), to find where a leak comes
from. Findings so far (docs/plan-gpu-backend.md, "float32 measured"): float64
drifts ~1e-14 per 100,000 ticks; float32 ~5e-5, almost all from the world
step's growth transfer; the rounding plug (Config.mass_plug_every) holds
float32 to its ledger.

    python scripts/mass_drift.py                       # 2D and 4D, both widths, 100,000 ticks
    python scripts/mass_drift.py --ticks 20000 --ledger --precision float32 --dims 2
    python scripts/mass_drift.py --set mass_plug_every=100 --precision float32
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim import Config, Simulation  # noqa: E402
from sim.config import parse_overrides  # noqa: E402
from sim.simulation import Batch  # noqa: E402

WORLDS = {1: dict(size=1024, food_patch_radius=55.0), 2: dict(size=32, food_patch_radius=4.0),
          3: dict(size=14, food_patch_radius=1.88), 4: dict(size=10, food_patch_radius=1.23)}
PHASES = ("_world_step", "_moves", "_eats", "_social", "_rest", "_metabolize", "_fall")


def install_ledger(ledger: dict) -> None:
    """Wrap each phase so its mass change (float64 sums) is added to `ledger`."""
    def mass(b: Batch) -> float:
        return sum(s.total_mass() for s in b.sims)

    for name in PHASES:
        orig = getattr(Batch, name)

        def run(self, *a, _orig=orig, _name=name, **k):
            before = mass(self)
            out = _orig(self, *a, **k)
            ledger[_name] += mass(self) - before
            return out
        setattr(Batch, name, run)


def drift(job: tuple) -> tuple:
    dims, precision, ticks, overrides, ledger_on = job
    ledger: dict = defaultdict(float)
    if ledger_on:
        install_ledger(ledger)
    sim = Simulation(Config(**{"dims": dims, "hidden_units": 8, "seed": 7, **WORLDS[dims],
                               **overrides, "precision": precision}), log_every=10**9)
    start, done, marks = sim.total_mass(), 0, []
    for mark in sorted({t for t in (1_000, 10_000, 30_000, ticks) if t <= ticks}):
        sim.run(mark - done)
        done = mark
        marks.append((mark, (sim.total_mass() - start) / start))
    plugged = sim.stats.mass_plugged / start
    return dims, precision, marks, {k: v / start for k, v in ledger.items()}, plugged


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", default=[2, 4])
    ap.add_argument("--precision", nargs="+", default=["float32", "float64"])
    ap.add_argument("--ticks", type=int, default=100_000)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE[,...]")
    ap.add_argument("--ledger", action="store_true", help="also book each phase's mass change (slow)")
    args = ap.parse_args()
    overrides: dict = {}
    for spec in args.set:
        overrides.update(parse_overrides(spec))
    jobs = [(d, p, args.ticks, overrides, args.ledger) for d in args.dims for p in args.precision]
    with ProcessPoolExecutor(len(jobs)) as pool:
        for dims, precision, marks, ledger, plugged in pool.map(drift, jobs):
            line = "  ".join(f"{t:>7,} ticks {d:+.2e}" for t, d in marks)
            print(f"{dims}D {precision}: {line}" + (f"  (plugged {plugged:+.2e})" if plugged else ""))
            for name in sorted(ledger, key=lambda k: -abs(ledger[k])):
                print(f"    {name:12s} {ledger[name]:+.2e}")


if __name__ == "__main__":
    main()
