"""Why do 4D nurseries peak at 100-200k ticks and then decay? (M2 slice R10)

Three tests of the candidate causes, on `scripts/long_nursery.py` checkpoints:

    python scripts/probe_decay.py hof               # what the nursery and its hall of fame look like per checkpoint
    python scripts/probe_decay.py rules             # score checkpoints under the nursery's own rules, too
    python scripts/probe_decay.py freeze            # resume at the peak with the hall of fame frozen

- `hof` reads the checkpoints only: the nursery's own collapse rate, the hall
  of fame's merits, turnover and generations, and how far its brains drift.
- `rules` plays fresh worlds from every checkpoint under the nursery's rules
  (`ladder.NURSERY_RULES`) and compares them with the play-rule scores in
  `runs/long-nursery-4d*.csv`: if the nursery score keeps improving while the
  play score decays, the brains fit the nursery, not play.
- `freeze` resumes checkpoints with `hall_of_fame_frozen` (no new entries, no
  credits, no drops) and trains on; if the decay stops, hall-of-fame drift is
  the cause.
Selection luck is the third test: more nursery seeds via
`long_nursery.py --nursery-seeds` (see the plan's slice R10).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim.brain import Brain  # noqa: E402
from sim.snapshot import load_snapshot, save_snapshot  # noqa: E402
from ladder import NURSERY_RULES, NURSERY_SEEDS  # noqa: E402
from long_nursery import folder, play  # noqa: E402

LONG = Path("snapshots/long")
ARMS = ("base", "both32", "both64")
TICKS = (50_000, 100_000, 200_000, 350_000, 500_000, 700_000)


def flat(brain: dict) -> np.ndarray:
    b = Brain.from_dict(brain)
    return np.concatenate([b.w1.ravel(), b.b1.ravel(), b.w2.ravel(), b.b2.ravel()])


# ================================================================== hof
def hof(out: Path, arms, nseeds, ticks) -> None:
    print("Per checkpoint, mean over nurseries. nursery = the nursery population's own collapse rate")
    print("(collapses per 1,000 ticks lived, NPCs alive at the checkpoint); hof = hall-of-fame entries.")
    print(f"{'arm':>7} {'ticks':>8} {'nursery':>7} {'hof rate':>8} {'merit':>6} {'lives':>6} {'copies':>6} "
          f"{'turnover':>8} {'hof gen':>7} {'live gen':>8} {'|w|':>6} {'drift':>6} {'copy%':>6}")
    for arm in arms:
        prev_ids, first_best = {}, {}
        for t in ticks:
            cols = []
            for n in nseeds:
                path = folder(out, 4, arm, n, t) / "state.json"
                if not path.exists():
                    continue
                s = json.loads(path.read_text())
                npcs, hall = s["npcs"], s["hall_of_fame"]
                prior = s["config"].get("hall_of_fame_prior_lives", 0.0)
                lived = sum(x["lifetime"] for x in npcs)
                ids = {e["id"] for e in hall}
                best = flat(hall[0]["brain"])
                first_best.setdefault(n, best)
                cols.append([
                    1000.0 * sum(x["collapses"] for x in npcs) / max(lived, 1),
                    np.mean([e["rate"] for e in hall]),
                    np.mean([-e["excess_sum"] / (e["lives"] + prior) for e in hall]),
                    np.mean([e["lives"] for e in hall]),
                    np.mean([e["copies"] for e in hall]),
                    len(ids - prev_ids[n]) / len(ids) if n in prev_ids else math.nan,
                    np.mean([e["generation"] for e in hall]),
                    np.mean([x["generation"] for x in npcs]),
                    np.mean([np.linalg.norm(flat(e["brain"])) for e in hall]),
                    np.linalg.norm(best - first_best[n]),
                    100.0 * np.mean([x["origin"] == "copy" for x in npcs]),
                ])
                prev_ids[n] = ids
            if cols:
                m = np.nanmean(np.array(cols, dtype=float), axis=0)
                print(f"{arm:>7} {t:>8,} {m[0]:7.2f} {m[1]:8.2f} {m[2]:+6.2f} {m[3]:6.1f} {m[4]:6.1f} "
                      f"{m[5]:8.2f} {m[6]:7.0f} {m[7]:8.0f} {m[8]:6.1f} {m[9]:6.1f} {m[10]:6.0f}")


# ================================================================ rules
def rules(out: Path, arms, nseeds, ticks, seeds: int, play_ticks: int, csv_path: Path, workers: int) -> None:
    jobs = [(4, a, t, [n], seeds, play_ticks, out, dict(NURSERY_RULES))
            for a in arms for t in ticks for n in nseeds if folder(out, 4, a, n, t).exists()]
    jobs += [(4, a, 0, [], seeds, play_ticks, out, dict(NURSERY_RULES)) for a in arms]
    rows = []
    with ProcessPoolExecutor(min(workers, len(jobs))) as pool:
        for fut in as_completed([pool.submit(play, j) for j in jobs]):
            rows.extend(fut.result())
            print(f"  play {len(rows)}", flush=True)
    write(csv_path, rows)


def write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def read(path: Path) -> list[dict]:
    with path.open() as f:
        return [{k: (v if k == "arm" else float(v) if v not in ("", "nan") else math.nan) for k, v in r.items()}
                for r in csv.DictReader(f)]


def curve(rows: list[dict], arm: str, key: str = "collapse_rate") -> dict[int, float]:
    out = {}
    for t in sorted({int(r["nursery_ticks"]) for r in rows if r["arm"] == arm}):
        out[t] = float(np.nanmean([r[key] for r in rows if r["arm"] == arm and int(r["nursery_ticks"]) == t]))
    return out


def report_rules(csv_path: Path, play_csvs: list[Path]) -> None:
    nursery = read(csv_path)
    played = [r for p in play_csvs if p.exists() for r in read(p)]
    print("\nCollapses per 1,000 ticks, worlds started from each checkpoint (tick 0 = scratch):")
    print(f"{'arm':>7} {'ticks':>8} {'nursery rules':>13} {'play rules':>10}   types (nursery / play)")
    for arm in sorted({r["arm"] for r in nursery}):
        a, b = curve(nursery, arm), curve(played, arm)
        ta, tb = curve(nursery, arm, "zone_types_per_life"), curve(played, arm, "zone_types_per_life")
        for t in a:
            print(f"{arm:>7} {t:>8,} {a[t]:13.2f} {b.get(t, math.nan):10.2f}   "
                  f"{ta[t]:.2f} / {tb.get(t, math.nan):.2f}")


# =============================================================== freeze
def freeze_one(job: tuple) -> str:
    """Resume a checkpoint with a frozen hall of fame and save at each later tick."""
    src, dst_root, arm, n, start, ends = job
    state = json.loads((src / "state.json").read_text())
    state["config"]["hall_of_fame_frozen"] = True
    tmp = dst_root / f"_start-{arm}-n{n}-t{start}"
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "state.json").write_text(json.dumps(state))
    (tmp / "world.npz").write_bytes((src / "world.npz").read_bytes())
    sim = load_snapshot(tmp, log_every=1000)
    shutil.rmtree(tmp)                                  # only the start copy; the run keeps going
    done = start
    for end in ends:
        sim.run(end - done)
        done = end
        save_snapshot(sim, folder(dst_root / f"from{start // 1000}k", 4, arm, n, end))
    return f"froze d4 {arm} n{n} from {start:,} to {done:,}"


def freeze(out: Path, dst: Path, arm: str, nseeds, starts, ends, seeds, play_ticks, csv_path, workers) -> None:
    jobs = [(folder(out, 4, arm, n, s), dst, arm, n, s, [e for e in ends if e > s]) for s in starts for n in nseeds]
    with ProcessPoolExecutor(min(workers, len(jobs))) as pool:
        for fut in as_completed([pool.submit(freeze_one, j) for j in jobs]):
            print("  ", fut.result(), flush=True)
    plays = [(s, (4, arm, e, [n], seeds, play_ticks, dst / f"from{s // 1000}k"))
             for s in starts for e in ends if e > s for n in nseeds]
    rows = []
    with ProcessPoolExecutor(min(workers, len(plays))) as pool:
        futs = {pool.submit(play, j): s for s, j in plays}
        for fut in as_completed(futs):
            rows.extend({**r, "frozen_from": futs[fut]} for r in fut.result())
            print(f"  play {len(rows)}", flush=True)
    write(csv_path, rows)


def report_freeze(csv_path: Path, play_csv: Path, arm: str) -> None:
    frozen, played = read(csv_path), read(play_csv)
    normal = curve(played, arm)
    print(f"\n{arm}: collapses per 1,000 ticks from checkpoints, normal vs hall of fame frozen at a tick")
    starts = sorted({int(r["frozen_from"]) for r in frozen})
    print(f"{'ticks':>8} {'normal':>7} " + " ".join(f"{'frozen@' + str(s // 1000) + 'k':>11}" for s in starts))
    for t in sorted(normal):
        cells = []
        for s in starts:
            rs = [r["collapse_rate"] for r in frozen if int(r["frozen_from"]) == s and int(r["nursery_ticks"]) == t]
            cells.append(f"{np.nanmean(rs):11.2f}" if rs else f"{'':>11}")
        print(f"{t:>8,} {normal[t]:7.2f} " + " ".join(cells))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("test", choices=("hof", "rules", "freeze"))
    ap.add_argument("--out", default=str(LONG), help="long_nursery.py checkpoints")
    ap.add_argument("--arms", nargs="+", default=list(ARMS))
    ap.add_argument("--nursery-seeds", type=int, nargs="+", default=list(NURSERY_SEEDS))
    ap.add_argument("--ticks", type=int, nargs="+", default=list(TICKS))
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--play-ticks", type=int, default=10_000)
    ap.add_argument("--starts", type=int, nargs="+", default=[100_000, 200_000], help="freeze: resume from")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    if args.test == "hof":
        hof(out, args.arms, args.nursery_seeds, args.ticks)
    elif args.test == "rules":
        path = Path("runs/decay-nursery-rules-4d.csv")
        if not args.report_only:
            rules(out, args.arms, args.nursery_seeds, args.ticks, args.seeds, args.play_ticks, path, args.jobs)
        report_rules(path, [Path("runs/long-nursery-4d.csv"), Path("runs/long-nursery-4d-64.csv")])
    else:
        path = Path("runs/decay-freeze-4d.csv")
        if not args.report_only:
            freeze(out, Path("snapshots/decay-freeze"), args.arms[0], args.nursery_seeds, args.starts,
                   args.ticks, args.seeds, args.play_ticks, path, args.jobs)
        report_freeze(path, Path("runs/long-nursery-4d.csv"), args.arms[0])


if __name__ == "__main__":
    main()
