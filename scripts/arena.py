"""The arena (5zorro, 2026-11-07): de-noise the hall of fame so top-ups copy
objectively good brains, not lucky ones.

One life is a noisy score (plan-m2 R3, R10, R13). Here a nursery fills its hall
of fame as usual, then every entry is raced on *shared scenarios*:

- **Common random numbers:** a scenario is a short test world with a fixed seed.
  Every brain plays the same scenarios, as a clonal world (all its NPCs carry
  that exact brain), so map and draw luck is the same for every brain and
  cancels when they are compared.
- **Successive halving** (racing; Jamieson & Talwalkar 2016, F-Race, Birattari
  2002, cited from memory): all entries play the first `--stages` scenarios,
  the better half plays the next ones, and so on. Clear losers stop early;
  tests go to telling the contenders apart.
- **Tested harsher than bred:** scenarios use their own rules (`--test`, e.g. 1x
  hunger) while the nursery breeds under `--breed` (e.g. 4D's 0.36x, where births
  happen but nothing collapses, R13). Scenario founders don't age from collapses
  (`collapse_age_penalty=0`) and the test is shorter than old age, so no founder
  dies and no bad record goes missing.
- **Score:** founders' collapses per 1,000 ticks, as an excess over the field
  (a scenario's mean, corrected for how much better than the field that
  scenario's players already proved; lower is better).
- **Write-back:** the hall of fame keeps the top `--keep` entries (stage reached,
  then mean excess), their track record set to the arena's (lives = scenarios
  played, excess_sum = summed excess), so top-ups pick them by that merit. The
  rest are dropped. The nursery then runs on and refills; the next race
  re-tests everyone on new scenarios.

Arms: `arena` (race after every round) and `plain` (same nursery seeds, no race).
Each round's checkpoint is scored on fresh play worlds (`--play` rules, the M2
goals), and each arm's curve is fitted to y = y_inf + (y0 - y_inf) exp(-t / tau)
to project the time to equilibrium (~3 tau).

    python scripts/arena.py --dims 4 --breed nutrient_decay=0.00108,metabolism_rate=0.0036 \
        --play nutrient_decay=0.00108,metabolism_rate=0.0036
    python scripts/arena.py --dims 4 --report-only

It lives outside `sim/` and changes no rule, so both engines stay as they are.
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
from sim.config import parse_overrides  # noqa: E402
from sim.simulation import Batch  # noqa: E402
from sim.snapshot import load_snapshot, save_snapshot  # noqa: E402
from ladder import LATE_FROM, LOG_EVERY, NURSERY_RULES, WORLD_SETS, verdicts, world  # noqa: E402
from sweep import run_batch  # noqa: E402

ARMS = ("plain", "arena", "persist")
RACED = ("arena", "persist")    # arms that race; persist keeps the verdicts (R14)
TEST_RULES = {"collapse_age_penalty": 0, "initial_npcs": 30}
METRICS = ("collapse_rate", "min_nutrient", "diet_diversity", "zone_types_per_life", "approach_excess")


# ================================================================ the race
def scenario_seed(nseed: int, rnd: int, index: int) -> int:
    """Shared by every brain in one race (common random numbers)."""
    return 50_000_000 + 100_000 * nseed + 1_000 * rnd + index


def play_scenarios(brains: list, base: dict, seeds: list[int], ticks: int) -> np.ndarray:
    """Founders' collapses per 1,000 ticks, one row per brain, one column per seed."""
    sims = []
    for brain in brains:
        for seed in seeds:
            sim = Simulation(Config(**{**base, "seed": seed}), log_every=max(ticks, 1))
            for npc in sim.npcs:                 # a clonal world: every founder is this brain
                npc.brain = brain
                npc.source = -1
            sims.append(sim)
    Batch(sims).run(ticks)
    rates = np.empty(len(sims))
    for i, sim in enumerate(sims):
        founders = [n for n in sim.npcs if n.origin == ""]
        if len(founders) != sim.cfg.initial_npcs:
            raise RuntimeError(f"a scenario lost founders ({len(founders)} of {sim.cfg.initial_npcs}); "
                               "shorten --test-ticks below old_age")
        rates[i] = 1000.0 * sum(n.collapses for n in founders) / max(sum(n.lifetime for n in founders), 1)
    return rates.reshape(len(brains), len(seeds))


def race(entries: list[dict], base: dict, stages: list[int], ticks: int, nseed: int, rnd: int,
         log: list | None = None) -> list[dict]:
    """Successive halving on shared scenarios. Returns one record per entry:
    {"stage", "excess": [per scenario]}, in the entries' order. `log` collects
    each stage's raw grid (players x scenarios) for the luck analysis."""
    records = [{"stage": 0, "excess": []} for _ in entries]
    alive = list(range(len(entries)))
    index = 0
    for stage, count in enumerate(stages, 1):
        if not alive:
            break
        seeds = [scenario_seed(nseed, rnd, index + k) for k in range(count)]
        index += count
        raw = play_scenarios([entries[i]["brain"] for i in alive], base, seeds, ticks)
        if log is not None:
            log.append({"players": list(alive), "seeds": seeds, "raw": raw.tolist()})
        # The field's mean on a later scenario is estimated from its players'
        # mean, corrected by how much better than the field they already proved.
        proved = np.array([np.mean(records[i]["excess"]) if records[i]["excess"] else 0.0 for i in alive])
        baseline = raw.mean(axis=0) - proved.mean()
        for row, i in enumerate(alive):
            records[i]["excess"].extend((raw[row] - baseline).tolist())
            records[i]["stage"] = stage
        if stage < len(stages):
            alive.sort(key=lambda i: np.mean(records[i]["excess"]))
            alive = alive[:max(1, len(alive) // 2)]
    return records


def ranked(records: list[dict]) -> list[int]:
    """Entries by stage reached (higher first), then mean excess (lower first)."""
    return sorted(range(len(records)), key=lambda i: (-records[i]["stage"], np.mean(records[i]["excess"])))


def write_back(sim, records: list[dict], keep: int, persist: bool = False) -> dict:
    """Keep the race's top `keep` with their race records. `persist` (arm
    persist): mark them raced, so nursery copies' lives don't join their record,
    the 5-copies floor can't drop them and newcomers can't push them out
    (sim._rank_hall_of_fame); an entry raced before adds this race to its record."""
    order = ranked(records)[:keep]
    kept = []
    for i in order:
        entry = dict(sim.hall_of_fame[i])
        lives, excess = float(len(records[i]["excess"])), float(np.sum(records[i]["excess"]))
        if persist and entry.get("raced"):
            lives, excess = entry["lives"] + lives, entry["excess_sum"] + excess
        entry["lives"], entry["excess_sum"] = lives, excess
        if persist:
            entry["raced"] = 1.0
        kept.append(entry)
    before = len(sim.hall_of_fame)
    sim.hall_of_fame = kept
    return {"raced": before, "kept": len(kept),
            "best_excess": float(np.mean(records[order[0]]["excess"])) if order else math.nan}


# ============================================================== nurseries
def shape_of(dims: int, hidden: int) -> tuple:
    return (dims, *WORLD_SETS["time"][dims], hidden, ())


def checkpoint(out: Path, arm: str, nseed: int, rnd: int) -> Path:
    return out / f"{arm}-n{nseed}-r{rnd}"


def race_log(sim, records: list[dict], grids: list, keep: int | None) -> dict:
    """What a race saw, for the luck analysis: each entry's merit going in (the
    nursery's own, untested ranking), its race record, and the raw grids."""
    prior = sim.cfg.hall_of_fame_prior_lives
    return {"tick": sim.tick, "keep": keep,
            "entries": [{"id": int(e["id"]), "generation": int(e["generation"]), "lives": float(e["lives"]),
                         "merit": -float(e["excess_sum"]) / (float(e["lives"]) + prior)}
                        for e in sim.hall_of_fame],
            "records": records, "grids": grids}


def nursery(job: tuple) -> list[str]:
    arm, nseed, args = job
    shape = shape_of(args["dims"], args["hidden"])
    base = world(shape)
    out, start = Path(args["out"]), args["start_round"]
    if start:
        sim = load_snapshot(checkpoint(out, arm, nseed, start), log_every=1000)
    else:
        sim = Simulation(Config(**{**base, **NURSERY_RULES, **args["breed"], "seed": nseed}), log_every=1000)
    test = {**base, **args["test"], **TEST_RULES}
    msgs = []
    for rnd in range(start + 1, args["rounds"] + 1):
        sim.run(args["round_ticks"])
        note, log = "", None
        if arm in RACED and sim.hall_of_fame:
            grids: list = []
            records = race(sim.hall_of_fame, test, args["stages"], args["test_ticks"], nseed, rnd, grids)
            log = race_log(sim, records, grids, args["keep"])
            info = write_back(sim, records, args["keep"], persist=arm == "persist")
            note = f" (raced {info['raced']}, kept {info['kept']}, best excess {info['best_excess']:+.2f})"
        path = checkpoint(out, arm, nseed, rnd)
        save_snapshot(sim, path)
        if log:
            (path / "race.json").write_text(json.dumps(log))
        msgs.append(f"{arm} n{nseed} round {rnd} at {sim.tick:,}{note}")
    return msgs


def measure(job: tuple) -> str:
    """Race a checkpoint's hall of fame without writing back (every entry plays
    every scenario: one stage), to see how much of its ranking is luck."""
    path, nseed, rnd, args = job
    sim = load_snapshot(path, log_every=1000)
    if not sim.hall_of_fame:
        return f"{path.name}: empty hall of fame"
    test = {**world(shape_of(args["dims"], args["hidden"])), **args["test"], **TEST_RULES}
    grids: list = []
    records = race(sim.hall_of_fame, test, [args["measure_scenarios"]], args["test_ticks"], nseed,
                   1000 + rnd, grids)                    # other seeds than the training races
    (path / "measure.json").write_text(json.dumps(race_log(sim, records, grids, None)))
    return f"measured {path.name}"


# ================================================================== luck
def components(raw: np.ndarray) -> dict:
    """Two-way split of a brains x scenarios grid (no replication): variance of
    brain quality, of shared scenario luck (cancels with common random numbers),
    and the leftover luck that doesn't."""
    B, S = raw.shape
    m = raw.mean()
    bm, sm = raw.mean(axis=1), raw.mean(axis=0)
    resid = raw - bm[:, None] - sm[None, :] + m
    ms_r = float((resid ** 2).sum() / max((B - 1) * (S - 1), 1))
    ms_b = float(S * ((bm - m) ** 2).sum() / max(B - 1, 1))
    ms_s = float(B * ((sm - m) ** 2).sum() / max(S - 1, 1))
    vb, vs = max((ms_b - ms_r) / S, 0.0), max((ms_s - ms_r) / B, 0.0)
    return {"brain": vb, "scenario": vs, "leftover": ms_r,
            "r_shared": vb / (vb + ms_r) if vb + ms_r > 0 else math.nan,
            "r_alone": vb / (vb + vs + ms_r) if vb + vs + ms_r > 0 else math.nan}


def tests_for(r: float, target: float = 0.8) -> float:
    """Spearman-Brown: tests whose mean has reliability `target`, if one has r."""
    if not r > 0:
        return math.inf
    return target * (1 - r) / ((1 - target) * r)


def spearman(a, b) -> float:
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    if np.std(ra) == 0 or np.std(rb) == 0:
        return math.nan
    return float(np.corrcoef(ra, rb)[0, 1])


def luck_rows(out: Path) -> list[dict]:
    """One row per race log (training races and measure-only races)."""
    rows = []
    for kind, name in (("arena", "race.json"), ("plain", "measure.json")):
        for p in sorted(out.glob(f"{kind}-n*-r*/{name}")):
            log = json.loads(p.read_text())
            grid = log["grids"][0]
            raw = np.array(grid["raw"])
            c = components(raw)
            merit = np.array([log["entries"][i]["merit"] for i in grid["players"]])
            quality = -raw.mean(axis=1)                  # fewer collapses = better
            half = len(merit) // 2
            agree = (len(set(np.argsort(-merit)[:half]) & set(np.argsort(-quality)[:half])) / half
                     if half else math.nan)
            rows.append({"kind": "raced" if kind == "arena" else "untested",
                         "round": int(p.parent.name.rsplit("-r", 1)[1]), "brains": len(merit),
                         "scenarios": raw.shape[1], **c, "merit_vs_race": spearman(merit, quality),
                         "top_half": agree})
    return rows


def luck_report(out: Path) -> None:
    rows = luck_rows(out)
    if not rows:
        return
    print("\nLuck in the hall of fame. One scenario's score = brain quality + shared luck (the same for"
          "\nevery brain on that scenario; cancels in a race) + leftover luck. r = the share of one score"
          "\nthat is quality: 'shared' when brains are compared on common scenarios, 'alone' for one life"
          "\nin its own world (an untested hall of fame). Tests = lives or scenarios for 0.8 reliability"
          "\n(Spearman-Brown). merit~race = rank correlation of the hall of fame's own merit with the race;"
          "\ntop half = share of its top half the race also puts there (50% = chance). 'raced' rows use"
          "\nstage 1 of each training race (the arena arm: half of it was raced before).")
    print(f"{'hall':>8} {'round':>5} {'brains':>6} {'quality':>7} {'shared':>7} {'leftover':>8} "
          f"{'r shared':>8} {'r alone':>7} {'tests (shared/alone)':>20} {'merit~race':>10} {'top half':>8}")
    for kind in ("untested", "raced"):
        for rnd in sorted({r["round"] for r in rows if r["kind"] == kind}):
            cell = [r for r in rows if r["kind"] == kind and r["round"] == rnd]
            m = {k: float(np.nanmean([r[k] for r in cell])) for k in cell[0] if k != "kind"}
            print(f"{kind:>8} {rnd:>5} {m['brains']:6.0f} {m['brain']:7.2f} {m['scenario']:7.2f} "
                  f"{m['leftover']:8.2f} {m['r_shared']:8.2f} {m['r_alone']:7.2f} "
                  f"{tests_for(m['r_shared']):9.1f}/{tests_for(m['r_alone']):<10.1f} "
                  f"{m['merit_vs_race']:+10.2f} {m['top_half']:8.0%}")


# ================================================================== play
def play(job: tuple) -> list[dict]:
    arm, nseed, rnd, args = job
    shape = shape_of(args["dims"], args["hidden"])
    overrides = {**world(shape), **args["play"]}
    if arm != "scratch":
        overrides["brains_from"] = str(checkpoint(Path(args["out"]), arm, nseed, rnd))
    runs = [(dict(overrides), s, args["play_ticks"], LATE_FROM, LOG_EVERY) for s in range(args["play_seeds"])]
    rows = []
    for s, row in enumerate(run_batch(runs)):
        rows.append({"arm": arm, "nursery": nseed, "round": rnd, "ticks": rnd * args["round_ticks"],
                     "seed": s, **row})
    return rows


# ================================================================ report
def fit(t: np.ndarray, y: np.ndarray) -> dict:
    """y = a + b exp(-t / tau): least squares on a grid of tau. Returns y_inf (a),
    tau, and whether tau sits on the grid's edge (no clear equilibrium)."""
    best = None
    span = float(t.max() - t.min()) or 1.0
    for tau in np.geomspace(span / 50, span * 20, 400):
        X = np.column_stack([np.ones_like(t), np.exp(-t / tau)])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        err = float(np.sum((X @ coef - y) ** 2))
        if best is None or err < best[0]:
            best = (err, tau, coef)
    _, tau, (a, b) = best
    edge = tau <= span / 49 or tau >= span * 19
    return {"y_inf": float(a), "tau": float(tau), "t95": float(3 * tau), "edge": edge}


def report(rows: list[dict], args: dict) -> None:
    scratch = {r["seed"]: r for r in rows if r["arm"] == "scratch"}
    print(f"\n{args['dims']}D arena vs plain nursery: play worlds from each round's checkpoint "
          f"(means over nurseries x seeds; scratch collapses "
          f"{np.mean([r['collapse_rate'] for r in scratch.values()]):.2f})")
    print(f"{'arm':>6} {'round':>5} {'ticks':>8} {'clpse':>5} {'nutr':>5} {'diet':>5} {'types':>11} "
          f"{'excess':>7}  goals (collapses, nutrient, diet, types, seeks diet)")
    curves = {}
    for arm in [a for a in ARMS if any(r["arm"] == a for r in rows)]:
        for rnd in sorted({r["round"] for r in rows if r["arm"] == arm}):
            cell = [r for r in rows if r["arm"] == arm and r["round"] == rnd]
            m = {k: float(np.nanmean([r[k] for r in cell])) for k in METRICS}
            types = [r["zone_types_per_life"] for r in cell]
            se = float(np.nanstd(types) / math.sqrt(max(len(types), 1)))
            ladder_rows = ([{**r, "dims": args["dims"], "hidden": args["hidden"], "brains": f"n{r['nursery']}"}
                            for r in cell] +
                           [{**r, "dims": args["dims"], "hidden": args["hidden"], "brains": "scratch"}
                            for r in scratch.values()])
            v = verdicts(ladder_rows)
            marks = " ".join("Y" if ok else "." for ok in v[0]["goals"].values()) if v else "-"
            print(f"{arm:>6} {rnd:>5} {cell[0]['ticks']:>8,} {m['collapse_rate']:5.2f} {m['min_nutrient']:5.2f} "
                  f"{m['diet_diversity']:5.2f} {m['zone_types_per_life']:5.2f}+-{se:4.2f} "
                  f"{m['approach_excess']:7.3f}  {marks}")
            curves.setdefault(arm, []).append((cell[0]["ticks"], m, rnd))
    print("\nEquilibrium projection, y = y_inf + (y0 - y_inf) exp(-t / tau); ~95% there at 3 tau:")
    for arm, points in curves.items():
        if len(points) < 3:
            print(f"  {arm}: needs 3+ rounds")
            continue
        t = np.array([p[0] for p in points], dtype=float)
        for key, label in (("zone_types_per_life", "types"), ("collapse_rate", "collapses"),
                           ("diet_diversity", "diet")):
            y = np.array([p[1][key] for p in points])
            f = fit(t, y)
            peak = int(np.argmax(y) if key != "collapse_rate" else np.argmin(y))
            shape = "" if peak == len(y) - 1 else f"; best at round {points[peak][2]}, then worse"
            where = "no clear equilibrium (tau at the fit's edge)" if f["edge"] else \
                f"-> {f['y_inf']:.2f}, tau {f['tau']:,.0f} ticks, 95% by ~{f['t95']:,.0f}"
            if not f["edge"] and f["t95"] > 2 * t.max():
                where += " (beyond 2x the data: a guess)"
            print(f"  {arm:>6} {label:>9}: {where}{shape}")


def write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def read(path: Path) -> list[dict]:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            if k != "arm":
                try:
                    r[k] = float(v) if v not in ("", "nan") else math.nan
                except ValueError:
                    pass
        for k in ("nursery", "round", "ticks", "seed"):
            r[k] = int(r[k])
    return rows


def rules(spec: str) -> dict:
    return parse_overrides(spec) if spec else {}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, default=4, choices=sorted(WORLD_SETS["time"]))
    ap.add_argument("--hidden", type=int, default=16)
    ap.add_argument("--breed", default="", help="nursery rules (KEY=VALUE,...), on top of the nursery's own")
    ap.add_argument("--test", default="", help="scenario rules (default: today's defaults, 1x hunger)")
    ap.add_argument("--play", default="", help="play-world rules for scoring checkpoints")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--round-ticks", type=int, default=20_000)
    ap.add_argument("--nursery-seeds", type=int, nargs="+", default=[100, 101, 102, 103])
    ap.add_argument("--stages", type=int, nargs="+", default=[2, 2, 4],
                    help="scenarios per stage; the field halves after each but the last")
    ap.add_argument("--keep", type=int, default=10, help="entries kept after a race")
    ap.add_argument("--test-ticks", type=int, default=1200, help="scenario length (below old_age)")
    ap.add_argument("--play-seeds", type=int, default=3)
    ap.add_argument("--play-ticks", type=int, default=10_000)
    ap.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    ap.add_argument("--out", default="snapshots/arena")
    ap.add_argument("--csv", default=None, help="default runs/arena-{dims}d.csv")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--start-round", type=int, default=0,
                    help="resume each nursery from this round's checkpoint (extends a run)")
    ap.add_argument("--play-every", type=int, default=1, help="score every Nth round (and the last)")
    ap.add_argument("--measure", action="store_true",
                    help="race the plain arm's checkpoints without writing back (luck in an untested hall of fame)")
    ap.add_argument("--measure-scenarios", type=int, default=4)
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()
    if a.rounds < 1 or a.round_ticks < 1 or a.keep < 1 or not a.stages or min(a.stages) < 1:
        ap.error("--rounds, --round-ticks, --keep and --stages must be positive")
    if a.test_ticks >= Config().old_age:
        ap.error("--test-ticks must be below old_age, or founders die and their records go missing")
    try:
        args = {"dims": a.dims, "hidden": a.hidden, "breed": rules(a.breed), "test": rules(a.test),
                "play": rules(a.play), "rounds": a.rounds, "round_ticks": a.round_ticks, "stages": a.stages,
                "keep": a.keep, "test_ticks": a.test_ticks, "play_seeds": a.play_seeds,
                "play_ticks": a.play_ticks, "out": a.out, "start_round": a.start_round,
                "measure_scenarios": a.measure_scenarios}
    except ValueError as e:
        ap.error(str(e))
    if not 0 <= a.start_round < a.rounds or a.play_every < 1 or a.measure_scenarios < 2:
        ap.error("--start-round must be below --rounds; --play-every >= 1; --measure-scenarios >= 2")
    path = Path(a.csv or f"runs/arena-{a.dims}d.csv")
    out = Path(a.out)
    if a.measure:
        jobs = [(p, int(p.name.split("-n")[1].split("-r")[0]), int(p.name.rsplit("-r", 1)[1]), args)
                for p in sorted(out.glob("plain-n*-r*")) if not (p / "measure.json").exists()]
        jobs = [j for j in jobs if j[2] == 1 or j[2] % a.play_every == 0]     # --play-every thins it
        if jobs:
            with ProcessPoolExecutor(min(a.jobs, len(jobs))) as pool:
                for fut in as_completed([pool.submit(measure, j) for j in jobs]):
                    print("  ", fut.result(), flush=True)
        luck_report(out)
        return
    if not a.report_only:
        jobs = [(arm, n, args) for arm in a.arms for n in a.nursery_seeds]
        jobs.sort(key=lambda j: j[0] not in RACED)        # the slower arms first
        with ProcessPoolExecutor(min(a.jobs, len(jobs))) as pool:
            for fut in as_completed([pool.submit(nursery, j) for j in jobs]):
                for msg in fut.result():
                    print("  ", msg, flush=True)
        scored = sorted(r for r in range(a.start_round + 1, a.rounds + 1) if r % a.play_every == 0 or r == a.rounds)
        plays = [(arm, n, r, args) for arm in a.arms for n in a.nursery_seeds for r in scored]
        old = read(path) if a.start_round and path.exists() else []    # an extension keeps earlier rounds
        rows = [r for r in old if r["arm"] == "scratch" or r["round"] <= a.start_round]
        if not any(r["arm"] == "scratch" for r in rows):
            plays.append(("scratch", -1, 0, args))
        with ProcessPoolExecutor(min(a.jobs, len(plays))) as pool:
            for fut in as_completed([pool.submit(play, j) for j in plays]):
                rows.extend(fut.result())
                print(f"  play {len(rows)}/{len(plays) * a.play_seeds}", flush=True)
        rows.sort(key=lambda r: (r["arm"], r["nursery"], r["round"], r["seed"]))
        write(path, rows)
    report(read(path), args)
    luck_report(out)


if __name__ == "__main__":
    main()
