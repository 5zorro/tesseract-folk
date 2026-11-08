# Plan: M3 Stable population from real births

Status (2026-11-08): **started.** The goal was rewritten with 5zorro the same
day (`docs/ROADMAP.md`). Slice S1 (the baseline) is next.
Open decisions (bottom) are 5zorro's.

**For a new session:** read `handoff.md`, `gotchas.md` and this file. M2's plan
(`docs/plan-m2-diet-travel.md`) holds the births research so far (R9 mating,
R11 hunger limit, R12 fertile edge, R13 split hunger); its laws are summarized in
`docs/research-tuning.md`.

## Goal (from ROADMAP.md)
In 2D, 3D and 4D, play worlds started from each dimension's M2 nursery at its
M2 hunger hold a steady population from their own births:
1. **Births replace the dead:** births outnumber top-ups at least 10 to 1
   (top-ups at most `stable_max_spawn_fraction` = 0.1 per birth).
2. **Off both rails:** the population stays above the top-up floor
   (`min_population` 30) and below the cap (`max_population` 250). A world on
   either rail is held there by a rule, not by its NPCs.
3. **Steady:** population std / mean below `stable_max_cv` (0.15).

All three are judged over the second half of each run, per world (proposed:
see open decisions), from population samples every 250 ticks.
What holds a passing world steady (food, poop and fertilizer, stink, crowding,
aging) is measured and reported, not required (rule 6).

**Worlds** (M2's, `scripts/ladder.py` "time" shapes):
| Dims | Size, radius | Hunger (M2 pick) | Nurseries |
|---|---|---|---|
| 2D | 32, 4.0 | 1x | `snapshots/hdist/d2-...-metabolism_rate0.01-nutrient_decay0.003-n100/101` |
| 3D | 14, 1.88 | 0.9x | `snapshots/hdist/d3-...-metabolism_rate0.009-nutrient_decay0.0027-n100/101` |
| 4D | 10, 1.23 | 0.36x | `snapshots/arena-fixed/persist-n100..103-r35` (700k ticks) |
Plus scratch worlds (no nursery) at the same settings, for comparison.

## What we know already (M2 research, 2026-11-06 to 11-08)
- **Hunger decides births.** Births stop when a random walk from one food to
  another costs ~0.14 of a hunger clock (R11, 2D-4D); M2's hunger picks sit
  near that edge so births could happen at all.
- **Today's play worlds (10k ticks, M2 ladders):**
  | | Births | Top-ups | Mean population |
  |---|---|---|---|
  | 2D, 1x | 87 | 113 | 36 |
  | 3D, 0.9x | 567 | 53 | 98 |
  | 4D, 0.36x, persist brains | ~20 | ~111 | 30 (floor) |
  | 4D, 0.36x, scratch | 22 | 125 | 30 (floor) |
- **3D is bistable** (Allee effect, R12): at 0.85x, worlds either boom to the
  250 cap or stay at the 30 floor, none in between. A mean of 98 can be a mix of
  both, so 3D's good ratio may still fail criteria 2 and 3.
- **4D is density-limited:** 30 NPCs in 10,000 cells. Mates within reach
  ~ N (1 + 2d) / cells (R9 law); NPCs sit as if scattered at random.
- **4D's trained brains have no more births than scratch ones** (the table
  above): M2 trained foraging, not finding a mate.
- **Most mate attempts come from NPCs too young, thin or unwell** (R9).
- **Equilibrium density has no law yet** (laws table: "open").
- **Stink only matters in crowded 2D** (17-53% of 2D collapses).

## Slices

### Slice S1: Baseline, measured the M3 way
- Add to `scripts/sweep.py`'s per-run result, over the late window: births,
  top-ups, population mean and cv, share of samples on the floor and at the
  cap. (Today it reports births and top-ups over the whole run, and the
  population only at the end.)
- `scripts/m3_ladder.py`: the worlds above, nursery and scratch, several seeds,
  one verdict per world and a summary per dimension; reuse finished runs only
  with the same settings (the review's rerun guard).
- Report which criterion fails where, and how a world's population moves
  (booms, floors, swings).

### Slice S2: What regulates a steady world (measure, don't add)
For worlds off both rails: deaths by cause over time, density, food stock,
fertilizer and stink against population. Is there a negative feedback below
the cap, and which one?

### Slice S3 onward: per dimension, after S1
Candidates, each measured before it's adopted:
- **2D** (births ~ top-ups): how far from the fertile edge is 1x? The kids
  rules (birth weight + child credit) raised 2D births 12x at 1.25x (R11 hint).
- **3D** (bistable): what makes a boom stop below the cap, if anything?
- **4D** (density): a world sized so 30-250 NPCs can meet (fewer cells per
  NPC), `mate_sense` (built, off by default), or breeding for births in the
  nursery. A pure world-size change is the cleanest test of the R9 law.

## Open decisions (5zorro)
1. **Per world or on average?** Proposed: every world must pass, since a mean
   hides bistable worlds. Alternative: a share of worlds (e.g. 80%).
2. **May hunger move again for M3?** Only where every M2 goal still holds.
3. **May the 4D world change shape** (size, initial NPCs, caps) for M3, given
   that 4D Miner's own world sets the real density later?
4. **Run length:** proposed 30,000 ticks per world, judged on the second half
   (`Config.old_age` is 1,500 ticks, so the judged half spans ~10 lifetimes).
