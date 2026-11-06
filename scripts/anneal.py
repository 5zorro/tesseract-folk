"""The anneal nursery (5zorro's "population explosion, then anneal", 2026-11-05):
train nurseries by raising hunger with the population instead of holding
harsh rules fixed, then start play worlds from them and score them with the
dimensions ladder's goals.

Hunger here is one dial, a scale on both kinds of play hunger: nutrient decay
(`nutrient_decay`) and body mass burned (`metabolism_rate`). Lowering only the
first wasn't enough: in 4D, scratch brains still starved their bodies and the
population crashed (probe, 2026-11-06).

Phase 1, hunger. Hunger starts low enough that nobody starves, and no one grows
old with time: only collapses age an NPC (`collapse_age_penalty`), so a third
collapse in a nursery makes an elder, and only elders die. Time aging is off, so
adulthood (mating) starts at birth. The population explodes; whenever it is at
or above `--threshold` at a check, hunger rises by `--factor`.

Deaths lag hunger by thousands of ticks (nutrients run down, then three
collapses), so raising at every check overshot: hunger kept climbing while the
population sat at its cap, then the population crashed to the top-up floor and
never bred again (probe, 2026-11-06). So it's a thermostat that searches: hunger
also falls by the same step when the population drops below `--low` x the
threshold; each change of direction halves the step; and after a change it waits
`--settle` checks for the effect. Hunger settles where hunger deaths hold the
population between the two lines: a carrying capacity. Phase 1 ends once
hunger hasn't changed for `--hold` checks, the step is under 3%, or at
`--phase1-max` of the ticks. The scale stays within `--start-scale` and 2x play.

Phase 2, age. Aging and adulthood come back. Hunger stays where it settled, and
old age falls from `--old-age-start` times the normal lifespan down to it
(geometrically, finishing at 80% of the remaining ticks).

Play worlds then use the normal rules (they never see the anneal's settings).
The fixed-rules nursery and scratch arms come from the ladder's CSV for the same
worlds (`ladder.py --worlds time`), so this only trains and plays the anneal arm.

    python scripts/anneal.py --dims 3 4
    python scripts/anneal.py --report-only --ladder-csv runs/ladder-width.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim import Config, Simulation  # noqa: E402
from sim.snapshot import save_snapshot  # noqa: E402
from sim.simulation import Batch  # noqa: E402
from ladder import NURSERY_RULES, NURSERY_SEEDS, WORLD_SETS, read_csv, report, world  # noqa: E402
from sweep import run_batch  # noqa: E402

HUNGER = ("nutrient_decay", "metabolism_rate")
DEFAULTS = dict(start_scale=0.15, factor=1.5, threshold=150, low=0.5, check=250, settle=3,
                hold=8, phase1_max=0.6, old_age_start=8.0)


def diversity(sim: Simulation) -> float:
    """Average distance of the living brains' weights from their mean (0 = clones)."""
    P = sim.pop
    live = P.live(sim.index)
    if live.size < 2:
        return math.nan
    w = np.concatenate([getattr(P, k)[live].reshape(live.size, -1) for k in ("w1", "b1", "w2", "b2")],
                       axis=1).astype(np.float64)
    return float(np.linalg.norm(w - w.mean(axis=0), axis=1).mean())


class Anneal:
    """Drives one nursery world through the two phases (see the module doc)."""

    def __init__(self, sim: Simulation, ticks: int, p: dict):
        self.sim, self.ticks, self.p = sim, ticks, p
        self.normal = {k: getattr(sim.cfg, k) for k in HUNGER + ("old_age", "adult_age")}
        self.phase, self.still, self.wait, self.trace = 1, 0, 0, []
        self.step, self.direction = math.log(p["factor"]), 0
        self.phase2_start = None
        sim.clock.player_active = False             # no aging with time; collapses still age
        sim.set_rule("adult_age", 0)
        self.set_hunger(p["start_scale"])

    def set_hunger(self, scale: float) -> None:
        self.scale = min(max(scale, self.p["start_scale"]), 2.0)
        for k in HUNGER:
            self.sim.set_rule(k, self.normal[k] * self.scale)

    def check(self) -> None:
        sim, p = self.sim, self.p
        pop = sim.pop.count(sim.index)
        h = sim.stats.history[-1] if sim.stats.history else {}
        self.trace.append({"tick": sim.tick, "phase": self.phase, "population": pop,
                           "hunger": self.scale, "old_age": sim.cfg.old_age,
                           "births": h.get("births", 0), "deaths": h.get("deaths", 0),
                           "collapses": h.get("collapses", 0), "diversity": diversity(sim)})
        if self.phase == 1:
            want = 1 if pop >= p["threshold"] else -1 if pop < p["low"] * p["threshold"] else 0
            before = self.scale
            if self.wait:
                self.wait -= 1
            elif want:
                if self.direction and want != self.direction:
                    self.step /= 2
                self.direction = want
                self.set_hunger(self.scale * math.exp(want * self.step))
                self.wait = p["settle"]
            self.still = 0 if self.scale != before else self.still + 1
            raised = self.scale > p["start_scale"]
            if ((raised and self.still >= p["hold"]) or self.step < math.log(1.03)
                    or sim.tick >= p["phase1_max"] * self.ticks):
                self.start_phase2()
        else:
            span = max(1, 0.8 * (self.ticks - self.phase2_start))
            done = min(1.0, (sim.tick - self.phase2_start) / span)
            old = self.normal["old_age"] * p["old_age_start"] ** (1.0 - done)
            sim.set_rule("old_age", int(round(old)))

    def start_phase2(self) -> None:
        sim = self.sim
        self.phase, self.phase2_start = 2, sim.tick
        self.settled = self.scale
        sim.clock.player_active = True
        sim.set_rule("adult_age", self.normal["adult_age"])
        sim.set_rule("old_age", int(round(self.normal["old_age"] * self.p["old_age_start"])))


def nursery_dir(out: Path, shape: tuple, nseed: int, ticks: int) -> Path:
    dims, size, radius, hidden, _ = shape
    return out / f"d{dims}-s{size}-r{radius:g}-h{hidden}-t{ticks}-n{nseed}"


def train(jobs: list[tuple]) -> list[str]:
    """Anneal these nurseries (one shape, one tick count) as one batch."""
    todo, msgs = [], []
    for shape, nseed, ticks, out, p in jobs:
        path = nursery_dir(out, shape, nseed, ticks)
        trace = path / "anneal.json"
        if trace.exists() and json.loads(trace.read_text())["settings"] == p:
            msgs.append(f"kept {path.name}")
            continue
        sim = Simulation(Config(**{**world(shape), **NURSERY_RULES, "seed": nseed}),
                         log_every=p["check"])
        todo.append((Anneal(sim, ticks, p), path))
    if todo:
        Batch([a.sim for a, _ in todo])
        ticks, check = jobs[0][2], jobs[0][4]["check"]
        for _ in range(ticks // check):
            todo[0][0].sim.run(check)                # steps the whole batch
            for a, _ in todo:
                a.check()
        for a, path in todo:
            if a.phase == 1:
                a.start_phase2()
            save_snapshot(a.sim, path)
            (path / "anneal.json").write_text(json.dumps(
                {"settings": a.p, "settled_hunger": a.settled, "phase2_start": a.phase2_start,
                 "trace": a.trace}, indent=1))
            msgs.append(f"annealed {path.name}: hunger settled at {a.settled:.3f}x play, "
                        f"phase 2 from tick {a.phase2_start}")
    return msgs


def play(jobs: list[tuple]) -> list[dict]:
    runs = []
    for shape, nseed, seed, ticks, nursery_ticks, out in jobs:
        overrides = {**world(shape), "brains_from": str(nursery_dir(out, shape, nseed, nursery_ticks))}
        runs.append((overrides, seed, ticks, 0.5, 250))
    rows = []
    for (shape, nseed, seed, *_), row in zip(jobs, run_batch(runs)):
        dims, size, radius, hidden, rules = shape
        rows.append({"dims": dims, "size": size, "radius": radius, "hidden": hidden, "rules": "",
                     "brains": f"a{nseed}", **row})
    return rows


def pool(fn, groups: list[list], workers: int, label: str) -> list:
    out = []
    with ProcessPoolExecutor(max_workers=min(workers, len(groups))) as ex:
        for fut in as_completed([ex.submit(fn, g) for g in groups]):
            out.extend(fut.result())
            print(f"  {label} {len(out)}", flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", default=[3, 4])
    ap.add_argument("--hidden", type=int, default=16)
    ap.add_argument("--nursery-ticks", type=int, default=20_000)
    ap.add_argument("--nursery-seeds", type=int, nargs="+", default=list(NURSERY_SEEDS))
    ap.add_argument("--ticks", type=int, default=10_000)
    ap.add_argument("--seeds", type=int, default=5)
    for k, v in DEFAULTS.items():
        ap.add_argument(f"--{k.replace('_', '-')}", type=type(v), default=v)
    ap.add_argument("--out", default="snapshots/anneal")
    ap.add_argument("--csv", default="runs/anneal.csv")
    ap.add_argument("--ladder-csv", default="runs/ladder-width.csv",
                    help="scratch and fixed-nursery rows for the same worlds, to compare against")
    ap.add_argument("--jobs", type=int, default=None)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    p = {k: getattr(args, k) for k in DEFAULTS}
    workers = args.jobs or os.cpu_count() or 1
    worlds = WORLD_SETS["time"]
    shapes = [(d, *worlds[d], args.hidden, ()) for d in args.dims]
    out, csv_path = Path(args.out), Path(args.csv)

    if not args.report_only:
        groups = [[(s, n, args.nursery_ticks, out, p)] for s in shapes for n in args.nursery_seeds]
        for msg in pool(train, groups, workers, "nursery"):
            print(f"    {msg}")
        jobs = [(s, n, seed, args.ticks, args.nursery_ticks, out)
                for s in shapes for n in args.nursery_seeds for seed in range(args.seeds)]
        groups = [[j for j in jobs if j[:2] == (s, n)] for s in shapes for n in args.nursery_seeds]
        rows = pool(play, groups, workers, "play")
        rows.sort(key=lambda r: (r["dims"], r["brains"], r["seed"]))
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {len(rows)} runs to {csv_path}")

    anneal_rows = read_csv(csv_path)
    ladder_rows = [r for r in read_csv(Path(args.ladder_csv))
                   if r["hidden"] == args.hidden and r["dims"] in args.dims] if Path(args.ladder_csv).exists() else []
    scratch = [r for r in ladder_rows if r["brains"] == "scratch"]
    fixed = [r for r in ladder_rows if r["brains"] != "scratch"]
    if fixed:
        print("\n== Fixed-rules nursery (ladder) ==")
        report(scratch + fixed)
    print("\n== Anneal nursery ==" + ("" if scratch else " (no ladder CSV: no scratch to compare)"))
    report(scratch + anneal_rows)


if __name__ == "__main__":
    main()
