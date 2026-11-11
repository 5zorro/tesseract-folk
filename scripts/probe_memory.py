"""MR0: do trained brains use their 2 recurrent memory units?
(docs/plan-memory-reaction.md; 5zorro 2026-11-10, "Yes, start MR0".)

Runs M3's sources (each dimension's M2 nurseries at its M2 hunger, top-up
worlds) twice on the same seeds:
- **trained:** the brains as they are;
- **memory0:** the same brains, with their memory units held at 0 every tick
  (the feedback is cut; everything else is identical). Keyed randomness keeps
  the paired worlds identical until behavior differs.

Reported per source: the paired difference in collapses, diet, food types per
life, lowest nutrient, approach excess and population, with how many seeds
agree in sign. From the trained arm, every SAMPLE ticks over the second half:
- **which senses sway the choice:** for each sense group, the mean change in
  the action probabilities (total variation, 0-1) when that group's values
  are swapped between random NPCs (permutation importance, Breiman 2001);
- **does memory hold a state:** each NPC's memory is followed for WINDOW
  ticks after each sample. "within" is how much it varies inside an NPC
  (mean per-NPC std), "between" how much NPCs differ (std of their means); a
  unit that sits at one value per NPC is a fixed bias, not a memory. The lag
  correlations are of the within-NPC part (each NPC's mean removed): how much
  of a change persists 1, 2, 10 and 11 ticks later (negative at odd
  lags and positive at even ones = it flips sign each tick).

    python scripts/probe_memory.py                       # 2D and 4D, 5 seeds x 10,000 ticks
    python scripts/probe_memory.py --dims 4 --source "snapshots/s3/births-n10*-r35"
"""
from __future__ import annotations

import argparse
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim.config import parse_overrides  # noqa: E402
from sim.simulation import Batch  # noqa: E402
from ladder import WORLD_SETS, physics_tag, world  # noqa: E402
from m3_ladder import HIDDEN, HUNGER, NURSERIES, ROOT, hunger_rules  # noqa: E402
from sweep import Run  # noqa: E402

ARMS = ("trained", "memory0")
SAMPLE = 100                 # ticks between sense samples (second half only)
LAGS = (1, 2, 10, 11)        # odd and even: a unit that flips sign each tick is a clock
WINDOW = 30                  # ticks each sampled NPC's memory is followed
LOG_EVERY = 250
METRICS = (("collapses", "collapse_rate"), ("diet", "diet_diversity"), ("types", "zone_types_per_life"),
           ("low nutr", "min_nutrient"), ("approach+", "approach_excess"), ("pop", "pop_mean"),
           ("births", "births"))


@contextmanager
def memory_held_at_zero():
    """Batch.decide_all with every deciding NPC's memory reset to 0 afterwards, so
    next tick's memory inputs are 0. Restored on exit (never leave it patched)."""
    original = Batch.decide_all

    def deciding(self, order, *a, **k):
        actions = original(self, order, *a, **k)
        self.pop.memory[order] = 0.0
        return actions

    Batch.decide_all = deciding
    try:
        yield
    finally:
        Batch.decide_all = original


def action_probs(batch: Batch, slots: np.ndarray, obs: np.ndarray) -> np.ndarray:
    """The action probabilities decide_all would use for these NPCs and senses."""
    P, A = batch.pop, batch.n_actions
    hidden = (np.tanh(np.matmul(P.w1[slots], obs[:, :, None])[:, :, 0] + P.b1[slots])
              if P.w1.shape[1] else obs)
    out = np.matmul(P.w2[slots], hidden[:, :, None])[:, :, 0] + P.b2[slots]
    logits = out[:, :A] / batch._p("action_temperature", P.world[slots])[:, None]
    logits -= logits.max(axis=1, keepdims=True)
    p = np.exp(logits)
    return p / p.sum(axis=1, keepdims=True)


def sensitivity(batch: Batch, slots: np.ndarray, obs: np.ndarray, layout: dict,
                rng: np.random.Generator) -> dict[str, float]:
    """Per sense group: mean total-variation change in the action probabilities
    when the group's values are swapped between random NPCs (0 = ignored)."""
    if len(slots) < 2:
        return {}
    base = action_probs(batch, slots, obs)
    out = {}
    for name, sl in layout.items():
        if name == "bias":
            continue
        swapped = obs.copy()
        swapped[:, sl] = obs[rng.permutation(len(slots)), sl]
        out[name] = float(0.5 * np.abs(action_probs(batch, slots, swapped) - base).sum(axis=1).mean())
    return out


def lag_correlation(pairs: list[tuple[np.ndarray, np.ndarray]]) -> float:
    """Pooled correlation between values and the same NPCs' values later."""
    if not pairs:
        return math.nan
    a = np.concatenate([p[0].ravel() for p in pairs])
    b = np.concatenate([p[1].ravel() for p in pairs])
    if a.size < 3 or a.std() == 0 or b.std() == 0:
        return math.nan
    return float(np.corrcoef(a, b)[0, 1])


def memory_state(series: list[np.ndarray]) -> dict:
    """series: one (ticks, units) array per followed NPC. Within- and between-NPC
    spread, and lag correlations of the within-NPC part (see the docstring)."""
    series = [x for x in series if len(x) > max(LAGS)]
    if not series:
        return {"within": math.nan, "between": math.nan, **{f"lag{k}": math.nan for k in LAGS}}
    means = np.array([x.mean(axis=0) for x in series])
    out = {"within": float(np.mean([x.std(axis=0).mean() for x in series])),
           "between": float(means.std(axis=0).mean()), "level": float(np.mean(np.abs(means)))}
    for k in LAGS:
        out[f"lag{k}"] = lag_correlation([(x[:-k] - x.mean(axis=0), x[k:] - x.mean(axis=0)) for x in series])
    return out


def job(task: tuple) -> dict:
    """One source and arm: every seed in one batch."""
    dims, source, arm, seeds, ticks, extra = task
    overrides = {**world((dims, *WORLD_SETS["time"][dims], HIDDEN, ())), **hunger_rules(HUNGER[dims]),
                 **extra, "brains_from": str(ROOT / source)}
    runs = [Run(dict(overrides), s, ticks, 0.5, LOG_EVERY) for s in seeds]
    batch = Batch([r.sim for r in runs])
    layout = runs[0].sim.sense_layout()
    rng = np.random.default_rng(seeds[0])
    sens: dict[str, list[float]] = {}
    follow: dict[int, list] = {}                     # NPC id -> memory each tick of its window
    until = 0
    series: list[np.ndarray] = []
    late = ticks // 2
    with memory_held_at_zero() if arm == "memory0" else _nothing():
        for _ in range(ticks):
            for r in runs:
                r.before_tick()
            batch.step()
            for r in runs:
                r.after_tick()
            if arm != "trained" or batch.tick < late:
                continue
            P = batch.pop
            live = P.live()
            if batch.tick % SAMPLE == 0 and live.size:
                for name, v in sensitivity(batch, live, batch.sense_slots(live), layout, rng).items():
                    sens.setdefault(name, []).append(v)
                series += [np.array(v) for v in follow.values()]
                follow, until = {int(i): [] for i in P.id[live]}, batch.tick + WINDOW
            if batch.tick < until:
                for i, s in zip(P.id[live], live):
                    if int(i) in follow:
                        follow[int(i)].append(P.memory[s].copy())
    series += [np.array(v) for v in follow.values()]
    return {"dims": dims, "source": source, "arm": arm, "rows": [r.result() for r in runs],
            "sens": {k: float(np.mean(v)) for k, v in sens.items()}, "state": memory_state(series)}


@contextmanager
def _nothing():
    yield


def label(source: str) -> str:
    return Path(source).name.replace("metabolism_rate", "m").replace("nutrient_decay", "nd")


def report(results: list[dict], seeds: list[int]) -> None:
    by = {(r["dims"], r["source"], r["arm"]): r for r in results}
    for dims in sorted({r["dims"] for r in results}):
        print(f"\n=== {dims}D (hunger {HUNGER[dims]}x, {len(seeds)} seeds; memory0 minus trained, "
              f"seeds agreeing in sign) ===")
        print(f"{'source':34s} " + " ".join(f"{m[0]:>17s}" for m in METRICS))
        sources = sorted({r["source"] for r in results if r["dims"] == dims})
        for source in sources:
            t, z = by.get((dims, source, "trained")), by.get((dims, source, "memory0"))
            if not (t and z):
                continue
            cells = []
            for _, key in METRICS:
                a = np.array([row[key] for row in t["rows"]], float)
                b = np.array([row[key] for row in z["rows"]], float)
                d = b - a
                ok = ~np.isnan(d)
                pos, neg = int((d[ok] > 0).sum()), int((d[ok] < 0).sum())
                cells.append(f"{np.nanmean(a):7.3g}{np.nanmean(d):+7.2g} {max(pos, neg)}/{ok.sum()}")
            print(f"{label(source):34s} " + " ".join(f"{c:>17s}" for c in cells))
        print(f"\nWhich senses sway the choice ({dims}D, trained arm; mean action-probability change, 0-1):")
        for source in sources:
            t = by.get((dims, source, "trained"))
            if not t:
                continue
            ranked = sorted(t["sens"].items(), key=lambda kv: -kv[1])
            top = ", ".join(f"{k} {v:.3f}" for k, v in ranked[:6])
            mem_rank = [k for k, _ in ranked].index("memory") + 1 if "memory" in t["sens"] else 0
            st = t["state"]
            print(f"  {label(source):34s} memory {t['sens'].get('memory', math.nan):.3f} "
                  f"(rank {mem_rank}/{len(ranked)}); |level| {st['level']:.2f}, within {st['within']:.3f}, "
                  f"between {st['between']:.3f}; within r at lag " + ", ".join(f"{k}: {st[f'lag{k}']:+.2f}" for k in LAGS))
            print(f"  {'':34s} top: {top}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", default=[2, 4])
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--ticks", type=int, default=10_000)
    ap.add_argument("--source", action="append", default=[], metavar="GLOB",
                    help="nursery folders (globs under the repo); default: M2's nurseries per dimension")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE[,...]")
    ap.add_argument("--jobs", type=int, default=None)
    a = ap.parse_args()
    extra: dict = {}
    for spec in a.set:
        extra.update(parse_overrides(spec))
    seeds = list(range(a.seeds))
    tasks = []
    for d in a.dims:
        found = ([str(p.relative_to(ROOT)) for g in a.source for p in sorted(ROOT.glob(g))]
                 if a.source else NURSERIES[d])
        tasks += [(d, s, arm, seeds, a.ticks, extra) for s in found for arm in ARMS]
    print(f"MR0 memory probe: {len(tasks)} jobs, physics{physics_tag() or ' (old)'}, extra {extra}", flush=True)
    with ProcessPoolExecutor(max_workers=a.jobs) as pool:
        results = list(pool.map(job, tasks))
    report(results, seeds)


if __name__ == "__main__":
    main()
