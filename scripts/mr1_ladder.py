"""MR1's delay ladder (docs/plan-memory-reaction.md): what does a reaction
queue of Q ticks cost, and does training win it back?

For each dimension's M2 nurseries (m3_ladder.NURSERIES, at the dimension's M2
hunger), at each queue length Q:
- **as is:** the nursery's brains scored with the queue on. They gain the
  queue's inputs with zero weights (sim.nursery.seed_brains), so they play
  exactly as before except that every action lands Q ticks late (tolerance);
- **trained:** a warm-start nursery (the same brains, NURSERY_RULES, the
  queue on) trained for --train-ticks, then scored. Trained at Q = 0 is the
  control for "just more training".

Scoring is M2's top-up worlds, paired: every arm on the same seeds. The
report gives each metric per Q, and the difference from Q = 0 within the arm
with how many (nursery, seed) pairs agree in sign.

    python scripts/mr1_ladder.py                                  # 2D and 4D, Q = 0 1 3 5
    python scripts/mr1_ladder.py --dims 4 --queue 0 3 --train-ticks 40000
    python scripts/mr1_ladder.py --report-only
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim import Config, Simulation  # noqa: E402
from sim.config import parse_overrides  # noqa: E402
from sim.nursery import load_brain_pool, seed_brains  # noqa: E402
from sim.snapshot import LEGACY, save_snapshot  # noqa: E402
from ladder import NURSERY_RULES, WORLD_SETS, physics_tag, world  # noqa: E402
from m3_ladder import HIDDEN, HUNGER, NURSERIES, ROOT, hunger_rules  # noqa: E402
from sweep import run_batch  # noqa: E402

LOG_EVERY = 250
METRICS = (("collapses", "collapse_rate"), ("diet", "diet_diversity"), ("types", "zone_types_per_life"),
           ("low nutr", "min_nutrient"), ("approach+", "approach_excess"), ("pop", "pop_mean"),
           ("births", "births"))


def play_rules(dims: int, queue: int, extra: dict) -> dict:
    return {**world((dims, *WORLD_SETS["time"][dims], HIDDEN, ())), **hunger_rules(HUNGER[dims]),
            **extra, "reaction_queue": queue}


def nursery_rules(dims: int, queue: int, nseed: int, extra: dict) -> dict:
    return {**play_rules(dims, queue, extra), **NURSERY_RULES, "seed": nseed}


def trained_path(out: Path, source: str, queue: int, ticks: int) -> Path:
    return out / f"{Path(source).name}-q{queue}-t{ticks}{physics_tag()}"


def reusable(path: Path, rules: dict, source: str, ticks: int) -> bool:
    """A trained nursery is reused only if it was trained exactly as asked now."""
    if not (path / "state.json").exists():
        return False
    state = json.loads((path / "state.json").read_text())
    saved = Config.from_dict({**LEGACY, **state.get("config", {})}).to_dict()
    wanted = Config(**rules).to_dict()
    differ = sorted(k for k, v in wanted.items() if saved.get(k) != v)
    meta = json.loads((path / "mr1.json").read_text()) if (path / "mr1.json").exists() else {}
    if differ or state.get("tick") != ticks or meta.get("source") != source:
        raise ValueError(f"{path} was trained otherwise ({', '.join(differ) or 'ticks or source'}). "
                         f"Delete it or use another --out.")
    return True


def train(task: tuple) -> str:
    dims, source, queue, nseed, ticks, out, extra = task
    path = trained_path(Path(out), source, queue, ticks)
    rules = nursery_rules(dims, queue, nseed, extra)
    if reusable(path, rules, source, ticks):
        return f"kept {path.name}"
    sim = Simulation(Config(**rules), log_every=1000)
    seed_brains(sim, load_brain_pool(ROOT / source))
    sim.run(ticks)
    save_snapshot(sim, path)
    (path / "mr1.json").write_text(json.dumps({"source": source, "queue": queue, "ticks": ticks}))
    return f"trained {path.name}"


def score(task: tuple) -> list[dict]:
    """One (dims, arm, queue, source) cell: every seed in one batch."""
    dims, arm, queue, source, brains, seeds, ticks, extra = task
    overrides = {**play_rules(dims, queue, extra), "brains_from": str(brains)}
    rows = run_batch([(dict(overrides), s, ticks, 0.5, LOG_EVERY) for s in seeds])
    return [{"dims": dims, "arm": arm, "queue": queue, "source": Path(source).name, **r} for r in rows]


def report(rows: list[dict]) -> None:
    for dims in sorted({r["dims"] for r in rows}):
        for arm in ("as is", "trained"):
            mine = [r for r in rows if r["dims"] == dims and r["arm"] == arm]
            if not mine:
                continue
            queues = sorted({r["queue"] for r in mine})
            print(f"\n=== {dims}D, {arm} (hunger {HUNGER[dims]}x; mean over nurseries x seeds; "
                  f"change from Q=0 with pairs agreeing in sign) ===")
            print(f"{'Q':>3s} " + " ".join(f"{m[0]:>22s}" for m in METRICS))
            base = {(r["source"], r["seed"]): r for r in mine if r["queue"] == 0}
            for q in queues:
                cells = []
                at = [r for r in mine if r["queue"] == q]
                for _, key in METRICS:
                    v = np.array([r[key] for r in at], float)
                    cell = f"{np.nanmean(v):8.3g}" if np.isfinite(v).any() else f"{'nan':>8s}"
                    pairs = [(r[key], base[(r["source"], r["seed"])][key]) for r in at
                             if (r["source"], r["seed"]) in base]
                    d = np.array([a - b for a, b in pairs], float)
                    d = d[np.isfinite(d)]
                    if q and d.size:
                        agree = max(int((d > 0).sum()), int((d < 0).sum()))
                        cell += f" {d.mean():+8.2g} {agree:2d}/{d.size}"
                    cells.append(cell)
                print(f"{q:3d} " + " ".join(f"{c:>22s}" for c in cells))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", default=[2, 4])
    ap.add_argument("--queue", type=int, nargs="+", default=[0, 1, 3, 5])
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--ticks", type=int, default=10_000)
    ap.add_argument("--train-ticks", type=int, default=20_000)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE[,...]")
    ap.add_argument("--out", default="snapshots/mr1")
    ap.add_argument("--csv", default="runs/mr1-ladder.json")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--jobs", type=int, default=None)
    a = ap.parse_args()
    if 0 not in a.queue:
        ap.error("--queue must include 0 (the baseline)")
    extra: dict = {}
    for spec in a.set:
        extra.update(parse_overrides(spec))
    csv = ROOT / a.csv
    settings = {"dims": a.dims, "queue": a.queue, "seeds": a.seeds, "ticks": a.ticks,
                "train_ticks": a.train_ticks, "set": extra, "physics": physics_tag()}
    if a.report_only:
        saved = json.loads(csv.read_text())
        print(f"settings: {saved['settings']}")
        report(saved["rows"])
        return
    out = ROOT / a.out
    seeds = list(range(a.seeds))
    trains = [(d, src, q, 100 + i, a.train_ticks, str(out), extra)
              for d in a.dims for i, src in enumerate(NURSERIES[d]) for q in a.queue]
    print(f"MR1 ladder: training {len(trains)} warm-start nurseries ({a.train_ticks} ticks), "
          f"physics{physics_tag() or ' (old)'}", flush=True)
    with ProcessPoolExecutor(max_workers=a.jobs) as pool:
        for msg in pool.map(train, trains):
            print(" ", msg, flush=True)
        scores = [(d, "as is", q, src, ROOT / src, seeds, a.ticks, extra)
                  for d in a.dims for src in NURSERIES[d] for q in a.queue]
        scores += [(d, "trained", q, src, trained_path(out, src, q, a.train_ticks), seeds, a.ticks, extra)
                   for d in a.dims for src in NURSERIES[d] for q in a.queue]
        print(f"scoring {len(scores)} cells x {a.seeds} seeds x {a.ticks} ticks", flush=True)
        rows = [r for cell in pool.map(score, scores) for r in cell]
    csv.parent.mkdir(parents=True, exist_ok=True)
    csv.write_text(json.dumps({"settings": settings, "rows": rows}))
    report(rows)


if __name__ == "__main__":
    main()
