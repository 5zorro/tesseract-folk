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
- **M1 survival is done** (5zorro, 2026-11-02). Plan: `docs/plan-m1-survival.md`. Done: slices
  1–3 (collapse causes, multi-seed `scripts/sweep.py`, honest stability check),
  **4b, the nursery** (`sim/nursery.py`, `--brains-from`) and **6, food scent**
  (`Config.food_scent`, on by default), plus an economy retune with 5zorro:
  eating counts as busy, food only in patches, slower hunger (0.003), costlier
  collapses (300). Criteria settled by 5zorro (plan, Goal): **all four met, in 2D
  and 4D** (3 only easily). 4D uses `food_patch_radius=2.0`.
- `--until-stable` honestly fails (top-ups, population on the floor) and prints
  why. Expect that until M3.
- **Smiting is off** (`Config.smiting = False`, 5zorro 2026-11-02) until a snapshot
  survives hunger. Piety and smiting return in M5.
- **Decided (5zorro):** play-world hunger stays easy (`nutrient_decay` 0.003);
  harshness, like food scarcity, belongs in the nursery.
- **Decided:** keep pillar 4 ("young can't die") in play. Evolution's deaths
  happen offline in the nursery (harsh `collapse_age_penalty=600`), and gentle
  play worlds start from its best brains.
- Honest state, hunger only (5 seeds × 10,000 ticks, 2D, today's defaults, unseen maps):
  | | From scratch | From `nursery-8` |
  |---|---|---|
  | Collapses / 1,000 NPC-ticks | 1.8 | **0.9** |
  | Lowest nutrient (bar: 0.4) | 0.44 | 0.51 |
  | Births vs top-ups | 19 vs 215 | 85 vs 129 |
  - Collapse causes: nutrients ~60%, body mass ~35% (new: NPCs keep nutrients
    up but don't take in enough mass).
  - Food scent only pays off through the nursery.
  - Nursery snapshots are local only (`snapshots/` is gitignored, ~1 MB each).
    `nursery-7/8` match today's rules; so do `nursery-scarce-1/2` (trained on
    half food) and `nursery-4d-1/2` (4D, `--dims 4 --size 10`, radius 2). Older ones were trained under older rules
    (`nursery-1/2` also need `--set food_scent=false`). Retrain with the
    commands in `scripts/run_headless.py`'s docstring.
  - Nobody learns or shares secrets, and there's no channel for food
    locations. No social structure is measurable yet (`openitems.md`).
  - 4D needs `food_patch_radius=2.0`: at the default radius every 4D cell grows
    every food, and foraging is trivial (`gotchas.md`).

## Where to pick up
1. **M2: diet drives travel.** Plan: `docs/plan-m2-diet-travel.md`. Slices 1–3
   are done and the thresholds are settled (5zorro, 2026-11-03). Slice 3's
   shared-patches control (`food_layout=shared`) halves zone switches, but it
   halves them for scratch brains too: geometry, not diet. Trained brains hop
   patches ~60% more than scratch in both layouts. Shared patches also crowd
   NPCs into stink. 4D still misses criterion 2 (2.4 food types per life).
   Next, if 5zorro agrees: slice 3b, a direct "deficit-directed travel" metric
   (does the next zone match the NPC's lowest nutrient more often than chance?).
2. Known gaps carried from M1: body starvation is ~35% of collapses; births
   still trail top-ups in 2D (M3's job).
3. Other levers: a harsher scarcity nursery (half food gave a mild win); **seasons** as a config schedule (famine winters, mostly for
   consistency); play-world drift fixes (re-seed, lower mutation in play).
4. Later (M5): the piety lifecycle (full until adulthood, then declines; share
   piety like a secret) as the path to answered prayers and shared secrets.
5. **5zorro's brainstorm (2026-11-03)** is in `openitems.md` (clock and day/night,
   occupations and wages, places with abilities, memory stack, sus and monsters,
   mutation schedule and brain size, immigrants). A proposed roadmap placement
   was offered on 2026-11-03; `docs/ROADMAP.md` is unchanged until 5zorro decides.

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
| Food scent (sense and field) | `sim/world.py: step, scent_at`, `sim/simulation.py: sense` |
| Food zones, travel metrics, the shared-patches control (M2) | `sim/world.py: _make_capacity` (`Config.food_layout`), `zone_at`, `sim/npc.py: record_zone`, `sim/stats.py: record_life, travel_summary` |
| What counts as busy vs idle | `sim/simulation.py: _act` (`did`), `Config.busy_resets_idle` |
| Old snapshots keeping old rules | `sim/snapshot.py: LEGACY`, `FORMAT` |
| A one-off diagnostic probe to copy | `scripts/probe_nutrients.py` |
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
