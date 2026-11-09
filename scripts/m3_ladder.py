"""M3 ladder (docs/plan-m3-births.md, slice S1): does each dimension's play
world hold a steady population from its own births?

Play worlds start from each dimension's M2 nursery at its M2 hunger (2D 1x, 3D
0.9x, 4D 0.36x), plus scratch worlds at the same settings. Each world is judged
over the second half of its run, on M3's three criteria:

1. births: top-ups at most `--max-spawn-fraction` (0.1) per birth;
2. off the rails: at most `--rail-share` of samples on the top-up floor or at
   the population cap;
3. steady: population std / mean below `--max-cv` (0.15).

    python scripts/m3_ladder.py                    # 2D-4D, 5 seeds x 30,000 ticks
    python scripts/m3_ladder.py --dims 4 --seeds 3
    python scripts/m3_ladder.py --report-only
    python scripts/m3_ladder.py --dims 4 --nurseries "4=snapshots/s3/births-n*-r35" --csv runs/m3-s3-births.csv
    python scripts/m3_ladder.py --dims 4 --set soil_diffusion=0.1 --csv runs/m3-soil0.1.csv
    python scripts/m3_ladder.py --dims 4 --hunger 0.36 0.5 0.75 --seeds 3 --csv runs/m3-hscan-4d.csv
        # a hunger grid (plan-m3 S3c); every level x every source

`--nurseries` may repeat a dimension: the first spec replaces its default
nurseries, later ones add to them. The M2 measures (collapses, lowest
nutrient, diet, food types per life) are reported beside M3's, over the whole
run (M2's ladders use 10,000-tick play worlds, so they are close, not equal).

Results go to `--csv` (default runs/m3-baseline.csv) with the settings beside it
(.json); a rerun reuses them only if the settings match (the 2026-11-08 review's
rerun guard).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from sim import Config  # noqa: E402
from sim.config import parse_overrides  # noqa: E402
from ladder import WORLD_SETS, physics_changes, world  # noqa: E402
from sweep import run_batch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# M2's pick per dimension: hunger and nursery folders (plan-m3 "Worlds").
HUNGER = {2: 1.0, 3: 0.9, 4: 0.36}
NURSERIES = {
    2: [f"snapshots/hdist/d2-s32-r4-h16-metabolism_rate0.01-nutrient_decay0.003-n{n}" for n in (100, 101)],
    3: [f"snapshots/hdist/d3-s14-r1.88-h16-metabolism_rate0.009-nutrient_decay0.0027-n{n}" for n in (100, 101)],
    4: [f"snapshots/arena-fixed/persist-n{n}-r35" for n in (100, 101, 102, 103)],
}
HIDDEN = 16
LOG_EVERY = 250


def hunger_rules(level: float) -> dict:
    base = Config()
    return {k: round(getattr(base, k) * level, 8) for k in ("metabolism_rate", "nutrient_decay")}


def sources(dims: int) -> list[str]:
    return NURSERIES[dims] + ["scratch"]


def job(task: tuple) -> list[dict]:
    """One source's worlds (every seed in one batch)."""
    dims, source, seeds, ticks, extra, level = task
    overrides = {**world((dims, *WORLD_SETS["time"][dims], HIDDEN, ())), **hunger_rules(level), **extra}
    if source != "scratch":
        overrides["brains_from"] = str(ROOT / source)
    rows = run_batch([(dict(overrides), s, ticks, 0.5, LOG_EVERY) for s in seeds])
    name = "scratch" if source == "scratch" else Path(source).name
    return [{"dims": dims, "hunger": level, "source": name, **r} for r in rows]


def levels(a, dims: int) -> list[float]:
    """The hunger levels a run uses for a dimension: --hunger, or M2's pick."""
    return list(a.hunger) if a.hunger else [HUNGER[dims]]


def verdict(row: dict, a) -> dict:
    """M3's criteria for one world (True = met)."""
    births, spawns = row["late_births"], row["late_spawns"]
    return {"births": births > 0 and spawns <= a.max_spawn_fraction * births,
            "off rails": row["at_floor"] <= a.rail_share and row["at_cap"] <= a.rail_share,
            "steady": row["pop_cv"] < a.max_cv}


def settings(a) -> dict:
    out = {"seeds": a.seeds, "ticks": a.ticks,
           "hunger": {str(d): levels(a, d) if a.hunger else HUNGER[d] for d in a.dims},
           "sources": {str(d): sources(d) for d in a.dims}, "hidden": HIDDEN, "log_every": LOG_EVERY}
    if a.set:                              # only when given, so older sidecars still match
        out["set"] = parse_overrides(a.set)
    physics = physics_changes()
    if physics:                            # a default that changed since the older sidecars
        out["physics"] = physics
    return out


def short(source: str) -> str:
    """A report label: hdist ...-n100 -> n100, births-cross-n100-r35 -> bc-n100-r35."""
    if len(source) <= 16:
        return source
    m = re.search(r"n\d+(-r\d+)?$", source)
    if not m:
        return source[-16:]
    words = [w for w in source[:m.start()].split("-") if w.isalpha()]
    return "".join(w[0] for w in words) + ("-" if words else "") + m.group(0)


def read(path: Path) -> list[dict]:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            if k != "source":
                r[k] = float(v) if v not in ("", "nan") else math.nan
        r["dims"] = int(r["dims"])
    return rows


def write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def report(rows: list[dict], a) -> None:
    print(f"\nM3: worlds judged on ticks {a.ticks // 2:,}-{a.ticks:,} (births: top-ups <= "
          f"{a.max_spawn_fraction} per birth; off rails: <= {a.rail_share:.0%} of samples on the floor or "
          f"cap; steady: cv < {a.max_cv})")
    print(f"{'dims':>4} {'hunger':>6} {'source':>16} {'worlds':>6} {'births':>7} {'top-ups':>7} {'pop':>6} {'cv':>5} "
          f"{'floor':>6} {'cap':>5}  births  rails  steady  pass | clpse  nutr  diet types")
    for dims, level in sorted({(r["dims"], r.get("hunger", HUNGER[r["dims"]])) for r in rows}):
        here = [r for r in rows if r["dims"] == dims and r.get("hunger", HUNGER[dims]) == level]
        for source in dict.fromkeys(r["source"] for r in here):
            cell = [r for r in here if r["source"] == source]
            v = [verdict(r, a) for r in cell]
            m = {k: float(np.nanmean([r[k] for r in cell]))
                 for k in ("late_births", "late_spawns", "pop_mean", "pop_cv", "at_floor", "at_cap")}
            met = {k: sum(x[k] for x in v) for k in v[0]}
            m2 = {k: float(np.nanmean([r[k] for r in cell]))
                  for k in ("collapse_rate", "min_nutrient", "diet_diversity", "zone_types_per_life")}
            print(f"{dims:>4} {level:>6} {short(source):>16} {len(cell):>6} {m['late_births']:7.0f} {m['late_spawns']:7.0f} "
                  f"{m['pop_mean']:6.0f} {m['pop_cv']:5.2f} {m['at_floor']:6.0%} {m['at_cap']:5.0%}  "
                  f"{met['births']:>6} {met['off rails']:>6} {met['steady']:>7} "
                  f"{sum(all(x.values()) for x in v):>5} | {m2['collapse_rate']:5.2f} {m2['min_nutrient']:5.2f} "
                  f"{m2['diet_diversity']:5.2f} {m2['zone_types_per_life']:5.2f}")
    print("(births, rails, steady, pass: worlds meeting each criterion; numbers are means over worlds)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dims", type=int, nargs="+", default=[2, 3, 4], choices=sorted(HUNGER))
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--ticks", type=int, default=30_000)
    ap.add_argument("--max-spawn-fraction", type=float, default=Config().stable_max_spawn_fraction)
    ap.add_argument("--max-cv", type=float, default=Config().stable_max_cv)
    ap.add_argument("--rail-share", type=float, default=0.05,
                    help="share of judged samples allowed on the floor or at the cap")
    ap.add_argument("--csv", default="runs/m3-baseline.csv")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--nurseries", nargs="+", default=[], metavar="DIMS=GLOB",
                    help="score other nursery folders for a dimension (e.g. 4=snapshots/s3/births-n*-r35)")
    ap.add_argument("--set", default="", metavar="K=V,...",
                    help="Config overrides for every world (e.g. soil_diffusion=0.1); saved in the settings")
    ap.add_argument("--hunger", type=float, nargs="+", default=None,
                    help="hunger levels to run every dimension at (default: M2's pick per dimension)")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()
    if a.hunger and not all(0 < h <= 10 for h in a.hunger):
        ap.error("--hunger levels must be within 0-10")
    try:
        extra = parse_overrides(a.set)
    except ValueError as e:
        ap.error(f"--set: {e}")
    replaced: set[int] = set()
    for spec in a.nurseries:
        dims, _, pattern = spec.partition("=")
        found = sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in ROOT.glob(pattern) if p.is_dir())
        if not dims.isdigit() or int(dims) not in NURSERIES or not found:
            ap.error(f"--nurseries {spec}: want DIMS=GLOB matching nursery folders")
        d = int(dims)
        NURSERIES[d] = (NURSERIES[d] if d in replaced else []) + found
        replaced.add(d)
    if a.seeds < 1 or a.ticks < 4 * LOG_EVERY:
        ap.error("--seeds must be >= 1 and --ticks >= 4 samples")
    path, meta = Path(a.csv), Path(a.csv).with_suffix(".json")
    if path.exists():
        saved = json.loads(meta.read_text()) if meta.exists() else None
        if saved != settings(a):
            raise SystemExit(f"{path} was made with other settings ({meta.name}: {saved}). "
                             "Rerun with those, or use another --csv.")
    elif a.report_only:
        raise SystemExit(f"{path} doesn't exist yet")
    else:
        missing = [s for d in a.dims for s in NURSERIES[d] if not (ROOT / s / "state.json").exists()]
        if missing:
            raise SystemExit(f"missing nurseries: {missing} (plan-m3 'Worlds' says how to rebuild them)")
        tasks = [(d, s, list(range(a.seeds)), a.ticks, extra, h)
                 for d in a.dims for h in levels(a, d) for s in sources(d)]
        tasks.sort(key=lambda t: -t[0])                 # 4D first: slowest per tick
        rows = []
        with ProcessPoolExecutor(min(a.jobs, len(tasks))) as pool:
            for fut in as_completed([pool.submit(job, t) for t in tasks]):
                part = fut.result()
                rows.extend(part)
                print(f"  {part[0]['dims']}D {part[0]['hunger']}x {part[0]['source']}: done", flush=True)
        rows.sort(key=lambda r: (r["dims"], r["hunger"], r["source"] == "scratch", r["source"], r["seed"]))
        write(path, rows)
        meta.write_text(json.dumps(settings(a), indent=1))
    report(read(path), a)


if __name__ == "__main__":
    main()
