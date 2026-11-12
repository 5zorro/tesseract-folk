"""Scent probe (docs/plan-memory-reaction.md, after MR2b): do today's foragers need food scent?

Scoring only. MR2's control nurseries (Q = 3, no memory slots, trained with
full scent; `scripts/mr2_experiment.py` builds them under snapshots/mr2) are
scored in M2's top-up worlds at several `scent_floor` values, and once with
**no scent**: both scent senses (the level here and the gradient) read as
zeros. The floor only fades the gradient, so "no scent" is the true zero.
Each arm is compared with floor 0, by nursery (seeds averaged first).

    python scripts/scent_floor_probe.py                  # 2D and 4D, floors 0 1 3 10 + no scent
    python scripts/scent_floor_probe.py --report-only
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager, nullcontext
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim.simulation import Batch  # noqa: E402
from m3_ladder import NURSERIES, ROOT  # noqa: E402
from mr2_experiment import METRICS, score, trained_path  # noqa: E402

NO_SCENT = "none"


@contextmanager
def scent_blind():
    """Batch.sense_slots with both food-scent senses zeroed. Restored on exit;
    never import this into a long-lived process."""
    original = Batch.sense_slots

    def sensing(self, slots, *a, **k):
        obs = original(self, slots, *a, **k)
        layout = self.sims[0].sense_layout()
        obs[:, layout["scent_here"]] = 0.0
        obs[:, layout["scent_grad"]] = 0.0
        return obs

    Batch.sense_slots = sensing
    try:
        yield
    finally:
        Batch.sense_slots = original


def job(task: tuple) -> list[dict]:
    dims, source, nseed, path, floor, seeds, ticks = task
    extra = {"scent_floor": 0.0 if floor == NO_SCENT else float(floor)}
    with scent_blind() if floor == NO_SCENT else nullcontext():
        rows = score((dims, "control", 0, source, nseed, path, seeds, ticks, extra))
    return [{**r, "floor": floor} for r in rows]


def report(rows: list[dict]) -> None:
    floors = list(dict.fromkeys(r["floor"] for r in rows))
    for dims in sorted({r["dims"] for r in rows}):
        mine = [r for r in rows if r["dims"] == dims]
        # mean per (floor, nursery) over seeds
        cell: dict = {}
        for r in mine:
            cell.setdefault((r["floor"], r["source"], r["nseed"]), []).append(r)
        nurseries = sorted({(r["source"], r["nseed"]) for r in mine})
        print(f"\n=== {dims}D: {len(nurseries)} nurseries; value, change vs floor 0, nurseries down/up ===")
        print(f"{'floor':>6s} " + " ".join(f"{m[0]:>22s}" for m in METRICS))
        for f in floors:
            out = []
            for _, key in METRICS:
                per = []
                for n in nurseries:
                    a, b = cell.get((f, *n)), cell.get((floors[0], *n))
                    if a and b:
                        per.append((np.nanmean([x[key] for x in a]), np.nanmean([x[key] for x in b])))
                v = np.array([p[0] for p in per], float)
                text = f"{np.nanmean(v):8.3g}"
                if f != floors[0]:
                    d = np.array([p[0] - p[1] for p in per], float)
                    d = d[np.isfinite(d)]
                    text += f" {d.mean():+8.2g} {(d < 0).sum():2d}/{(d > 0).sum():<2d}"
                out.append(text)
            print(f"{str(f):>6s} " + " ".join(f"{c:>22s}" for c in out))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", default=[2, 4])
    ap.add_argument("--floors", nargs="+", default=["0", "1", "3", "10", NO_SCENT])
    ap.add_argument("--nursery-seeds", type=int, nargs="+", default=[200, 201, 202])
    ap.add_argument("--train-ticks", type=int, default=60_000)
    ap.add_argument("--trained", default="snapshots/mr2", help="where mr2_experiment saved its nurseries")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--ticks", type=int, default=10_000)
    ap.add_argument("--csv", default="runs/scent-floor-probe.json")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--jobs", type=int, default=None)
    a = ap.parse_args()
    csv = ROOT / a.csv
    if a.report_only:
        saved = json.loads(csv.read_text())
        print(f"settings: {saved['settings']}")
        report(saved["rows"])
        return
    floors = [f if f == NO_SCENT else float(f) for f in a.floors]
    seeds, trained = list(range(a.seeds)), ROOT / a.trained
    tasks = []
    for d in a.dims:
        for src in NURSERIES[d]:
            for n in a.nursery_seeds:
                path = trained_path(trained, src, 0, n, a.train_ticks)
                if not (path / "state.json").exists():
                    raise SystemExit(f"missing trained nursery {path}; run scripts/mr2_experiment.py first")
                tasks += [(d, src, n, path, f, seeds, a.ticks) for f in floors]
    tasks.sort(key=lambda t: -t[0])
    print(f"scent probe: {len(tasks)} cells x {a.seeds} seeds x {a.ticks} ticks", flush=True)
    with ProcessPoolExecutor(max_workers=a.jobs) as pool:
        rows = [r for cell in pool.map(job, tasks) for r in cell]
    settings = {"dims": a.dims, "floors": a.floors, "nursery_seeds": a.nursery_seeds, "trained": a.trained,
                "seeds": a.seeds, "ticks": a.ticks}
    csv.parent.mkdir(parents=True, exist_ok=True)
    csv.write_text(json.dumps({"settings": settings, "rows": rows}, default=float))
    report(rows)


if __name__ == "__main__":
    main()
