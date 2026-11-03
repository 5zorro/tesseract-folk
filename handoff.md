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
- **M1 survival in progress.** Plan: `docs/plan-m1-survival.md`. Done: slices
  1–3 (collapse causes, multi-seed `scripts/sweep.py`, honest stability check)
  and **4b, the nursery** (`sim/nursery.py`, `--brains-from`). Criteria wording
  is still open (bottom of the plan, and the question under slice 4b).
- `--until-stable` honestly fails (top-ups, population on the floor) and prints
  why. Expect that until M3.
- **Smiting is off** (`Config.smiting = False`, 5zorro 2026-11-02) until a snapshot
  survives hunger. Piety and smiting return in M5.
- **Decided:** keep pillar 4 ("young can't die") in play. Evolution's deaths
  happen offline in the nursery (harsh `collapse_age_penalty=600`), and gentle
  play worlds start from its best brains.
- Honest state, hunger only (5 seeds × 10,000 ticks, 2D, gentle rules):
  | | From scratch | From `snapshots/nursery-2` |
  |---|---|---|
  | Collapses / 1,000 NPC-ticks | 3.9 | 2.9 |
  | Births vs top-ups | 21 vs 250 | **156 vs 130** |
  - Starvation causes nearly all collapses.
  - Nursery brains generalize to unseen maps.
  - But their advantage **erodes over generations** in gentle worlds
    (1.9 → 2.4 → 3.5), because selection is weak there.
  - Nursery snapshots are local only (`snapshots/` is gitignored, ~1 MB each).
    Retrain them with the commands in `scripts/run_headless.py`'s docstring.
  - Nobody learns or shares secrets, and there's no channel for food
    locations. No social structure is measurable yet (`openitems.md`).
  - In 4D the scripted forager never collapses, so the 4D economy is easy.

## Where to pick up
1. 5zorro: settle the M1 criteria questions (plan bottom, and under slice 4b).
2. Then pick one: keep play worlds from drifting (re-seed, lower play mutation,
   or mild selection), or slice 5 (bigger brains) to push the nursery further.

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
| Nursery: evolve offline, start fresh worlds from the best brains | `sim/nursery.py`; commands in `scripts/run_headless.py` docstring; `sweep.py --variant brains_from=<snapshot>` |
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
