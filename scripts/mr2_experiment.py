"""MR2's experiment (docs/plan-memory-reaction.md): does training use the memory net?

Two arms, both warm-started from each dimension's M2 nursery pools
(m3_ladder.NURSERIES) with the reaction queue on (Q = 3):
- **control:** no memory slots;
- **memory:** K memory slots and a fresh memory net per pool brain.
Each pool trains --nursery-seeds nurseries per arm (NURSERY_RULES, the
dimension's M2 hunger, --train-ticks), paired by (pool, nursery seed).

Every trained nursery is then scored in M2's top-up worlds (--seeds x
--ticks), and the memory arm once more as **blind**: the same brains, slots
still written, but the slot senses read as zeros (for the forager and the
memory net alike), so nobody can use a memory.

Usage, measured over the second half of the memory and blind arms' scoring:
- **ops:** the memory net's writes and forgets per 1,000 NPC-ticks;
- **slots:** the share of slots in use and the mean age of the memories held;
- **follow:** of the moves made while a slot remembers food rich in the
  NPC's lowest nutrient, the share that got closer to the best such cell,
  against the chance a random move would (axes still to travel / (2 dims)).
  Remembered food cells are food patches NPCs head for by scent anyway, so the
  blind arm's follow excess is the baseline; memory minus blind is the use.

    python scripts/mr2_experiment.py                         # 2D and 4D, K = 8, 3 nurseries per pool
    python scripts/mr2_experiment.py --dims 4 --slots 4 --train-ticks 30000
    python scripts/mr2_experiment.py --report-only
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

from sim import Config, Simulation  # noqa: E402
from sim.config import parse_overrides  # noqa: E402
from sim.nursery import load_brain_pool, seed_brains  # noqa: E402
from sim.simulation import Batch  # noqa: E402
from sim.snapshot import save_snapshot  # noqa: E402
from sim.world import wrapped_delta  # noqa: E402
from ladder import physics_tag  # noqa: E402
from m3_ladder import HUNGER, NURSERIES, ROOT  # noqa: E402
from mr1_ladder import nursery_rules, play_rules, reusable  # noqa: E402
from sweep import Run  # noqa: E402

LOG_EVERY = 250
QUEUE = 3
METRICS = (("collapses", "collapse_rate"), ("diet", "diet_diversity"), ("types", "zone_types_per_life"),
           ("low nutr", "min_nutrient"), ("approach+", "approach_excess"), ("pop", "pop_mean"),
           ("births", "births"))
USAGE = ("ops", "writes", "forgets", "in_use", "age", "follow", "follow_chance", "follow_moves")


def arm_rules(slots: int, extra: dict) -> dict:
    return {**extra, "memory_slots": slots}


def trained_path(out: Path, source: str, slots: int, nseed: int, ticks: int) -> Path:
    return out / f"{Path(source).name}-q{QUEUE}-k{slots}-n{nseed}-t{ticks}{physics_tag()}"


def train(task: tuple) -> str:
    dims, source, slots, nseed, ticks, out, extra = task
    path = trained_path(Path(out), source, slots, nseed, ticks)
    rules = nursery_rules(dims, QUEUE, nseed, arm_rules(slots, extra))
    if reusable(path, rules, source, ticks):
        return f"kept {path.name}"
    sim = Simulation(Config(**rules), log_every=1000)
    seed_brains(sim, load_brain_pool(ROOT / source))
    sim.run(ticks)
    save_snapshot(sim, path)
    (path / "mr1.json").write_text(json.dumps({"source": source, "slots": slots, "ticks": ticks}))
    return f"trained {path.name}"


@contextmanager
def slots_blind():
    """Batch.sense_slots with the memory slots' senses zeroed (the slots are still
    written and kept), so no net can use a memory. Restored on exit."""
    original = Batch.sense_slots

    def sensing(self, slots, *a, **k):
        obs = original(self, slots, *a, **k)
        obs[:, self.sims[0].sense_layout()["slots"]] = 0.0
        return obs

    Batch.sense_slots = sensing
    try:
        yield
    finally:
        Batch.sense_slots = original


def follow_targets(batch: Batch, live: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per NPC: whether a slot remembers food rich in its lowest nutrient, and
    the cell of the slot remembering the most of it."""
    P = batch.pop
    need = np.argmin(P.nutrients[live], axis=1)
    wanted = batch._rich[P.world[live]] == need[:, None]                       # (n, types)
    score = (P.mem_food[live] * wanted[:, None, :]).sum(axis=2) * P.mem_filled[live]
    best = score.argmax(axis=1)
    has = score[np.arange(live.size), best] > 0
    return has, P.mem_pos[live, best]


def closer_and_chance(before: np.ndarray, after: np.ndarray, target: np.ndarray, size: int) -> tuple:
    """Did each move get closer (wrapped L1) to its target, and how likely was
    that for a random move: the axes still to travel, / (2 dims)."""
    d0 = np.abs(wrapped_delta(before, target, size))
    d1 = np.abs(wrapped_delta(after, target, size))
    return d1.sum(axis=1) < d0.sum(axis=1), (d0 > 0).sum(axis=1) / (2 * before.shape[1])


def score(task: tuple) -> list[dict]:
    """One trained nursery, one arm: every seed in one batch, with usage measures."""
    dims, arm, slots, source, nseed, brains, seeds, ticks, extra = task
    overrides = {**play_rules(dims, QUEUE, arm_rules(slots, extra)), "brains_from": str(brains)}
    runs = [Run(dict(overrides), s, ticks, 0.5, LOG_EVERY) for s in seeds]
    batch = Batch([r.sim for r in runs])
    late = ticks // 2
    use = {k: 0.0 for k in USAGE}
    samples = 0
    measure = arm in ("memory", "blind")
    with slots_blind() if arm == "blind" else nullcontext():
        for _ in range(ticks):
            for r in runs:
                r.before_tick()
            P = batch.pop
            tracking = measure and batch.tick >= late
            if tracking:
                live = P.live()
                has, target = follow_targets(batch, live)
                watch = live[has]
                keys = (P.world[watch].copy(), P.id[watch].copy())
                pos0, target = P.pos[watch].copy(), target[has]
            batch.step()
            for r in runs:
                r.after_tick()
            if tracking and watch.size:
                same = P.alive[watch] & (P.world[watch] == keys[0]) & (P.id[watch] == keys[1])
                moved = same & P.moved_last[watch]
                if moved.any():
                    closer, chance = closer_and_chance(pos0[moved], P.pos[watch[moved]], target[moved], batch.size)
                    use["follow"] += closer.sum()
                    use["follow_chance"] += chance.sum()
                    use["follow_moves"] += moved.sum()
            if tracking and batch.tick % 50 == 0:
                live = P.live()
                filled = P.mem_filled[live]
                use["in_use"] += filled.mean() if live.size else 0.0
                ages = (batch.tick - P.mem_tick[live])[filled]
                use["age"] += ages.mean() if ages.size else 0.0
                samples += 1
    rows = [r.result() for r in runs]
    if measure:
        late_rows = [h for r in runs for h in r.sim.stats.history if h["tick"] > late]
        npc_ticks = sum(h["population"] for h in late_rows) * LOG_EVERY
        use["writes"] = 1000 * sum(h["memory_writes"] for h in late_rows) / max(npc_ticks, 1)
        use["forgets"] = 1000 * sum(h["memory_forgets"] for h in late_rows) / max(npc_ticks, 1)
        use["ops"] = use["writes"] + use["forgets"]
        use["in_use"] /= max(samples, 1)
        use["age"] /= max(samples, 1)
        moves = max(use["follow_moves"], 1)
        use["follow"] /= moves
        use["follow_chance"] /= moves
    return [{"dims": dims, "arm": arm, "source": Path(source).name, "nseed": nseed, **row,
             **({"usage": use} if measure and i == 0 else {})} for i, row in enumerate(rows)]


def report(rows: list[dict]) -> None:
    for dims in sorted({r["dims"] for r in rows}):
        mine = [r for r in rows if r["dims"] == dims]
        by = {(r["arm"], r["source"], r["nseed"], r["seed"]): r for r in mine}
        print(f"\n=== {dims}D (hunger {HUNGER[dims]}x, Q = {QUEUE}; means over pools x nurseries x seeds) ===")
        print(f"{'arm':10s} " + " ".join(f"{m[0]:>22s}" for m in METRICS))
        for arm, base in (("control", None), ("memory", "control"), ("blind", "memory")):
            at = [r for r in mine if r["arm"] == arm]
            if not at:
                continue
            cells = []
            for _, key in METRICS:
                v = np.array([r[key] for r in at], float)
                cell = f"{np.nanmean(v):8.3g}" if np.isfinite(v).any() else f"{'nan':>8s}"
                if base:
                    d = np.array([r[key] - by[(base, r["source"], r["nseed"], r["seed"])][key] for r in at
                                  if (base, r["source"], r["nseed"], r["seed"]) in by], float)
                    d = d[np.isfinite(d)]
                    if d.size:
                        cell += f" {d.mean():+8.2g} {max((d > 0).sum(), (d < 0).sum()):2d}/{d.size}"
                cells.append(cell)
            label = arm if not base else f"{arm} - {base[:4]}"
            print(f"{label:10s} " + " ".join(f"{c:>22s}" for c in cells))
        for arm in ("memory", "blind"):
            usage = [r["usage"] for r in mine if "usage" in r and r["arm"] == arm]
            if not usage:
                continue
            u = {k: np.mean([x[k] for x in usage]) for k in USAGE}
            print(f"{arm} arm: {u['writes']:.1f} writes + {u['forgets']:.1f} forgets per 1,000 NPC-ticks; "
                  f"{100 * u['in_use']:.0f}% of slots in use, mean memory age {u['age']:.0f} ticks; "
                  f"follow {u['follow']:.3f} vs chance {u['follow_chance']:.3f} "
                  f"(excess {u['follow'] - u['follow_chance']:+.3f}; {u['follow_moves']:.0f} moves per cell)")
        cells = {(r["source"], r["nseed"]): {} for r in mine if "usage" in r}
        for r in mine:
            if "usage" in r:
                cells[(r["source"], r["nseed"])][r["arm"]] = r["usage"]["follow"] - r["usage"]["follow_chance"]
        diffs = [c["memory"] - c["blind"] for c in cells.values() if {"memory", "blind"} <= set(c)]
        if diffs:
            print(f"follow excess, memory minus blind, per trained nursery: "
                  + " ".join(f"{d:+.3f}" for d in diffs)
                  + f"  (mean {np.mean(diffs):+.3f}; {sum(d > 0 for d in diffs)}/{len(diffs)} positive)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", default=[2, 4])
    ap.add_argument("--slots", type=int, default=8)
    ap.add_argument("--nursery-seeds", type=int, nargs="+", default=[200, 201, 202])
    ap.add_argument("--train-ticks", type=int, default=60_000)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--ticks", type=int, default=10_000)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE[,...]")
    ap.add_argument("--out", default="snapshots/mr2")
    ap.add_argument("--csv", default="runs/mr2-experiment.json")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--jobs", type=int, default=None)
    a = ap.parse_args()
    csv = ROOT / a.csv
    if a.report_only:
        saved = json.loads(csv.read_text())
        print(f"settings: {saved['settings']}")
        report(saved["rows"])
        return
    extra: dict = {}
    for spec in a.set:
        extra.update(parse_overrides(spec))
    out, seeds = ROOT / a.out, list(range(a.seeds))
    arms = (("control", 0), ("memory", a.slots))
    trains = [(d, src, k, n, a.train_ticks, str(out), extra)
              for d in a.dims for src in NURSERIES[d] for _, k in arms for n in a.nursery_seeds]
    trains.sort(key=lambda t: -t[0])                    # 4D first: the slow ones
    print(f"MR2 experiment: training {len(trains)} nurseries ({a.train_ticks} ticks, Q = {QUEUE}, "
          f"K = 0 vs {a.slots}), physics{physics_tag() or ' (old)'}", flush=True)
    with ProcessPoolExecutor(max_workers=a.jobs) as pool:
        for msg in pool.map(train, trains):
            print(" ", msg, flush=True)
        scores = []
        for d in a.dims:
            for src in NURSERIES[d]:
                for n in a.nursery_seeds:
                    for arm, k in (("control", 0), ("memory", a.slots), ("blind", a.slots)):
                        path = trained_path(out, src, k, n, a.train_ticks)
                        scores.append((d, arm, k, src, n, path, seeds, a.ticks, extra))
        scores.sort(key=lambda t: -t[0])
        print(f"scoring {len(scores)} cells x {a.seeds} seeds x {a.ticks} ticks", flush=True)
        rows = [r for cell in pool.map(score, scores) for r in cell]
    settings = {"dims": a.dims, "slots": a.slots, "nursery_seeds": a.nursery_seeds, "train_ticks": a.train_ticks,
                "seeds": a.seeds, "ticks": a.ticks, "queue": QUEUE, "set": extra, "physics": physics_tag()}
    csv.parent.mkdir(parents=True, exist_ok=True)
    csv.write_text(json.dumps({"settings": settings, "rows": rows}, default=float))
    report(rows)


if __name__ == "__main__":
    main()
