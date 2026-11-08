# Plan: M3 Stable population from real births

Status (2026-11-08, late): S1 baseline, S1b probe, S3 (births race, cross
entry) and S3b (poop and soil diffusion, built, off by default) done; no world
passes yet. Soil diffusion ends the soil mining: births-race worlds no longer
crash, they sit at the population cap (250) instead. 5zorro (2026-11-08):
soil diffusion should be the default, hunger may move, every world should
pass M3, and fix M2's 4D diet goal too if the map was the cause.
`soil_diffusion` 0.1 is the default since 2026-11-08 (re-baseline below).
**Next: S3c (re-measure hunger under the new physics, for M2's axes and
with mating), the M2 recheck (S3e), and the meals rule (S3d, 5zorro's
idea).**
The goal was rewritten with 5zorro on 2026-11-08 (`docs/ROADMAP.md`).
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
Why scoring births doesn't break rule 6: having children is what fitness
means in evolution; rule 6 forbids rewarding social behaviors (trading,
sharing) whose emergence is the experiment. Scoring only collapses was the
proxy, "rewarding B while hoping for A" (5zorro's management-accounting
framing, Kerr 1975).

**Built (2026-11-08):** `arena.py --arms births cross births-cross`.
- **Signal check first** (4D, 5 hall-of-fame brains x 4 scenarios, 1,200
  ticks): births per scenario, persist n100 vs n101 (lost mating):
  | Scenario rules | n100 | n101 |
  |---|---|---|
  | 1x hunger, 30 founders | 2.2 (0.8-3.8 per brain) | 0.0 |
  | 0.36x hunger, 30 founders | 10.7 (8.0-13.5) | 0.0 |
  | 0.36x hunger, 60 founders | 34.8 (20-48) | 0.0 |
  So births are scored at the breed hunger (`--birth-test`, default the
  nursery's rules), 30 founders as in every race, while collapses stay scored
  at 1x (`--test`), keeping the harsher test that raised diet in R14.
- **Score** per scenario pair (same seed, two rule sets): collapses per 1,000
  founder-ticks at 1x - `--birth-weight` (5) x births per 1,000 founder-ticks
  at 0.36x. At 5, the spread in births between brains (~0.2-0.4 per 1,000
  founder-ticks) is worth about as much as typical collapse differences; the
  weight is a choice, a candidate for a ladder (0, 2, 5, 10) if S3 shows an
  effect.
- **Cross entry:** after the race and write-back, the 10 picks are crossed in
  20 random pairs (uniform crossover, no mutation, keyed on nursery seed and
  round), the 20 crosses race on their own seeds (round + 500), and only the
  best 10 crosses enter (marked raced). Parents leave the hall of fame.
- **Run:** `arena.py --dims 4 --breed H --play H --arms births cross
  births-cross --rounds 35 --play-every 5 --out snapshots/s3 --csv
  runs/s3-4d.csv` (H as in R15), compared with persist
  (`runs/arena-4d-persist-fixed.csv`, `runs/m3-baseline.csv`).

**Result (2026-11-08, `runs/s3-4d.log`, `runs/m3-s3-*.log`).**
Arena play worlds (10,000 ticks, 0.36x, round 35; persist from
`runs/arena-4d-persist-fixed.csv`):
| Arm | Births | Top-ups | Pop (end) | Types | Diet | Nutrient | M2 goals |
|---|---|---|---|---|---|---|---|
| persist | 22 | 112 | 30 | 2.67 | 0.86 | 0.91 | all |
| births | 1,105 | 1.5 | 169 | 2.31 | 0.82 | 0.57 | not types |
| cross | 0.8 | 121 | 30 | 2.71 | 0.86 | 0.90 | all (rounds 20, 25, 35) |
| births-cross | 1,111 | 0.0 | 178 | 2.33 | 0.83 | 0.57 | not types |
- **Scoring births brings mating back** in all 4 nurseries (births per play
  world 963-1,162 from round 20 on), at a cost: food types ~2.3 (< 2.5).
- **Cross entry alone doesn't:** without births in the score, mating fades as
  in persist (0.8 births). It forages best of any 4D run so far (types 2.71,
  diet 0.86), but that's one run of 4 nurseries.
- **M3 ladder (30,000 ticks, judged 15-30k): no world passes in any arm.**
  births 55-176 births vs 125-180 top-ups, pop 31-43; births-cross similar;
  cross 0-4 births. The 10,000-tick play worlds saw only the boom.

**Why: boom, then the food cores are mined out** (one births-n101 world,
seed 0, traced every 1,000 ticks):
| Tick | 1k | 2k | 5k | 8k | 10k | 12k | 15k | 30k |
|---|---|---|---|---|---|---|---|---|
| Population | 162 | 250 (cap) | 247 | 194 | 107 | 44 | 30 (floor) | 30 |
| Food | 1,289 | 791 | 313 | 223 | 229 | 244 | 234 | 197 |
| Body per NPC | 2.99 | 2.72 | 1.26 | 1.09 | 1.15 | 1.32 | 1.21 | 1.24 |
Body falls below the 1.2 needed to mate, births stop, the population ages
out. Food never recovers because **the richest 10% of cells (57% of all food
capacity) lose their soil**: 1.0 per cell at the start, 0.067 at 3k, 0.004 at
15k, while the rest of the world gains it (1.0 -> 1.18). NPCs eat in the cores
and poop wherever they walk; food grows only from its own cell's soil and
nothing carries soil back. Scratch worlds drift the same way, slower (core
soil 0.40 at 3k, 0.07 at 30k; food 1,658 -> 829), so this likely also drives
the S1 baseline's decline. In ecology this is nutrient export by animals
(e.g. lateral transport from feeding to resting grounds; Doughty et al. 2016
on megafauna, cited from memory). The poop-fertilizer loop the original M3
text relied on doesn't close in space.

**So M3 needs a world rule before more brain work.** Candidates (each a rule
in both engines, off by default until 5zorro approves a re-baseline):
- soil diffusion (soil spreads slowly to neighbors, mass conserved);
- food growth drawing on soil within a radius, not just its own cell;
- poop decomposing into nearby cells (runoff).
Then rerun `m3_ladder.py` on the births arms (kept: `snapshots/s3/births-*-r35`,
`births-cross-*-r35`, which fail M2's types goal; see open decision 5).

### Slice S3b (done 2026-11-08): poop and soil diffusion
5zorro: "yes, poop diffusion sounds like it would prevent concentration of
plants over time, lets implement." Spec:
- `Config.poop_diffusion` and `Config.soil_diffusion` (default 0.0: fingerprints
  unchanged): each tick a fraction of each cell's poop / soil moves toward its
  neighbors' mean, like stink (`stink_diffusion`).
- **Why both:** poop lasts ~100 ticks (`poop_decompose_rate` 0.01), so poop
  diffusion alone moves mass only a few cells, and it lands where NPCs walk,
  which includes the cores. Soil diffusion is what carries mass back into a
  mined core, at a rate set by the gradient. Measure each alone and together.
- **Rule 1 (mass):** diffusion must conserve mass exactly. Use pairwise
  fluxes along each axis (what leaves one cell enters its neighbor) with the
  exact-transfer pattern, not `x += D * (mean - x)` (stink's form, which only
  conserves up to rounding); `mass_plug_every` must stay quiet. Test at dims=4.
- **Both engines (rule 7):** `sim/world.py` `World.step` (the reference engine
  runs it, line ~153) and `sim/simulation.py` `Batch._world_step_part`
  (stacked worlds, line ~791); `tests/test_engines.py` compares them.
  Range-check the new fields in `sim/config.py` like the other diffusions
  (`world.py` line ~64 checks them).
- **Then:** trace the births-n101 world again (core soil, food, population
  per 1,000 ticks; the S3 table) at a few rates, and rerun `m3_ladder.py` on
  the births and births-cross r35 nurseries. A default change needs 5zorro's
  re-baseline approval (old and new fingerprints recorded here).

**Built** (commit fc314ea): `sim/world.py` `diffuse_mass`, called by both
engines after poop decomposes (poop, then soil). Three disjoint passes of
neighbor pairs per axis (even-left, odd-left, the wrap pair), each pair an
exact transfer; first-order equal to stink's neighbor mix. Total mass drifts
at rounding level (~1e-13, the same as with it off), and fingerprints are
unchanged with both rates 0.

**Result** (`python scripts/trace_soil.py`, births-n101-r35 nursery, 4D M3
world at 0.36x, 3 seeds x 30,000 ticks; `runs/trace-soil-births-n101.txt`).
Core = cells in any food type's zone (273 of 10,000):
| Variant | Core soil 3k / 10k / 30k | Core food (share of capacity) 30k | Population 10k / 30k | Top-ups per 1k ticks, 30k |
|---|---|---|---|---|
| off | 0.066 / 0.004 / 0.002 | 0.03 | 202 / 31 (floor) | 7 |
| poop 0.3 | 0.046 / 0.002 / 0.000 | 0.02 | 165 / 31 (floor) | 10 |
| soil 0.01 | 0.25 / 0.26 / 0.32 | 0.74 | 250 / 250 (cap) | 0 |
| soil 0.03 | 0.57 / 0.60 / 0.67 | 0.94 | 250 / 250 (cap) | 0 |
| soil 0.1 | 0.74 / 0.75 / 0.78 | 0.95 | 250 / 250 (cap) | 0 |
| soil 0.3 | 0.79 / 0.80 / 0.82 | 0.97 | 250 / 250 (cap) | 0 |
| poop 0.3 + soil 0.1 | 0.73 / 0.74 / 0.76 | 0.95 | 250 / 250 (cap) | 0 |
- **Soil diffusion ends the mining; poop diffusion doesn't help** (slightly
  worse). As predicted, poop lasts too short to carry mass back; soil's
  gradient does.
- **Equilibrium:** core soil settles where diffusion's inflow balances what
  food draws out. A rate of 0.03 already holds the cores at ~0.6 and their
  food at ~0.9 of capacity; above 0.1 it barely changes.
- **The world now fails M3 at the other rail:** births run ~130 per 1,000
  ticks and the population sits at the cap with no top-ups. At 0.36x the
  map, once it keeps its soil, feeds far more than 250 NPCs. So the M3
  ladder on these worlds would fail "off rails" in every world; not run.

**Re-baseline (5zorro, 2026-11-08: "go ahead and do .1 as the soil diffusion
rate"):** `Config.soil_diffusion` defaults to 0.1 (`poop_diffusion` stays 0).
Snapshots saved without the fields load with both 0 (`snapshot.py` LEGACY),
so they resume as saved; worlds seeded from them (`brains_from`) get 0.1.
`scripts/fingerprint.py`, 600 ticks:
| World | Before (soil mining) | After (soil 0.1) |
|---|---|---|
| 2D float64 | 3426bd65dc54b903 | b78a2617357eea99 |
| 3D float64 | dcde46a3c61d5393 | 569944fb5d71ae59 |
| 4D float64 | 1447aa17ab5ffa6c | 90d126743283c0b7 |
| 2D float32 | c25bebb90a9a550a | e35c2916e621d048 |
| 3D float32 | c5977561ea6614b6 | 69fa688efb5f01c4 |
| 4D float32 | 82286d860933f3b2 | 31b99dfb70416d09 |
Every earlier M2 and M3 number was measured with soil mining. `ladder.py`
nurseries trained before the change now count as other settings and are
retrained. The kept M2 snapshots still hold their M2 scores as measured, but
their play worlds now run the new physics (S3e re-scores them).

### Slice S3c (next, after the soil default): re-pick hunger with mating as a survival axis
**Update after S3b:** the budget law still holds for fixed world physics;
S3b changed the physics, so hunger must be re-measured (5zorro: "that idea is
perfectly valid if we don't change the world physics. As we are changing the
world physics, then we have to re-measure hunger (and it probably has
stability at a lower hunger at only 4 survival axis vs 5 survival axis)").
With fertile cores, 0.36x feeds the births-race worlds past the cap, so for
M3 the window likely sits higher than 0.36x, where food, not the cap, stops
growth. **Test both axis counts under the new physics:** M2's four axes
(two nutrients, calories, stink; no births scored) and five (plus mating),
each a hunger ladder, to compare the windows as 5zorro's prediction says.
The law: the steady population (carrying capacity) as a function of hunger
and `child_mass`, and where it falls between the floor (30) and the cap
(250).

5zorro: "in a resource constrained environment... adding another constraint
without changing anything can cause collapse. Perhaps there is a law here.
perhaps we need to re-evaluate the .36 after adding the mating survival
constraint?"
- **Hypothesis (budget law):** a hunger level gives a fixed food budget per
  lifetime, shared by the survival axes (two nutrients, calories, stink, and
  now mating, whose child costs each parent 0.3 body). 0.36x was picked where
  the old axes fit with slack; mating takes from the same budget, so the old
  axes drop (measured: types 2.67 -> 2.31, nutrient 0.88 -> 0.57 in the births
  arms) and booms mine the food. Known neighbors, cited from memory: life
  history's cost of reproduction (Williams 1966; Stearns 1992), Liebig's law
  of the minimum, and Pareto fronts (one more objective moves the optimum).
- **Test:** `hunger_search.py`-style ladder over hunger (e.g. 0.25-0.5x) with
  births-race nurseries, goals = M2's and M3's together. For the law, add a
  `child_mass` ladder (the new axis's cost) and fit how the goal-meeting
  hunger window moves with it: relationship, not just a pick.
- After S3b, because today's boom-and-crash would swamp any hunger effect.

### Slice S3d (proposed, 5zorro's idea 2026-11-08): plants that grow whole meals
5zorro: "in order to make the world easier for npcs, we should have a mature
plant grow from a radius of soil and make 'complete meals', and that might
make it so that the npcs aren't eating crumbs." Draft, to be agreed before
building (both engines, Rule 1 exact transfers, tested at dims=4):
- **Why:** M2 found crumb grazing is 4D's main diet loss: patches are
  Gaussians whose tails never reach zero, so crumbs grow almost everywhere
  and 91% of 4D bites are under a quarter of a bite (M2 slices 3e/3f). The
  meal scent and `eat_most` only partly fixed it.
- **Roots:** a plant draws soil from every cell within `root_radius`
  (weighted, never more than a cell holds), not only its own cell. This
  overlaps with soil diffusion; with diffusion as the default, roots may
  only be needed for the meals.
- **Meals:** food grows as a plant that is only edible when mature: it gains
  mass until it reaches `meal_size` (e.g. a full stomach), then holds there.
  Eating a mature plant takes it whole or in bites (to agree); an immature
  plant can't be eaten, so there are no crumbs.
- **Changes the senses' meaning,** not their shape: food gradients and scent
  would come from mature plants only (as the meal scent does).
- **Test:** the M2 crumb probe (`scripts/probe_crumbs.py`) and the M2 and M3
  ladders, against the soil default alone.

### Slice S3e (after S3c, 5zorro): did soil mining move M2's 4D goalpost?
5zorro: "If we are able to figure out the issue in the map that caused us to
need to move the goalposts with m2, then that would be great too to fix m2 as
well." M2 lowered 4D's diet goal from 0.9 to 0.8 (and hunger to 0.36x).
**Hypothesis:** the cores were mined out in M2's 4D runs too (nurseries run
for 700k ticks), so the rich foods were mostly crumbs at the patch tails and
diet suffered. The S3 trace already showed scratch worlds drifting the same
way, slower. **Test:** trace core soil in a 4D M2 nursery and its play worlds
(`trace_soil.py --source snapshots/arena-fixed/persist-n101-r35`). Then rerun
M2's 4D ladder with soil diffusion on, scoring diet against the original 0.9,
and retrain with the persist recipe (~1 hour) if the nurseries need it. If
diet reaches 0.9, restoring that goal is 5zorro's call.

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

## Known gaps (review 2026-11-08, before compaction)
- **Luck in M3's scoring:** 5 seeds per nursery, every world must pass; the
  2D/3D nurseries (`snapshots/hdist`) were never raced, so n100 vs n101 may be
  partly nursery luck. Only 4D's were raced, and on collapses until S3.
- **Raced vs nursery merit are in different units** in one top-up tournament
  (gotchas.md, raced entries): still unmeasured. The births arms widen it
  (score = collapses - 5 x births).
- **Hunger is computed in three places:** `hunger_search.run_level`,
  `m3_ladder.hunger_rules`, and the `H` / `HUNGER_036` strings in
  `arena.py` commands and `variation_ladder.py`. One helper would keep them
  from drifting.
- **Untested:** `m3_ladder` main (the settings guard, `--nurseries`), and
  `probe_births` (a probe; it now refuses `topup_crossover`, which would
  mislabel parent distances).
- **Cross seeds:** fixed in review: `arena.py` refuses nursery seeds 5 or 10
  apart, which would share scenario seeds (crosses use round + 500,
  measure-only races round + 1000). The S3 run used 100-103: unaffected.
- **The births weight (5) is a choice;** ladder it (0, 2, 5, 10) once a
  world can hold a population.
- **`probe_births` runs float64 without the mass plug,** unlike the ladders
  (`sweep.RESEARCH_DEFAULTS`: float32, plug every 100). Its counts are a
  probe, not M3 scores; `trace_soil.py` uses the research defaults.

## Open decisions (5zorro)
1. **Per world or on average?** Answered (5zorro, 2026-11-08): "i want
   everything to pass m3 if possible": every world.
2. **May hunger move again for M3?** Answered: yes ("hunger probably must
   move"), where every M2 goal still holds.
3. **May the 4D world change shape** (size, initial NPCs, caps) for M3, given
   that 4D Miner's own world sets the real density later?
4. **Run length:** proposed 30,000 ticks per world, judged on the second half
   (`Config.old_age` is 1,500 ticks, so the judged half spans ~10 lifetimes).
5. **Keep the births-arm snapshots?** They fail M2 (types ~2.3), so the
   snapshot rule says delete; kept for now (8 folders, ~13 MB) because the
   soil-rule test needs them and they take ~3 hours to rebuild.
6. **The soil rule:** answered (5zorro, 2026-11-08): soil diffusion at 0.1
   is the default (re-baseline in S3b, fingerprints recorded there).
