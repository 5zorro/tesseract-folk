"""Variation x capacity ladder (5zorro, 2026-11-07: "if the problem is we get
same-y same-y bs then we need either more mutations or bigger brains or both?").

R14 found 4D's food-types ceiling (~2.6-2.65 at 0.36x hunger) doesn't move when
luck is taken out of selection, and the hall of fame is near-equal. This grid
trains plain nurseries (`scripts/arena.py --arms plain`) at each mutation size
(`mutation_scale` x the default, nursery only) and brain size (`hidden_units`),
and scores each checkpoint in the usual play worlds (default mutation).

    python scripts/variation_ladder.py                       # the default 3 x 3 grid
    python scripts/variation_ladder.py --scales 0.5 1 2 --hidden 8 16 32
    python scripts/variation_ladder.py --report-only

Each cell writes `runs/var-{d}d-m{scale}-h{hidden}.csv` / `.log`; cells already
run are reused, but only with the same settings: rounds, round length, nursery
seeds and scored rounds are checked against the CSV, and a non-default
`--hunger` adds a tag to the name (review 2026-11-08: a rerun with other
settings silently reused old cells). Checkpoints are deleted after scoring unless the cell meets every
M2 goal at its last round (snapshot rule: keep only what passes M2).
Prints one table (mean +- se over nurseries) and a least-squares fit of each
metric on log2(scale) and log2(hidden) at the last round: the relationship,
not just the winner.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from sim import Config  # noqa: E402
import arena  # noqa: E402
from ladder import physics_tag, verdicts  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HUNGER_036 = "nutrient_decay=0.00108,metabolism_rate=0.0036"     # 4D's pick (R12-R14)
SHOWN = (("zone_types_per_life", "types"), ("diet_diversity", "diet"), ("min_nutrient", "nutr"),
         ("collapse_rate", "clpse"))


def cell_name(dims: int, scale: float, hidden: int, hunger: str = HUNGER_036) -> str:
    tag = "" if hunger == HUNGER_036 else "-" + hashlib.sha1(hunger.encode()).hexdigest()[:6]
    return f"var-{dims}d-m{round(scale, 3)}-h{hidden}{tag}{physics_tag()}"


def scored_rounds(a) -> set[int]:
    return {r for r in range(1, a.rounds + 1) if r % a.play_every == 0 or r == a.rounds}


def check_settings(path: Path, rows: list[dict], a) -> None:
    """Refuse a cell's CSV that other settings made (the name can't hold them all)."""
    plain = [r for r in rows if r["arm"] == "plain"]
    found = ({r["round"] for r in plain}, {r["nursery"] for r in plain},
             {r["ticks"] == r["round"] * a.round_ticks for r in plain})
    wanted = (scored_rounds(a), set(a.nursery_seeds), {True})
    if found != wanted:
        raise SystemExit(f"{path.name} was made with other settings (rounds {sorted(found[0])}, nurseries "
                         f"{sorted(found[1])}, round length matches: {found[2] == {True}}). "
                         "Rerun with those settings, or delete the cell's .csv and .log to redo it.")


def run_cell(dims: int, scale: float, hidden: int, a) -> str:
    name = cell_name(dims, scale, hidden, a.hunger)
    csv = ROOT / "runs" / f"{name}.csv"
    if csv.exists():
        check_settings(csv, arena.read(csv), a)
        return f"{name}: reused"
    out = ROOT / "snapshots" / "var" / name
    breed = f"{a.hunger},mutation_scale={round(Config().mutation_scale * scale, 6)}"
    cmd = [sys.executable, str(ROOT / "scripts" / "arena.py"), "--dims", str(dims), "--hidden", str(hidden),
           "--arms", "plain", "--breed", breed, "--play", a.hunger, "--rounds", str(a.rounds),
           "--round-ticks", str(a.round_ticks), "--play-every", str(a.play_every),
           "--nursery-seeds", *map(str, a.nursery_seeds), "--jobs", str(len(a.nursery_seeds)),
           "--out", str(out), "--csv", str(csv)]
    with (ROOT / "runs" / f"{name}.log").open("w") as log:
        subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    passes = summary(dims, scale, hidden, a)["passes"]
    if not passes:
        shutil.rmtree(out, ignore_errors=True)
    return f"{name}: done{' (passes M2: checkpoints kept)' if passes else ''}"


def summary(dims: int, scale: float, hidden: int, a) -> dict | None:
    path = ROOT / "runs" / f"{cell_name(dims, scale, hidden, a.hunger)}.csv"
    if not path.exists():
        return None
    rows = arena.read(path)
    check_settings(path, rows, a)
    scratch = [r for r in rows if r["arm"] == "scratch"]
    rounds = sorted({r["round"] for r in rows if r["arm"] == "plain"})
    by_round = {}
    for rnd in rounds:
        cell = [r for r in rows if r["arm"] == "plain" and r["round"] == rnd]
        stats = {}
        for key, _ in SHOWN:
            per_n = [float(np.nanmean([r[key] for r in cell if r["nursery"] == n]))
                     for n in sorted({r["nursery"] for r in cell})]
            se = float(np.std(per_n, ddof=1) / math.sqrt(len(per_n))) if len(per_n) > 1 else math.nan
            stats[key] = (float(np.mean(per_n)), se)
        ladder_rows = ([{**r, "dims": dims, "hidden": hidden, "brains": f"n{r['nursery']}"} for r in cell] +
                       [{**r, "dims": dims, "hidden": hidden, "brains": "scratch"} for r in scratch])
        v = verdicts(ladder_rows)
        stats["goals"] = v[0]["goals"] if v else {}
        stats["ticks"] = cell[0]["ticks"]
        by_round[rnd] = stats
    last = by_round[rounds[-1]]
    return {"scale": scale, "hidden": hidden, "rounds": by_round,
            "passes": bool(last["goals"]) and all(last["goals"].values())}


def report(a) -> None:
    for dims in a.dims:
        cells = [s for s in (summary(dims, m, h, a) for m in a.scales for h in a.hidden) if s]
        if not cells:
            print(f"{dims}D: no cells yet")
            continue
        goal_names = list(next(iter(cells[0]["rounds"].values()))["goals"])
        print(f"\n{dims}D variation x capacity, plain nurseries at {a.hunger} "
              f"(mean +- se over nurseries; goals: {', '.join(goal_names)})")
        print(f"{'scale':>5} {'hidden':>6} {'ticks':>8} " + " ".join(f"{lab:>11}" for _, lab in SHOWN) + "  goals")
        for s in cells:
            for rnd, st in s["rounds"].items():
                marks = " ".join("Y" if ok else "." for ok in st["goals"].values())
                vals = " ".join(f"{st[k][0]:5.2f}+-{st[k][1]:4.2f}" for k, _ in SHOWN)
                print(f"{s['scale']:>5} {s['hidden']:>6} {st['ticks']:>8,} {vals}  {marks}")
        if len(cells) >= 3:
            X = np.array([[1.0, math.log2(s["scale"]), math.log2(s["hidden"])] for s in cells])
            print("  last round: metric = a + b*log2(mutation scale) + c*log2(hidden)  (per doubling)")
            for key, lab in SHOWN:
                y = np.array([list(s["rounds"].values())[-1][key][0] for s in cells])
                coef, *_ = np.linalg.lstsq(X, y, rcond=None)
                resid = y - X @ coef
                dof = max(len(y) - 3, 1)
                cov = np.linalg.pinv(X.T @ X) * float(resid @ resid) / dof
                se = np.sqrt(np.diag(cov))
                print(f"  {lab:>6}: a {coef[0]:+.3f}, per mutation doubling {coef[1]:+.3f} +- {se[1]:.3f}, "
                      f"per brain doubling {coef[2]:+.3f} +- {se[2]:.3f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", default=[4])
    ap.add_argument("--scales", type=float, nargs="+", default=[0.5, 1.0, 2.0],
                    help="mutation_scale as a multiple of the default")
    ap.add_argument("--hidden", type=int, nargs="+", default=[8, 16, 32])
    ap.add_argument("--hunger", default=HUNGER_036, help="nursery and play hunger rules")
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--round-ticks", type=int, default=50_000)
    ap.add_argument("--play-every", type=int, default=2)
    ap.add_argument("--nursery-seeds", type=int, nargs="+", default=[100, 101, 102, 103])
    ap.add_argument("--parallel", type=int, default=4, help="cells at once (each uses one core per nursery)")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()
    if any(s <= 0 for s in a.scales) or any(h < 1 for h in a.hidden):
        ap.error("--scales must be > 0 and --hidden >= 1")
    if not a.report_only:
        cells = [(d, m, h) for d in a.dims for m in a.scales for h in a.hidden]
        cells.sort(key=lambda c: -c[2])                    # the big brains first: they're slowest
        with ThreadPoolExecutor(a.parallel) as pool:
            for msg in pool.map(lambda c: run_cell(*c, a), cells):
                print("  ", msg, flush=True)
    report(a)


if __name__ == "__main__":
    main()
