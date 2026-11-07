"""Find the hunger per dimension that meets M2 with the most births (5zorro,
2026-11-07: "use a ladder so I don't have to keep approving guess-and-check runs").

For each level it runs `scripts/ladder.py --worlds time` (nurseries + play worlds,
the usual M2 goals) with hunger scaled by that level (`nutrient_decay` and
`metabolism_rate`, as in `scripts/hunger_ladder.py`), then refines: it bisects
between the lowest level that meets every goal and the next lower level that
doesn't, `--refine` times. Levels already run (`runs/hdist-{d}d-h{level}.csv`)
are reused, so reruns only add what's missing.

    python scripts/hunger_search.py --dims 3 --levels 0.85 0.9 0.95 1.0
    python scripts/hunger_search.py --dims 4 --levels 0.36 0.5 0.75 1.0 --refine 2
    python scripts/hunger_search.py --dims 3 --report-only

Pick: the lowest hunger that meets every goal (lower hunger = more births, R12).
Within-noise misses (e.g. diet 0.89 vs 0.9) count as misses: the goals stay put.
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from sim import Config  # noqa: E402
from anneal import HUNGER  # noqa: E402
from ladder import read_csv, verdicts  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def name(level: float) -> str:
    return f"{round(level, 3)}"


def csv_path(dims: int, level: float) -> Path:
    return ROOT / "runs" / f"hdist-{dims}d-h{name(level)}.csv"


def run_level(dims: int, level: float, hidden: int, out: str) -> None:
    path = csv_path(dims, level)
    if path.exists():
        return
    base = Config()
    rules = ",".join(f"{k}={round(getattr(base, k) * level, 8)}" for k in HUNGER)
    cmd = [sys.executable, str(ROOT / "scripts" / "ladder.py"), "--worlds", "time", "--dims", str(dims),
           "--hidden", str(hidden), "--set", rules, "--out", out, "--csv", str(path)]
    print(f"  {dims}D hunger {name(level)}x: running ladder", flush=True)
    with path.with_suffix(".log").open("w") as log:
        subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)


def summary(dims: int, level: float) -> dict | None:
    path = csv_path(dims, level)
    if not path.exists():
        return None
    rows = read_csv(path)
    lines = verdicts(rows)
    if not lines:
        return None
    line = lines[0]
    nursery = [r for r in rows if r["brains"] != "scratch"]
    mean = lambda k: float(np.mean([r[k] for r in nursery]))   # noqa: E731
    return {**line, "level": level, "births": mean("births"), "spawns": mean("spawns"),
            "population": mean("population"), "passes": all(line["goals"].values())}


def known_levels(dims: int) -> list[float]:
    out = []
    for p in (ROOT / "runs").glob(f"hdist-{dims}d-h*.csv"):
        try:
            out.append(float(p.stem.split("-h", 1)[1]))
        except ValueError:
            pass
    return sorted(out)


def report(dims: int) -> float | None:
    rows = [s for s in (summary(dims, lv) for lv in known_levels(dims)) if s]
    if not rows:
        print(f"{dims}D: no runs yet")
        return None
    goal_names = list(rows[0]["goals"])
    print(f"\n{dims}D, nursery-started worlds by hunger (goals: {', '.join(goal_names)})")
    print(f"{'hunger':>6} {'clpse':>5} {'scr':>5} {'nutr':>5} {'diet':>5} {'types':>5} "
          f"{'births':>7} {'top-ups':>7} {'pop':>5}  goals")
    for s in rows:
        marks = " ".join("Y" if ok else "." for ok in s["goals"].values())
        print(f"{name(s['level']):>6} {s['collapses']:5.2f} {s['scratch_collapses']:5.2f} {s['min_nutrient']:5.2f} "
              f"{s['diet']:5.2f} {s['types']:5.2f} {s['births']:7.0f} {s['spawns']:7.0f} {s['population']:5.0f}  {marks}")
    passing = [s["level"] for s in rows if s["passes"]]
    pick = min(passing) if passing else None
    print(f"  pick: {name(pick) + 'x (lowest hunger meeting every goal)' if pick else 'none meets every goal'}")
    return pick


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", required=True)
    ap.add_argument("--levels", type=float, nargs="+", default=[])
    ap.add_argument("--refine", type=int, default=1, help="bisection steps after the grid")
    ap.add_argument("--min-gap", type=float, default=0.02, help="stop bisecting below this hunger gap")
    ap.add_argument("--hidden", type=int, default=16)
    ap.add_argument("--out", default="snapshots/hdist")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    if any(not 0 < lv <= 10 for lv in args.levels):
        ap.error("--levels must be in (0, 10]")
    for dims in args.dims:
        if not args.report_only:
            for lv in args.levels:
                run_level(dims, lv, args.hidden, args.out)
            for _ in range(args.refine):
                rows = [s for s in (summary(dims, lv) for lv in known_levels(dims)) if s]
                passing = sorted(s["level"] for s in rows if s["passes"])
                if not passing:
                    break
                below = [s["level"] for s in rows if not s["passes"] and s["level"] < passing[0]]
                if not below or passing[0] - max(below) < args.min_gap:
                    break
                run_level(dims, round((passing[0] + max(below)) / 2, 3), args.hidden, args.out)
        report(dims)


if __name__ == "__main__":
    main()
