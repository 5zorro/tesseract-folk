# Handoff: Tesseract Folk

Read this first instead of searching around. Read `gotchas.md` before measuring
anything. Stray ideas go in `openitems.md`, not into the current plan.
(`openitems.md` is 5zorro's private brainstorming: gitignored, local only.)

## What it is
An artificial-life society in Python: tiny neural-net NPCs (Creatures-style),
aging, hunger with nutrients, poop → stink → fertilizer, prayer and stale secrets,
all on a conserved-mass loop. It runs in N dimensions (2D now, 4D later) and is
meant to be ported to a C++ mod for 4D Miner. Full design: `docs/DESIGN.md`.
Milestones: `docs/ROADMAP.md`. Rules for working in the code: `AGENT_CONVENTIONS.md`.

## Status (2026-11-02)
- **M0 (plumbing) is done and verified:** all tests pass, 2D and 4D headless runs
  work, mass drift ~1e-13, snapshot resume is bit-identical.
- **Safety first:** `docs/SAFETY.md` (threat model, rules marked
  enforced/planned/decision) and `SECURITY.md` (how to report) exist. `sim/`'s
  no-outside-I/O rule is enforced by `tests/test_safety.py`.
- **Public on GitHub: https://github.com/5zorro/tesseract-folk** (branch `main`,
  first pushed 2026-11-02). 5zorro pushes; agents only commit locally. Licensed **AGPL-3.0-or-later** (`LICENSE`; notes on
  monetizing, contributors and the 4D Miner mod in `openitems.md`). Still open:
  CI, private vulnerability reporting, and a contributor agreement before
  accepting outside PRs.
- **M1 survival in progress.** Plan: `docs/plan-m1-survival.md`. Slices 1–3
  (collapse causes, multi-seed `scripts/sweep.py`, honest stability check) are
  done; slice 4 (economy tuning) is next. Two decisions on criteria wording are
  open (bottom of the plan).
- `--until-stable` now honestly fails (top-ups, population on the floor) and
  prints why. It will keep failing until M3.
- **Smiting is off** (`Config.smiting = False`, 5zorro 2026-11-02) until a snapshot
  survives hunger. Piety and smiting return in M5.
- Honest state, hunger only (5 seeds × 10,000 ticks):
  - Collapses ≈ 3.9 per 1,000 NPC-ticks in 2D; starvation causes about 99% of them.
  - Brains beat the 2D scripted forager (3.5 vs 6.5) but **don't improve across
    generations** (flat 3.5 → 3.5 → 3.7). The earlier trend was mostly learning
    not to pray. Selection pressure is the next suspect (plan, slice 4 step 2b).
  - In 4D the scripted forager never collapses, so the 4D economy is easy.
  - Births ≈ 21 per run vs about 250 top-up spawns. That belongs to M3.

## Where to pick up
1. `docs/plan-m1-survival.md`, slice 4 (economy tuning with `scripts/sweep.py`).

## Setup (Windows)
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest -q
.venv/Scripts/python scripts/run_headless.py --ticks 3000
```
In WSL, make a separate venv (`.venv/bin/python`); see `gotchas.md`.

## Where things are (examples to copy from)
| Need | Look at |
|---|---|
| Tick order (sense → think → act → metabolize) | `sim/simulation.py: step` |
| Every damage source | `sim/simulation.py: _metabolize`, `sim/deity.py: pray`; always via `NPC.take_damage` so the cause is recorded |
| Collapse causes, per-generation rates | `sim/stats.py: CAUSES, collapse_rate_by_generation`; printed by `run_headless.py: print_summary` |
| Comparing configs over many seeds | `scripts/sweep.py` (e.g. `--seeds 5 --ticks 10000 --variant metabolism_rate=0.008 --variant controller=scripted`) |
| Collapse vs death, the hall-of-fame top-up | `sim/simulation.py: _collapse, _die, _top_up` |
| Adding a tunable | `sim/config.py` (every number lives here) |
| Adding a stats counter | `sim/stats.py: COUNTERS`, then `run_headless.py: COLUMNS/HEADERS` |
| Moving mass without breaking the invariant | `sim/simulation.py: _give`, `sim/deity.py: step` |
| A non-brain controller | `sim/controllers.py: ScriptedController` |
| Test style, small configs | `tests/test_simulation.py: small()` |
| N-d helpers | `sim/world.py: neighbor, adjacent, wrapped_delta` |
| Safety rules, threat model, release checklist | `docs/SAFETY.md`, guard tests in `tests/test_safety.py` |

## Working rules (short version; the full list is in AGENT_CONVENTIONS.md)
- Mass is conserved; new mechanics move matter between pools.
- Stay N-dimensional; test new features at dims=4.
- No ML frameworks; never script or reward the emergent behaviors.
- All randomness through `sim.rng`.
- 5zorro pushes. Agents may commit locally, with no Co-Authored-By or AI attribution
  lines (a GitHub hook enforces this).
