"""O1's experiment (docs/plan-occupations.md): can evolution make workers punctual?

Two arms, both warm-started from each dimension's M2 nursery pools
(m3_ladder.NURSERIES) with the reaction queue on (Q = 3) and no memory:
- **control:** no posts;
- **posts:** --posts occupation posts per world (shifts, the fallback walk,
  frazzled, wages; Config defaults otherwise).
Each pool trains --nursery-seeds nurseries per arm (NURSERY_RULES, the
dimension's M2 hunger, --train-ticks), paired by (pool, nursery seed).

Scoring (M2's top-up worlds, --seeds x --ticks):
- control brains without posts (**control**) and with posts (**naive**:
  brains that never had a job, their work senses widened in at zero weight);
- the posts arm's brains with posts (**posts**).
Work measures over the second half of scoring, per shift start (on time +
late): on time, left mid-shift, fallback-walk ticks, paid. Compared by
nursery, not by scoring seed (MR2's lesson).

    python scripts/o1_occupations.py                  # 2D and 4D, 10 posts, 3 nurseries per pool
    python scripts/o1_occupations.py --report-only
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
from sim.simulation import Batch  # noqa: E402
from sim.snapshot import save_snapshot  # noqa: E402
from sim.work import WORK_COUNTERS  # noqa: E402
from ladder import physics_tag  # noqa: E402
from m3_ladder import NURSERIES, ROOT  # noqa: E402
from mr1_ladder import nursery_rules, play_rules, reusable  # noqa: E402
from sweep import Run  # noqa: E402

LOG_EVERY = 250
QUEUE = 3
METRICS = (("collapses", "collapse_rate"), ("diet", "diet_diversity"), ("types", "zone_types_per_life"),
           ("low nutr", "min_nutrient"), ("pop", "pop_mean"), ("births", "births"))
WORK = (("on time", "on_time_share"), ("left/shift", "left_per_shift"), ("walk/shift", "walk_per_shift"),
        ("paid", "paid_share"), ("shifts", "shifts"))


def trained_path(out: Path, source: str, posts: int, nseed: int, ticks: int) -> Path:
    return out / f"{Path(source).name}-q{QUEUE}-p{posts}-n{nseed}-t{ticks}{physics_tag()}"


def train(task: tuple) -> str:
    dims, source, posts, nseed, ticks, out, extra = task
    path = trained_path(Path(out), source, posts, nseed, ticks)
    rules = nursery_rules(dims, QUEUE, nseed, {**extra, "n_posts": posts})
    if reusable(path, rules, source, ticks):
        return f"kept {path.name}"
    sim = Simulation(Config(**rules), log_every=1000)
    seed_brains(sim, load_brain_pool(ROOT / source))
    sim.run(ticks)
    save_snapshot(sim, path)
    (path / "mr1.json").write_text(json.dumps({"source": source, "posts": posts, "ticks": ticks}))
    return f"trained {path.name}"


def work_measures(history: list[dict], since: int) -> dict:
    """Per shift start (on time + late) over the rows after `since`."""
    late = [h for h in history if h["tick"] > since]
    n = {k: sum(h.get(k, 0) for h in late) for k in WORK_COUNTERS}
    shifts = n["work_on_time"] + n["work_late"]
    per = (lambda x: x / shifts) if shifts else (lambda x: float("nan"))
    return {"shifts": shifts, "on_time_share": per(n["work_on_time"]), "left_per_shift": per(n["work_left"]),
            "walk_per_shift": per(n["work_walk_ticks"]), "paid_share": per(n["work_paid"])}


def score(task: tuple) -> list[dict]:
    """One trained nursery in one arm: every seed in one batch."""
    dims, arm, posts, source, nseed, brains, seeds, ticks, extra = task
    overrides = {**play_rules(dims, QUEUE, {**extra, "n_posts": posts}), "brains_from": str(brains)}
    runs = [Run(dict(overrides), s, ticks, 0.5, LOG_EVERY) for s in seeds]
    batch = Batch([r.sim for r in runs])
    for _ in range(ticks):
        for r in runs:
            r.before_tick()
        batch.step()
        for r in runs:
            r.after_tick()
    out = []
    for r in runs:
        row = {"dims": dims, "arm": arm, "source": Path(source).name, "nseed": nseed, **r.result()}
        if posts:
            row.update(work_measures(r.sim.stats.history, ticks // 2))
        out.append(row)
    return out


def by_nursery(rows: list[dict], key: str) -> dict:
    cells: dict = {}
    for r in rows:
        cells.setdefault((r["source"], r["nseed"]), []).append(r[key])
    return {k: float(np.nanmean(v)) if np.isfinite(v).any() else float("nan") for k, v in cells.items()}


def report(rows: list[dict]) -> None:
    for dims in sorted({r["dims"] for r in rows}):
        mine = [r for r in rows if r["dims"] == dims]
        arm = {a: [r for r in mine if r["arm"] == a] for a in ("control", "naive", "posts")}
        n = len({(r["source"], r["nseed"]) for r in mine})
        print(f"\n=== {dims}D, Q = {QUEUE}: {n} nurseries; mean over nurseries, "
              f"then change and nurseries down/up ===")
        print(f"{'arm':14s} " + " ".join(f"{m[0]:>20s}" for m in METRICS))
        for name, base in (("control", None), ("naive", "control"), ("posts", "control")):
            if not arm[name]:
                continue
            cells = []
            for _, key in METRICS:
                mean = by_nursery(arm[name], key)
                text = f"{np.nanmean(list(mean.values())):8.3g}"
                if base and arm[base]:
                    ref = by_nursery(arm[base], key)
                    d = np.array([mean[k] - ref[k] for k in mean if k in ref], float)
                    d = d[np.isfinite(d)]
                    if d.size:
                        text += f" {d.mean():+7.2g} {(d < 0).sum()}/{(d > 0).sum()}"
                cells.append(text)
            label = name if not base else f"{name} - {base[:4]}"
            print(f"{label:14s} " + " ".join(f"{c:>20s}" for c in cells))
        print(f"{'work':14s} " + " ".join(f"{m[0]:>14s}" for m in WORK))
        for name in ("naive", "posts"):
            if arm[name]:
                print(f"{name:14s} " + " ".join(
                    f"{np.nanmean(list(by_nursery(arm[name], key).values())):14.3g}" for _, key in WORK))
        if arm["naive"] and arm["posts"]:
            a, b = by_nursery(arm["posts"], "on_time_share"), by_nursery(arm["naive"], "on_time_share")
            d = [a[k] - b[k] for k in a if k in b and np.isfinite(a[k] - b[k])]
            print("on time, posts minus naive, per nursery: " + " ".join(f"{x:+.2f}" for x in d)
                  + f"  ({sum(x > 0 for x in d)}/{len(d)} up)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", default=[2, 4])
    ap.add_argument("--posts", type=int, default=10)
    ap.add_argument("--nursery-seeds", type=int, nargs="+", default=[200, 201, 202])
    ap.add_argument("--train-ticks", type=int, default=60_000)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--ticks", type=int, default=10_000)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE[,...]")
    ap.add_argument("--out", default="snapshots/o1")
    ap.add_argument("--csv", default="runs/o1-occupations.json")
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
    trains = [(d, src, p, n, a.train_ticks, str(out), extra)
              for d in a.dims for src in NURSERIES[d] for p in (0, a.posts) for n in a.nursery_seeds]
    trains.sort(key=lambda t: -t[0])                    # 4D first: the slow ones
    print(f"O1 experiment: training {len(trains)} nurseries ({a.train_ticks} ticks, Q = {QUEUE}, "
          f"posts 0 vs {a.posts}), physics{physics_tag() or ' (old)'}", flush=True)
    with ProcessPoolExecutor(max_workers=a.jobs) as pool:
        for msg in pool.map(train, trains):
            print(" ", msg, flush=True)
        scores = []
        for d in a.dims:
            for src in NURSERIES[d]:
                for n in a.nursery_seeds:
                    control = trained_path(out, src, 0, n, a.train_ticks)
                    posts = trained_path(out, src, a.posts, n, a.train_ticks)
                    scores += [(d, "control", 0, src, n, control, seeds, a.ticks, extra),
                               (d, "naive", a.posts, src, n, control, seeds, a.ticks, extra),
                               (d, "posts", a.posts, src, n, posts, seeds, a.ticks, extra)]
        scores.sort(key=lambda t: -t[0])
        print(f"scoring {len(scores)} cells x {a.seeds} seeds x {a.ticks} ticks", flush=True)
        rows = [r for cell in pool.map(score, scores) for r in cell]
    settings = {"dims": a.dims, "posts": a.posts, "nursery_seeds": a.nursery_seeds, "train_ticks": a.train_ticks,
                "seeds": a.seeds, "ticks": a.ticks, "queue": QUEUE, "set": extra, "physics": physics_tag()}
    csv.parent.mkdir(parents=True, exist_ok=True)
    csv.write_text(json.dumps({"settings": settings, "rows": rows}, default=float))
    report(rows)


if __name__ == "__main__":
    main()
