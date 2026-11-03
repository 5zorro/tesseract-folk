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
  (`Config.food_scent`, on by default), plus an economy retune with 5zorro:
  eating counts as busy, food only in patches, slower hunger (0.003), costlier
  collapses (300). Criteria settled by 5zorro (plan, Goal): **all four met, in 2D
  and 4D** (3 only easily). 4D uses `food_patch_radius=2.0`.
- `--until-stable` honestly fails (top-ups, population on the floor) and prints
  why. Expect that until M3.
- **Smiting is off** (`Config.smiting = False`, 5zorro 2026-11-02) until a snapshot
  survives hunger. Piety and smiting return in M5.
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
  - In 4D the scripted forager never collapses, so the 4D economy is easy.

## Where to pick up
1. **5zorro: call M1 done?** All criteria pass (plan, top). Criterion 3 is easy
   (scratch passes too): raise the bar, or accept it?
2. Then M2 (diet drives travel; `docs/ROADMAP.md`). Known gaps to carry along:
   body starvation is ~35% of collapses; births still trail top-ups in 2D (M3).
3. Other levers: a harsher scarcity nursery (half food gave a mild win); **seasons** as a config schedule (famine winters, mostly for
   consistency); play-world drift fixes (re-seed, lower mutation in play).
4. Later (M5): the piety lifecycle (full until adulthood, then declines; share
   piety like a secret) as the path to answered prayers and shared secrets.
