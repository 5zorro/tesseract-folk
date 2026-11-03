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
  1–3 (collapse causes, multi-seed `scripts/sweep.py`, honest stability check),
  **4b, the nursery** (`sim/nursery.py`, `--brains-from`) and **6, food scent**
  (`Config.food_scent`, on by default). Criteria settled by 5zorro (plan, Goal):
  1–2 met, **3 (lowest nutrient above 0.4) is the gap**, 4 (4D) not measured.
- `--until-stable` honestly fails (top-ups, population on the floor) and prints
  why. Expect that until M3.
- **Smiting is off** (`Config.smiting = False`, 5zorro 2026-11-02) until a snapshot
  survives hunger. Piety and smiting return in M5.
- **Decided:** keep pillar 4 ("young can't die") in play. Evolution's deaths
  happen offline in the nursery (harsh `collapse_age_penalty=600`), and gentle
  play worlds start from its best brains.
- Honest state, hunger only (5 seeds × 10,000 ticks, 2D, gentle rules, unseen maps):
  | | From scratch | From `nursery-2` (no scent) | From `nursery-4` (scent) |
  |---|---|---|---|
  | Collapses / 1,000 NPC-ticks | 4.1 | 2.9 | **2.7** |
  | Lowest nutrient (bar: 0.4) | 0.30 | 0.33 | 0.34 |
  | Births vs top-ups | 15 vs 258 | 156 vs 130 | **243 vs 64** |
  - Starvation causes most collapses (nutrients ~76%, body ~12%, stink ~13%).
  - Scent only helps through the nursery; from scratch it changes nothing.
  - Drift in gentle worlds is much smaller with scent (late generations +0.3
    instead of +1.1). One world in five passed the stability check.
  - Nursery snapshots are local only (`snapshots/` is gitignored, ~1 MB each).
    `nursery-3/4` have scent; `nursery-1/2` don't and need `--set food_scent=false`.
    Retrain with the commands in `scripts/run_headless.py`'s docstring.
  - Nobody learns or shares secrets, and there's no channel for food
    locations. No social structure is measurable yet (`openitems.md`).
  - In 4D the scripted forager never collapses, so the 4D economy is easy.

## Where to pick up
1. **Criterion 3:** diagnosed (plan, under slice 6). Not diet balance: intake is
   too low (small bites from the thin food layer; eating counts as idle, so hunger
   runs 2.5× while eating). Even the scripted forager only reaches 0.40–0.42.
   Waiting on 5zorro: should eating reset the idle streak, and is 0.4 the right bar?
   Rules changes mean retraining the nursery.
2. **Criterion 4:** train a 4D nursery (`--dims 4 --size 10`) and measure.
3. Other levers: **seasons** as a config schedule (famine winters, mostly for
   consistency); play-world drift fixes (re-seed, lower mutation in play).
4. Later (M5): the piety lifecycle (full until adulthood, then declines; share
   piety like a secret) as the path to answered prayers and shared secrets.
