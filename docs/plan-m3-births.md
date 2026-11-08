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

**Result (2026-11-08, `runs/m3-baseline.log`; 5 seeds x 30,000 ticks, judged
on 15-30k).** Means over worlds; the last four columns count worlds (of 5)
meeting each criterion:
| Dims | Source | Births | Top-ups | Pop | On floor | Births | Off rails | Steady | Pass |
|---|---|---|---|---|---|---|---|---|---|
| 2D | n100 | 41 | 210 | 30 | 78% | 0 | 0 | 5 | 0 |
| 2D | n101 | 230 | 174 | 42 | 67% | 1 | 1 | 4 | 0 |
| 2D | scratch | 48 | 225 | 30 | 81% | 0 | 0 | 5 | 0 |
| 3D | n100 | 724 | 82 | 80 | 28% | 3 | 3 | 5 | **3** |
| 3D | n101 | 69 | 192 | 31 | 71% | 0 | 0 | 5 | 0 |
| 3D | scratch | 410 | 178 | 58 | 62% | 1 | 0 | 4 | 0 |
| 4D | persist n100-n103 | 0-10 | ~210 | 30 | 95-100% | 0 | 0 | 5 | 0 |
| 4D | scratch | 35 | 194 | 30 | 86% | 0 | 0 | 5 | 0 |
- **3 of 55 worlds pass, all 3D from nursery n100.** No 2D or 4D world passes.
- **Most worlds end on the floor.** 30k-tick worlds start at 60 NPCs and fall
  to the 30 floor, where top-ups hold them; the M2 ladders' 10k-tick runs (3D
  0.9x: 567 births vs 53 top-ups) mostly saw the start. "Steady" is met almost
  everywhere only because the floor is flat; the rails criterion catches it.
- **3D is bistable by nursery and seed:** n100's worlds either thrive
  (3 of 5) or sit on the floor; n101's all sit on the floor.
- **4D's trained brains have fewer births than scratch brains** (0-10 vs 35;
  every nursery). Hypothesis, not measured: the nursery selects against
  mating (rewarding not collapsing at 0.36x, where mating costs body mass),
  "rewarding B while hoping for A". Next: mate attempts and their failure
  reasons per source (`scripts/probe_mating.py`, R9).

### Slice S1b: Why they fall (2026-11-08, `scripts/probe_births.py`)
5zorro: "why do you think it fell? how can survival be weighted toward births".
Same worlds, 3 seeds x 15,000 ticks per source (`runs/probe-births.log`).
- **Replacement arithmetic.** The young can't die (pillar 4), so every life
  ends at old age (~1,500-2,050 ticks) and a steady population needs ~2
  children per life (each birth counts for both parents). Children per life:
  | | Founders | Born | Top-ups |
  |---|---|---|---|
  | 2D n100 / n101 / scratch | 0.75 / 0.92 / 0.53 | 0.33 / 1.73 / 0.56 | 0.25 / 0.26 / 0.57 |
  | 3D n100 / n101 / scratch | 2.01 / 1.23 / 0.33 | 1.91 / 1.13 / 0.78 | 0.91 / 0.46 / 0.37 |
  | 4D persist n100 / n101-103 / scratch | 1.45 / 0.00 / 0.24 | 0.80 / none / 0.32 | 0.39 / 0.00 / 0.26 |
  Only 3D n100 reaches ~2: the source whose worlds passed (3 of 5). Top-ups
  (mutated copies) have the fewest children everywhere.
- **4D's trained brains stopped trying to mate.** Mate attempts per 1,000
  NPC-ticks: persist n101-n103 0.9-2.5, n100 34, scratch 55. Three of four
  nurseries lost the behavior; the nursery (rewarding not collapsing, where a
  child costs each parent 0.3 body) selected it away. "Rewarding B while hoping
  for A", measured.
- **Why attempts fail.** 2D/3D: too thin (body < 1.2) 29-39%, no one in reach
  21-37%, too young 17-24%. 4D: no one in reach 54-68% (density, R9 law).
- **5zorro's crossover idea (children of different parents break):**
  within each nursery, children in the far third by parent distance (RMS
  weight difference) collapse more than the near third: 2D 0.23 -> 0.54 ->
  0.71 per 1,000 ticks (3x), 3D 0.52 -> 0.70 -> 0.79 (1.5x); 4D has too few
  collapses to tell. Children per life fall with distance in 3D (1.98 -> 1.88
  -> 1.58), not in 2D (1.18 -> 1.74 -> 1.54). A correlation (distance may track
  other things, e.g. top-up parents carry ~30 mutations); the causal test is
  the slice that selects for crossing.

### Slice S2: What regulates a steady world (measure, don't add)
For worlds off both rails: deaths by cause over time, density, food stock,
fertilizer and stink against population. Is there a negative feedback below
the cap, and which one?

### Slice S3 (proposed): select for lineages, with luck kept out
The nursery scores the proxy (collapses); M3 needs lineages. Arms in
`scripts/arena.py`, each against `persist`:
- **births race:** scenarios score children per founder as well as collapses
  (shared seeds, so luck still cancels). Scenario worlds are clonal, so this
  selects for trying to mate and staying fit enough to, not for crossing well.
- **cross entry (5zorro's idea 1):** raced entries enter the hall of fame only
  as unmutated crosses of two raced brains, so brains that cross badly fail in
  the nursery, before M3.
- both together.
Scored with `m3_ladder.py` (and M2's goals, which must still hold).

### Slice S4 (proposed): survival axes x brain size, for a law
5zorro: "survival has 3 axis... i don't think we have down the optimal brain
structure law". A grid of axes switched on (nutrients 1-3, mating on/off) x
hidden units, fitting the brain size each axis count needs (requisite variety;
R7's knee ~ sqrt(weights)). After S3, so mating is being selected at all.

### Slice S5 onward: per dimension
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
