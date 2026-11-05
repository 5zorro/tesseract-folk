"""Compare ladder CSVs nursery by nursery (how the research slices' tables were made).

Each argument is LABEL=FILE[+FILE...] (files under runs/); rows are filtered to
one dims and hidden size. Prints, per label, the mean over nurseries (each
nursery averaged over its play seeds) with the standard error, scratch's
collapses, and each nursery's collapses so pairs can be compared by seed.

    python scripts/compare_runs.py 3 8 "baseline=2026-11-04-defaults-3d.csv" "track=2026-11-04-track-3d.csv"
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ladder import read_csv  # noqa: E402

KEYS = ("collapse_rate", "zone_types_per_life", "diet_diversity", "min_nutrient",
        "approach_excess", "cause_body_starve", "births")


def summarize(rows: list[dict]) -> tuple[dict, dict, float]:
    per = {}
    for brains in sorted({r["brains"] for r in rows if r["brains"] != "scratch"}):
        cell = [r for r in rows if r["brains"] == brains]
        per[brains] = {k: float(np.nanmean([r.get(k, math.nan) for r in cell])) for k in KEYS}
    scratch = [r["collapse_rate"] for r in rows if r["brains"] == "scratch"]
    return per, {k: [v[k] for v in per.values()] for k in KEYS}, float(np.mean(scratch)) if scratch else math.nan


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dims", type=int)
    ap.add_argument("hidden", type=int)
    ap.add_argument("sets", nargs="+", metavar="LABEL=FILE[+FILE]")
    ap.add_argument("--runs", type=str, default="runs")
    args = ap.parse_args()
    for spec in args.sets:
        label, _, files = spec.partition("=")
        rows = [r for f in files.split("+") for r in read_csv(Path(args.runs) / f)
                if r["dims"] == args.dims and r["hidden"] == args.hidden]
        if not rows:
            print(f"{label}: no rows for {args.dims}D, {args.hidden} hidden units")
            continue
        per, cols, scratch = summarize(rows)
        n = len(per)

        def mean_se(k):
            v = np.array(cols[k])
            se = v.std(ddof=1) / math.sqrt(n) if n > 1 else math.nan
            return f"{v.mean():.2f} ± {se:.2f}"
        print(f"{label}: {n} nurseries | collapses {mean_se('collapse_rate')} (scratch {scratch:.2f}) | "
              f"food types {mean_se('zone_types_per_life')} | diet {np.mean(cols['diet_diversity']):.2f} | "
              f"lowest nutrient {np.mean(cols['min_nutrient']):.2f} | approach excess "
              f"{np.mean(cols['approach_excess']):.3f} | body starvation {np.mean(cols['cause_body_starve']):.2f} | "
              f"births {np.mean(cols['births']):.0f}")
        print("    collapses by nursery: " + " ".join(f"{b}:{v['collapse_rate']:.2f}" for b, v in per.items()))


if __name__ == "__main__":
    main()
