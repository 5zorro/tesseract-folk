# Plan: M2 Diet drives travel

Status: **slices 1–3e done (2026-11-04); thresholds settled. The move-based
metric (3c) shows diet-seeking in 2D (all criteria met there, with criterion 3
revised) but none in 4D. Slice 3d (dimensions ladder) found brain size isn't
the limit: 4 hidden units pass in 2D, and bigger never helps. Next (5zorro):
accept the revised criterion 3; slice 3e (travel time) found 3D learns diet-seeking
and is one criterion short; full 4D starves with matched trips. Then 5zorro picks:
3D as the 4D Miner target, then 4a (memory stack) or a 3D trip-time ladder.** Slices are ordered; each one ends with tests passing and a commit.
Open decisions (bottom) are 5zorro's.

**For a new session:** read `handoff.md`, `gotchas.md` and this file. M1's plan
(`docs/plan-m1-survival.md`) holds the nursery recipe and every rule change so far.

## Goal (from ROADMAP.md)
**Pass:** `diet_diversity` stays high *and* NPCs move between food zones (add a
metric: distinct food zones visited per lifetime).

The point is causal: NPCs should travel *because* their diet needs it, not just
wander. So the test compares the normal world with a control where travel isn't
needed for a balanced diet.

**Criteria** (over 5 seeds × 10,000 ticks, 2D, play worlds started from the
nursery, as in M1). Settled 2026-11-03 with criterion 1 raised to 0.9 (see slice 2):
1. `diet_diversity` stays at or above 0.9 in the last quarter.
2. NPCs eat in the zones of all three food types: the mean number of distinct
   food types eaten *inside a zone* per lifetime is at least 2.5.
3. **Diet drives the travel:** NPCs switch between zones more often in the normal
   world than in a "shared patches" control world (every food type grows in the
   same patches, so no travel is needed), beyond seed noise.
4. The same holds in 4D (`--dims 4 --size 10`, `food_patch_radius=2.0`, a
   shorter run is fine).

## What we know already (2026-11-02)
- **`diet_diversity` is already high:** about 0.97 in nursery-8's run (it's a
  per-250-tick entropy of food types eaten; 1 = perfectly even). Criterion 1 is
  likely met today. The question is criterion 3.
- **Food types overlap a lot.** In 2D, 57–75% of cells can hold a full bite of
  two or more types, and 8–23% of all three (seeds 0–2). In 4D (radius 2),
  44–60% hold two or more. So an NPC can probably eat a balanced diet while
  barely moving. Patches are huge (`gotchas.md`).
- **`eat` already picks the best food here.** The eat action chooses the food type
  that best fixes the NPC's deficits at that cell. That's an instinct, and it
  makes balanced diets easy wherever types overlap. Brains still decide *where*
  to be and *when* to eat.
- **Food scent exists** (M1 slice 6): brains can smell each food type's direction,
  which is the sense travel needs.
- The world doesn't remember where patches are. `World._make_capacity` draws the
  patch centers and throws them away, so there's no "zone" to measure yet.

## Slices

### Slice 1: Zones and travel metrics ✅ (2026-11-02)
**Built:**
- `World.patch_centers`, `World.zones` (types × cells; patch index or -1) and
  `World.zone_at`, made in `_make_capacity` with no extra random draws.
  `Config.zone_core` (0.5) sets the core.
- `NPC.zones_eaten`, `last_zone`, `zone_switches`, `record_zone`. Only bites
  taken from the ground count (carried food isn't a place). A collapse keeps the
  zones but resets `last_zone`, so waking up elsewhere isn't a switch.
- `Stats.record_life` (at each death) and `travel_summary`; the `zone_switches`
  counter. `run_headless.py` prints a travel line; `sweep.py` prints a "Diet and
  travel" table (diet over the last quarter; travel over lives ending in the late
  window that lasted 500+ ticks).
- Snapshot format 3 saves the zone map; older snapshots rebuild it from the seed.
- Tests: `tests/test_zones.py` (2D and 4D).

*Fixed in slice 2:* a switch first counted any change of zone, so eating a
second food where two zones overlap counted as travel (the scripted forager,
which barely moves, logged 6 switches per 1,000 ticks). Now a switch needs the
NPC to have left its previous zone. Test:
`test_eating_another_food_where_zones_overlap_isnt_a_switch`.

**Original proposal:**
- **World keeps its patch centers:** `world.patch_centers[t]`, a list per food
  type, recorded while making capacity (same rng draws, so worlds don't change).
  Saved in snapshots (format 3; older snapshots recompute them, since the same
  seed draws the same centers).
- **What a zone is:** a cell belongs to zone (t, i) if patch i is the nearest
  center of type t and the cell is in its core (`capacity[t] ≥ zone_core *
  food_capacity`, a new config value, e.g. 0.5). Cells outside every core belong
  to no zone. Works in N dimensions through `wrapped_delta`.
- **Per NPC, kept through collapses, saved in snapshots:**
  - zones eaten in (the set of (t, i) where it took a bite of type t inside zone
    (t, i)),
  - zone switches (a bite in a different zone than its previous in-zone bite).
- **Stats and sweep columns:** mean distinct zones and distinct zone *types* per
  lifetime (NPCs with lifetime ≥ 500), and zone switches per 1,000 NPC-ticks.
  `run_headless.py` prints them in its summary.
- **Tests:** zones match patches at dims 2 and 4; eating inside a core records the
  zone and outside doesn't; switches count only changes; snapshot round trip
  keeps zones and resumes identically; mass and determinism unaffected.

### Slice 2: Baseline measurement ✅ (2026-11-02)
Added `sweep.py`'s distance column: straight-line distance from where each NPC
stood 100 ticks earlier (late window; NPCs that collapsed in between are skipped).

Play worlds, today's defaults (`runs/2026-11-02-m2-baseline.csv`, `-baseline-4d.csv`).
Travel counts lives that ended in the second half and lasted 500+ ticks.

2D, 5 seeds × 10,000 ticks:
| Brains | Collapses | Diet | Zones / life (of 9) | Food types / life | Switches / 1k ticks | Distance / 100 ticks |
|---|---|---|---|---|---|---|
| Scratch | 1.8 ± 0.4 | 0.96 | 5.5 | 2.7 | 5.0 ± 1.0 | 9.4 |
| Scripted forager | 3.9 ± 0.8 | 0.88 | 2.9 | 2.2 | 0.7 ± 0.2 | 0.9 |
| Nursery-8 | 0.9 ± 0.3 | 0.97 | 6.4 | 2.8 | **7.7 ± 1.2** | 10.6 |
| Nursery-scarce-2 | 0.9 ± 0.2 | 0.96 | 5.9 | 2.8 | **7.8 ± 0.7** | 9.3 |

4D (radius 2), 5 seeds × 5,000 ticks:
| Brains | Collapses | Diet | Zones / life | Food types / life | Switches / 1k ticks | Distance / 100 ticks |
|---|---|---|---|---|---|---|
| Scratch | 1.4 ± 0.2 | 0.96 | 3.5 | 2.1 | 2.1 ± 0.4 | 5.3 |
| Scripted forager | 2.3 ± 1.5 | 0.93 | 3.3 | 2.2 | 2.5 ± 2.6 | 1.1 |
| 4D nursery-2 | 0.6 ± 0.0 | 0.97 | 4.0 | 2.4 | 2.4 ± 0.5 | 4.9 |

Reading:
- **Diet is high for every brain** (0.96–0.97). Only the scripted forager, which
  barely moves, drops lower (0.88 in 2D).
- **Everyone wanders.** Even scratch brains cover about 9 cells per 100 ticks in
  2D. So distance alone can't show that diet drives travel.
- **Trained brains switch zones about 55% more than scratch** (7.7–7.8 vs 5.0)
  while covering about the same distance. That's the first hint of purposeful
  travel; slice 3's control is what can confirm it.
- **Food types per life is partly free:** the scripted forager reaches 2.2 of 3
  while hardly moving, because zones overlap.
- **4D falls short:** 2.4 food types per life, about 2 switches per 1,000 ticks,
  and the 4D nursery travels no more than scratch.

**Thresholds, settled by 5zorro (2026-11-03)**; these replace the draft criteria in Goal:
1. Diet ≥ **0.9** (0.8 would pass even a forager that sits still).
2. Food types eaten in-zone per life ≥ **2.5** (as drafted). Met in 2D (2.8), not
   in 4D (2.4).
3. Shared-patches control (slice 3): trained brains switch zones more in the
   normal world than in the control, beyond seed noise.
4. 4D: same thresholds.

**Original proposal:**
Measure today's worlds on the new metrics, 5 seeds × 10,000 ticks (4D: 5,000):
scratch, scripted forager, `nursery-8`, `nursery-scarce-2`, and in 4D
`nursery-4d-2`. Record a table here, then settle the criteria thresholds with 5zorro.
Also record how far NPCs travel (mean distance from where they were 100 ticks
earlier), to tell "wanders a lot" from "goes between zones".

### Slice 3: The shared-patches control (`sim/world.py`, `sim/config.py`)
**Built (2026-11-03):**
- `Config.food_layout`: `"separate"` (default, today's worlds, bit-identical) or
  `"shared"`. Shared grows every type in type 0's patches, scaled so each type
  keeps exactly its total capacity in the separate world. Same rng draws, so
  shrines and starting NPCs match too. Unknown values raise `ValueError`.
- Zones in the shared layout are the same cells for every type (cores come from
  the unscaled patch shape), so eating two foods in one patch is never a switch.
- Caveat: because totals are matched, a type's peak can sit above or below
  `food_capacity` (2D seed 0: 2.0, 1.5, 1.22). Same food overall, different
  height.
- Tests: `tests/test_zones.py` (shared shape and totals in 2D and 4D, bad
  value refused, snapshot round trip).

**Results (2026-11-03;** `runs/2026-11-03-m2-shared-2d.csv`, `-4d.csv`; travel
counts lives ending in the second half that lasted 500+ ticks):

2D, 5 seeds × 10,000 ticks:
| Brains | Layout | Collapses | Stink % | Diet | Food types / life | Switches / 1k ticks | Distance / 100 ticks |
|---|---|---|---|---|---|---|---|
| Scratch | separate | 1.8 ± 0.4 | 0 | 0.96 | 2.7 | 5.0 ± 1.0 | 9.4 |
| Scratch | shared | 1.4 ± 0.3 | 4 | 0.95 | 2.8 | 2.4 ± 0.3 | 9.5 |
| Nursery-8 | separate | 0.9 ± 0.3 | 6 | 0.97 | 2.8 | 7.7 ± 1.2 | 10.6 |
| Nursery-8 | shared | 1.6 ± 0.2 | 42 | 0.97 | 2.9 | 4.0 ± 0.8 | 9.9 |
| Scripted | separate | 3.9 ± 0.8 | 15 | 0.88 | 2.2 | 0.7 ± 0.2 | 0.9 |
| Scripted | shared | 4.1 ± 0.8 | 100 | 0.95 | 3.0 | 0.3 ± 0.2 | 2.3 |

4D (radius 2), 5 seeds × 5,000 ticks:
| Brains | Layout | Collapses | Diet | Food types / life | Switches / 1k ticks | Distance / 100 ticks |
|---|---|---|---|---|---|---|
| Scratch | separate | 1.4 ± 0.2 | 0.96 | 2.1 | 2.1 ± 0.4 | 5.3 |
| Scratch | shared | 1.3 ± 0.2 | 0.97 | 2.2 | 1.0 ± 0.4 | 5.4 |
| 4D nursery-2 | separate | 0.6 ± 0.0 | 0.97 | 2.4 | 2.4 ± 0.5 | 4.9 |
| 4D nursery-2 | shared | 0.8 ± 0.0 | 0.97 | 2.5 | 1.2 ± 0.5 | 4.9 |

Reading:
- **Criterion 3 passes as written, but it doesn't show what it was meant to.**
  Trained brains switch zones about twice as often in the separate world (2D
  7.7 vs 4.0; 4D 2.4 vs 1.2). But **scratch brains show the same 2×** (5.0 vs
  2.4; 2.1 vs 1.0), at the same distance. So the gap comes from the layout's
  geometry, not from diet-seeking: the separate world has 9 zones to bump into,
  the shared one only 3 places.
- Trained brains switch about 60% more than scratch in **both** layouts. They
  hop between patches more, whether or not their diet needs it: food-seeking,
  not yet diet-seeking.
- **The shared control isn't neutral:** everyone crowds the same 3 patches, so
  poop piles up. Stink causes 42% of nursery-8's collapses there (6% in the
  separate world), and all of the scripted forager's.
- Criteria status: 1 (diet ≥ 0.9) met in 2D and 4D. 2 (≥ 2.5 food types per
  life) met in 2D (2.8), not in 4D (2.4). 3 met only literally. 4 not met.

**Proposed next (for 5zorro): slice 3b, a direct test of diet-driven travel.**
Each time an NPC switches zones, record whether the new zone's food type is
the one richest in the nutrient it was lowest on when it left. Chance is about
1 in 3 (weighted by how much of each type's zone it could reach). Diet drives
travel if trained brains beat chance and beat scratch by more than seed noise.
This needs no control world, so geometry and crowding drop out. Then slice 4's
levers can be judged on it.

### Slice 3b: Deficit-directed travel ✅ (2026-11-03)
**Built:** `World.serves(pos)` (per nutrient: is this cell in the zone of a food
rich in it?). At each zone switch, `_eat` adds to `NPC.directed_hits` (served
its lowest nutrient, measured before the bite) and `NPC.directed_chance` (share
of nutrients served there). `travel_summary` reports `directed` and `chance`
per switch; `sweep.py` adds directed/chance/lift columns; `run_headless.py`
prints them. Observation only: every other column matches slice 2 exactly.
Tests in `tests/test_zones.py`.

**Results** (`runs/2026-11-03-m2-directed-2d.csv`, `-4d.csv`; same runs and lives
as slice 2):
| Brains | 2D directed | 2D chance | 2D lift | 4D directed | 4D chance | 4D lift |
|---|---|---|---|---|---|---|
| Scratch | 0.64 | 0.39 | 0.25 ± 0.03 | 0.71 | 0.36 | 0.35 ± 0.05 |
| Nursery-8 / 4D nursery-2 | 0.66 | 0.40 | 0.26 ± 0.03 | 0.66 | 0.37 | 0.29 ± 0.04 |
| Nursery-scarce-2 | 0.65 | 0.40 | 0.25 ± 0.04 | | | |
| Scripted forager | 0.81 | 0.37 | **0.44 ± 0.10** | 0.85 | 0.40 | **0.46 ± 0.08** |

Reading:
- **Every brain beats chance by the same margin, so this lift isn't diet-seeking.**
  Trained brains match scratch (2D +0.01, 4D −0.06), and the scripted forager,
  which walks toward *any* food and knows nothing of diet, scores highest.
- **Why:** a switch is only recorded when a bite is taken, and `eat` picks the
  food that fixes the NPC's deficit whenever it's at the cell. So arrivals that
  happen to serve the need are the ones that get recorded as switches. The eat
  instinct leaks into any bite-based travel metric. Geometry adds to it: an
  NPC tends to be low on whatever its last zone didn't serve.
- **Conclusion: M2 criterion 3 is not demonstrated.** Trained brains are
  food-seekers that hop patches more than scratch; nothing yet shows they head
  for the food they need. Scratch brains are the only honest null so far.

**Proposed next (for 5zorro):**
1. **A move-based metric** that never looks at bites: on each move made while
   outside the needed food's zones, how much closer did it get to the nearest
   patch of its needed food, compared with the other foods? Judged against
   scratch brains (a random walk's drift depends on distance, so 0 isn't the
   null). Small, like 3b.
2. **The memory stack** as slice 4's first lever (draft below), judged on 1.

### Slice 3c: Move-based approach metric ✅ (2026-11-03)
**Built:** `World.need_distance` (per nutrient, each cell's distance to the
nearest patch center of a food rich in it; rebuilt from the seed, not saved).
`_record_approach` runs on every move made while the NPC is outside the zones
of its lowest nutrient's food: score = mean cells gained toward the other foods'
patches subtracted from cells gained toward the needed one. The **random-step
null** is the mean score of all 2 × dims steps from the same cell, recorded
alongside. `approach - null` (sweep column "excess") is diet-seeking beyond
chance. Bites never enter, so the eat instinct can't leak in. Tests in
`tests/test_zones.py`.

Why the null matters: scratch brains scored +0.12 raw. A random walk drifts away
from near food faster than from far food, and the needed food is usually the
far one, so random steps score about +0.04 (2D) and +0.03 (4D) on their own.

**Results** (`runs/2026-11-03-m2-approach-2d.csv`, `-4d.csv`; excess in cells
per move, lives as in slice 2):
| Brains | 2D excess | 2D vs scratch, per seed | 4D excess | 4D vs scratch |
|---|---|---|---|---|
| Scratch | 0.073 ± 0.029 | | 0.005 ± 0.004 | |
| Nursery-8 / 4D nursery-2 | 0.131 ± 0.042 | +0.058 (4 of 5 seeds higher) | 0.006 ± 0.004 | +0.002 |
| Nursery-scarce-2 | 0.157 ± 0.075 | +0.083 (5 of 5) | | |
| Scripted forager | −0.081 ± 0.035 | −0.154 | −0.130 ± 0.061 | −0.135 |
| Shared layout (any brain) | 0 by construction | | | |

Reading:
- **In 2D, diet does steer travel.** Every brain beats random steps on every
  seed, and nursery brains about double scratch: each move gains about 0.13
  cells more toward the needed food than a random step would.
- **The metric passes its checks.** The scripted forager, which walks toward
  *any* food, scores negative: food-seeking alone doesn't fake diet-seeking.
  The shared layout scores exactly 0.
- **In 4D, nobody seeks the needed food** (0.005, nursery = scratch). That fits
  4D's 2.4 food types per life. 4D brains find food, not the right food.
- Scratch brains beat random in 2D too: play worlds select a little (top-ups
  come from the hall of fame), so "scratch" isn't a blank brain.

**Proposed criterion 3, revised (for 5zorro):** nursery brains' approach excess is
above 0 on every seed and above scratch on average. **2D: met** (nursery-8 and
nursery-scarce-2). **4D: not met.** Criterion 2 also fails in 4D, so the M2
gap is now 4D. Slice 4a (memory stack) targets it; a 4D retrain with the new
metric in view is the cheaper first check.

**Original proposal:**
- `food_layout` config: `"separate"` (today) or `"shared"` (every food type uses
  the same patch centers, so all food grows together). Same total capacity, so
  the only difference is whether diet needs travel. Brain shape is unchanged, so
  nursery brains run in both.
- Measure criterion 3: zone switches, distance and collapses in both layouts,
  2D and 4D.
- **Tests:** shared layout puts every type's peak on the same cells; total
  capacity matches the separate layout within a few percent.

### Slice 3d: The dimensions ladder, brain size vs dimension (proposed, 5zorro's idea)
**Question:** what's the smallest brain that meets the goals in 1D, 2D and 3D?
The trend says what 4D brains need, before adding memory (4a) changes the
brain shape. Also: 4D Miner NPCs can't fly, so they live on a 3D surface
("3.5D", `openitems.md`). Today's 4D runs let NPCs move along all 4 axes, which
is harder than the port needs, so the 3D result may matter most.

**Making dimensions comparable** (checked 2026-11-03, 4 seeds each). Hold the
cell count near 1,000 and the share of cells where a type can be bitten
(capacity ≥ one bite) at 2D's 45%. That also matches overlap (cells with two or
more foods: 40–44% everywhere) and keeps food per cell within ±20%.
| Dims | Size | Cells | `food_patch_radius` | Inputs | Actions |
|---|---|---|---|---|---|
| 1 | 1024 | 1,024 | 55 | 38 | 11 |
| 2 | 32 | 1,024 | 4 (today) | 47 | 13 |
| 3 | 10 | 1,000 | 1.84 | 56 | 15 |
| 4 | 6 | 1,296 | 1.35 | 65 | 17 |
Found: today's 4D world (size 10, radius 2) has 10× the cells and only 27% bite
coverage (0.95 food per cell vs 1.57 in 2D): a sparser world than 2D, which may
explain part of the 4D gap by itself.

**Runs:**
- Hidden units 4, 8, 16, 32 in each dimension: 16 combinations.
- Two nurseries per combination (`collapse_age_penalty=600`, 20,000 ticks,
  nursery seeds 100 and 101): 32 nurseries.
- Each nursery seeds play worlds: 5 seeds × 10,000 ticks. Scratch at each
  hidden size as the null. Roughly 45–60 minutes on 16 cores, in the
  background.
- A small orchestration script, `scripts/ladder.py`, trains the nurseries in
  parallel and calls `sweep.py`, so the experiment can be rerun.

**Goals checked per combination** (M1 and M2): collapses below scratch, lowest
nutrient ≥ 0.4, diet ≥ 0.9, ≥ 2.5 food types per life, approach excess above 0
on every seed and above scratch. The answer is the smallest hidden size that
meets them all, per dimension, plus how the goals degrade as brains shrink.

**Not changed:** sensing, actions, mutation, nursery rules. If no size meets the
goals in 3D, the problem isn't brain size, and the levers (4a memory, patches)
come next.

**Ran 2026-11-03** (`scripts/ladder.py`, `runs/2026-11-03-ladder.csv`, nurseries in
`snapshots/ladder/`, ~45 min on 16 cores). Each cell: 2 nurseries × 5 seeds ×
10,000 ticks, against 5 scratch seeds at the same size.
| Dims | Hidden | Collapses (nursery / scratch) | Lowest nutrient | Diet | Food types / life | Approach excess (nursery / scratch) | Distance / 100 ticks | All goals |
|---|---|---|---|---|---|---|---|---|
| 1 | 4 | 4.45 / 5.17 | 0.37 | 0.76 | 2.42 | −0.011 / −0.009 | 14 | no |
| 1 | 32 | 4.85 / 5.45 | 0.35 | 0.74 | 2.40 | −0.015 / −0.026 | 16 | no |
| 2 | 4 | **0.93** / 1.78 | 0.49 | 0.96 | 2.84 | **0.117** / 0.068 | 11 | **yes** |
| 2 | 8 | 1.01 / 1.81 | 0.50 | 0.96 | 2.80 | 0.104 / 0.058 | 10 | yes |
| 2 | 16 | 1.10 / 1.78 | 0.49 | 0.96 | 2.78 | 0.123 / 0.073 | 10 | yes |
| 2 | 32 | 1.42 / 1.90 | 0.46 | 0.95 | 2.70 | 0.102 / 0.070 | 10 | yes |
| 3 | 4 | 0.85 / 0.97 | 0.59 | 0.98 | 2.84 | 0.017 / 0.007 | 4 | barely |
| 3 | 8 | 1.13 / 1.03 | 0.56 | 0.97 | 2.76 | 0.017 / 0.009 | 4 | no |
| 3 | 16 | 1.24 / 1.15 | 0.54 | 0.96 | 2.73 | 0.015 / 0.008 | 4 | no |
| 3 | 32 | 1.41 / 1.23 | 0.51 | 0.96 | 2.67 | 0.011 / 0.010 | 4 | no |
| 4 | 4 | 1.31 / 0.98 | 0.56 | 0.97 | 2.65 | −0.003 / 0.000 | 3 | no |
| 4 | 8 | 1.54 / 1.03 | 0.58 | 0.97 | 2.67 | −0.002 / −0.001 | 3 | no |
| 4 | 16 | 1.34 / 1.09 | 0.51 | 0.96 | 2.66 | −0.003 / 0.001 | 3 | no |
| 4 | 32 | 1.33 / 1.29 | 0.52 | 0.96 | 2.66 | −0.002 / −0.002 | 3 | no |
(1D at 8 and 16 hidden units look like 4 and 32; full rows in the CSV and `runs/ladder.log`.)

Reading:
- **Brain size isn't the bottleneck.** 4 hidden units meet every goal in 2D,
  including diet-seeking. Going from 4 to 32 never helps anywhere; it makes
  collapses slightly worse in every dimension, for nursery and scratch alike
  (more weights evolve more slowly in the same number of ticks). Today's 16 is
  already more than needed.
- **2D is the sweet spot:** travel matters (food types are ~10 cells apart) and
  it's learnable. Nursery brains halve collapses and seek their needed food at
  every size.
- **3D and 4D at ~1,000 cells are small worlds:** everything is a few steps
  away (3–4 cells per 100 ticks). Scratch brains already collapse less than in
  2D (~1.0), diet barely needs travel, and diet-seeking is tiny (3D) or absent
  (4D). There, nursery brains do *worse* than scratch (4D: 1.3–1.5 vs
  1.0–1.3), likely because harsh-trained pools are hard to displace in an easy
  world (`gotchas.md`, pool fitness).
- **1D fails at every size:** a line forces long trips (patches ~100 cells
  apart, and you can't go around), so diet (0.75) and nutrients (0.36) fail.
  The hardest world, not the easiest.
- **So the 4D gap is about the world, not the brain.** Today's 4D world (size
  10, radius 2) is sparse and hard, and the nursery helps there; in a small,
  dense 4D world there's nothing to learn. Whether diet-seeking appears in 3D
  or 4D needs worlds where travel matters, like 2D's.

**Proposed next (for 5zorro):**
1. ~~Bigger 3D and 4D worlds (e.g. 3D size 20, 4D size 10)~~: those sizes were
   a guess. Replaced by slice 3e, which derives sizes from travel *time* (5zorro's
   idea).
2. Then slice 4a (memory stack), which now has room: inputs aren't the limit.
3. Later: consider 8 hidden units as the default (cheaper for the C++ port).

### Slice 3e: Worlds matched on travel time (proposed, 5zorro's idea)
**Idea (5zorro, 2026-11-03):** measure the distance between foods as *time*, the
way hunger is measured, so world size has a meaning.

**The two clocks:**
- **Hunger:** a nutrient goes from full to starving (0.1) in 0.9 / 0.003 = **300
  ticks** of moving (idle hunger is 2.5× faster). Body mass burns 1% per tick
  (about 120 ticks from 1.0 to the 0.3 floor), but any food refills it.
- **Trip:** a move is one cell along one axis per tick, so a trip takes its
  grid-step (L1) distance in ticks. Measured as: from each zone-core cell of one
  food, the steps to the nearest core of another food, averaged over food
  pairs (overlap counts as 0). Script: `scripts/travel_time.py`.

**Measured** (4 seeds each):
| World | Cells | Total food | Trip (ticks) | Trip / hunger clock |
|---|---|---|---|---|
| 1D ladder (1024, r 55) | 1,024 | 1,900 | 102.5 | 0.34 |
| **2D today** (32, r 4) | 1,024 | 1,604 | **5.7** | 0.019 |
| 3D ladder (10, r 1.84) | 1,000 | 1,449 | 3.0 | 0.010 |
| 4D ladder (6, r 1.35) | 1,296 | 1,752 | 2.4 | 0.008 |
| 4D today (10, r 2) | 10,000 | **9,535** | 4.2 | 0.014 |

What this corrects:
- The ladder's 3D/4D trips were about half of 2D's (3.0 and 2.4 vs 5.7), not
  "a few steps vs far away". Smaller, but not the whole story.
- **Today's 4D world has 2D-like trips (4.2) but 6× the food** for the same
  number of NPCs. Abundance, not distance, is the likelier reason 4D shows no
  diet-seeking: with food everywhere, being choosy doesn't pay.
- Trips are short against hunger everywhere except 1D (2% of the clock in 2D).
  Diet travel in 2D is cheap; in 1D it's a third of the clock, and 1D fails.

**Design:** hold the two things that set the economy fixed, and vary only the
dimension: **the same total food** (so the same food per NPC, with today's
population) and **the same trip time** as 2D (5.7 ticks). Patch radius sets
the food; world size sets the trip. Computed (radius found per size for ~1,600
food):
| Dims | Size | Cells | Radius | Trip (ticks) |
|---|---|---|---|---|
| 2 | 24 / 32 / 48 / 64 | 576 / 1,024 / 2,304 / 4,096 | 4.6 / 4.05 / 3.9 / 3.8 | 2.7 / **5.7** / 11.0 / 16.7 |
| 3 | 10 / 12 / 14 / 17 / 20 | 1,000 – 8,000 | 2.1 – 1.8 | 2.5 / 3.9 / **5.3** / 6.9 / 8.6 |
| 4 | 6 / 8 / 10 / 12 | 1,296 – 20,736 | 1.3 – 1.2 | 2.5 / 4.1 / **5.6** / 6.8 |
So the matched worlds are **2D size 32 (r 4), 3D size 14 (r 1.88), 4D size 10
(r 1.23)**.

**Runs:** those three worlds × hidden units 8 and 16 × (2 nurseries + scratch)
× 5 seeds × 10,000 ticks, with `scripts/ladder.py` (its `WORLDS` table becomes
an option). Then, if diet-seeking appears in 3D and 4D, a trip-time ladder in
one dimension (e.g. 2D at 6, 11 and 17 ticks) to see how the ratio drives it.

**Ran 2026-11-04** (`python scripts/ladder.py --worlds time --hidden 8 16`,
`runs/2026-11-03-ladder-time.csv`; 2D nurseries reused from slice 3d, since the
world is identical):
| World | Hidden | Collapses (nursery / scratch) | Diet | Food types / life | Approach excess (nursery / scratch) | Body starvation | Births | All goals |
|---|---|---|---|---|---|---|---|---|
| 2D size 32 | 8 | **1.01** / 1.81 | 0.96 | 2.80 | **0.104** / 0.058 | 35% | 90 | **yes** |
| 2D size 32 | 16 | 1.10 / 1.78 | 0.96 | 2.78 | 0.123 / 0.073 | 34% | 80 | yes |
| 3D size 14 | 8 | **0.94** / 2.50 | 0.96 | 2.30 | **0.062** / 0.032 (10/10 > 0) | 26% | 14 | all but types |
| 3D size 14 | 16 | 1.15 / 2.49 | 0.96 | 2.06 | 0.048 / 0.031 (10/10 > 0) | 30% | 10 | all but types |
| 4D size 10 | 8 | 7.14 / 7.89 | 0.83 | 0.70 | 0.029 / 0.027 | **88%** | 0 | no |
| 4D size 10 | 16 | 7.23 / 8.23 | 0.85 | 0.69 | 0.021 / 0.024 | **88%** | 0 | no |

Reading:
- **3D, with trips that matter, learns diet-seeking.** Nursery brains cut
  collapses by more than half (0.94 vs 2.50), and head for their needed food
  beyond random on all 10 runs, about twice scratch. Only criterion 2 misses
  (2.3 food types per life vs 2.5). This is the 4D Miner case (5zorro's "3.5D"),
  and it works at 8 hidden units.
- **8 hidden units beat 16** in 2D and 3D again. Small brains are enough.
- **This 4D world starves:** 88% of collapses are body starvation, no births,
  0.7 food types per life. Matching total food and trip time left its patches
  as pinpoints: a type can be bitten on only **3% of cells** (2D 44%, 3D 17%),
  so 60 NPCs crowd a few cells. Likely also the soil loop: food regrows from
  soil in its own cell, but NPCs poop across a mostly empty world, so mass
  drains away from the tiny patches (not verified).
- **Lesson:** in higher dimensions you can't hold total food, trip time and
  coverage all at 2D's values with round patches; something gives. Search
  ("how far is food from anywhere") gets harder with dimension even at equal
  trips: 2.5 ticks in 2D, 2.9 in 3D, 4.0 in 4D from a random cell to a given
  food.
- **Births drop with space:** 3D's 2,744 cells give 60 NPCs fewer chances to
  meet (14 births vs 90 in 2D). Density matters for M3.

**Proposed next (for 5zorro):** treat **3D as the 4D Miner target** (NPCs on a 3D
surface). M2 in 3D is one criterion short (food types per life 2.3). Options:
the memory stack (4a), or the trip-time ladder in 3D. For full-4D worlds,
patches need to be a different shape (blobs that keep coverage) before brains
can be judged there.

**5zorro (2026-11-04): don't move the goalposts.** Food types per life fails in
3D *and* 4D, so it's a trend to explain first.

### Slice 3f: Why higher dimensions fail (brainstorm, 2026-11-04)
**Probe** (`scripts/probe_supply.py`; travel-time worlds, scratch brains,
3 seeds × 4,000 ticks):
| | 2D | 3D | 4D |
|---|---|---|---|
| Cells that can grow a full bite of some food | 95% | 63% | 21% |
| Full bites per clump (patch) at full growth, median | 502 | 260 | 191 |
| Food on the map after 4,000 ticks (of ~1,600 capacity) | 1,386 | 1,778 | 1,846 |
| Soil stranded where nothing can grow | 5% | 54% | 85% |
| Ground bites taken inside a zone core | 31% | 5% | **1%** |
| Mean ground bite (of a full 0.2 bite) | 39% | 24% | **7%** |
| Bites under a quarter of a full bite ("crumbs") | 56% | 72% | **91%** |
| Pick-ups per run / bites eaten from inventory | 2,190 / 0% | 3,226 / 0% | 4,935 / **0%** |

**Hypotheses, ranked by the evidence:**
1. **Crumb grazing (strong).** Patches are Gaussians, whose tails never reach
   zero, so a crumb of food grows almost everywhere. `eat` takes whatever is
   in the cell, one bite per tick, even a crumb. In higher dimensions most of a
   blob's volume is its thin outer shell (the "curse of dimensionality"), so
   NPCs mostly meet crumbs: the mean bite falls from 39% to 7% of a full bite,
   and 4D's collapses are 88% body starvation. NPCs aren't short of food; they
   graze dust next to it.
2. **Carrying is dead in every dimension.** `eat` always takes a ground crumb
   before touching the inventory, and crumbs are everywhere, so 0% of bites come
   from carried food, while pick-ups (also often crumbs) lock some mass away.
   Inventory capacity is the same in every dimension (1.0, five full bites), and
   equally useless.
3. **The food-types metric undercounts, partly a symptom of 1.** "Food types
   per life" counts only bites inside a zone core, and only 5% (3D) or 1% (4D)
   of bites land in one. Diet diversity is 0.96 in 3D, so NPCs do eat all
   three foods, just not in cores. The metric fails because the behavior (staying
   on the fringe) is real.
4. **Supply isn't the limit (5zorro's "meals per clump").** Clumps hold 190–500
   full bites, and food stays near capacity: much of it is never eaten. The
   problem is reaching it, not making it.
5. **Soil is stranded, but not binding yet.** In 4D, 85% of the soil sits where
   nothing grows (poop lands everywhere). Food is still near capacity, so it
   doesn't matter today; it will once population grows (M3).
6. **Search gets harder with dimension.** From a random cell to a given food:
   2.5 / 2.9 / 4.0 ticks. Scent spreads over 2 × dims neighbors, so it fades
   faster, and each axis's gradient carries less of the signal. Plausible,
   secondary to 1.
7. **The economy was tuned in 2D.** Bite size, satiation, the idle penalty and
   `zone_core` were all set in 2D and reused unchanged.
8. **Density and evolution time.** The same 60 NPCs in more cells mean fewer
   births (0 in 4D, 14 in 3D), so less selection in play. The nursery runs the
   same 20,000 ticks for more weights. Longer nurseries are untested.
9. **Grid steps:** a move is one axis per tick, so diagonal trips cost up to
   √dims more than straight-line distance. Minor.

**Follow-up probes (2026-11-04), on 5zorro's question "can a smell toward richer
food let NPCs learn to ignore crumbs?":**
- **Brains don't skip crumbs today** (`scripts/probe_crumbs.py`). How often each
  brain chooses `eat` is flat whatever is in its cell (2D scratch 10–11%,
  nursery-8 26–33%; 3D and 4D nurseries 34–43%). Nursery brains learned "eat
  often", not "eat where it's rich".
- **The eat instinct itself picks crumbs.** It chooses the food that best fixes
  the NPC's deficits *per unit*, ignoring how much is there. So it takes a crumb
  of the needed food even when a full bite of another food is in the same
  cell. Of crumb bites, this is the case for **84% in 2D, 54% in 3D, 16% in
  4D**. In 4D most crumbs really are alone (patch edges, hypothesis 1).
- This also explains why brains can't learn to skip crumbs: choosing `eat` on a
  rich cell often yields a crumb anyway, so eating looks the same everywhere.

**Two causes, so two fixes (rule changes; nurseries retrain):**
- **A. The eat choice** (main cause in 2D and 3D): choose by nutrition actually
  gained this bite, value × min(bite, amount here). An instinct's rule, not a
  behavior we want to emerge, so rule 6 is fine.
- **B. A meal scent** (5zorro's idea; the 4D patch-edge cause): food smells only
  above a full bite (emission ∝ amount beyond one bite), so crumbs have no smell
  and the gradient leads to meals. Same inputs, so brain shape is unchanged.
  Lets "skip crumbs, follow the meal smell" emerge rather than be scripted.

**Candidate tests (for 5zorro; each changes the rules, so nurseries retrain):**
- For 1: patches with a hard edge (food only where capacity is at least a bite,
  like 5zorro's biomes); or `eat` ignores cells with less than some minimum.
- For 2: `eat` takes from the inventory when the ground has only a crumb.
- For 3: re-measure food types per life after 1 is fixed, before changing
  the metric.

### Slice 4: Levers, only if criterion 3 fails
Criterion 3 isn't demonstrated (slice 3b). 5zorro picked the memory stack as the
first lever (2026-11-03).

**4a. The memory stack (draft, for 5zorro; design notes in `openitems.md`):**
- `Config.memory_slots` (e.g. 4; 0 = off, so old snapshots and pools keep
  their brain shape through `LEGACY`). Each NPC keeps up to K memories: absolute
  position, tick, and a tag (the food type richest at that cell, as one-hots).
  A new memory pushes out the oldest. Saved in snapshots; no mass.
- **Sensed per slot:** filled (0/1), direction to it (`wrapped_delta / half`,
  like the known-secret sense), freshness `exp(-age / memory_tau)`, tag
  one-hots. 2D: 1 + 2 + 1 + 3 = 7 inputs per slot, 28 for 4 slots (47 → 75);
  4D: 9 per slot (65 → 101).
- **Written by** a new `remember` action ("here, now, what grows here"). One
  more output; a busy action when it writes.
- **Not in 4a:** gifts (`share` copying a memory, the inbox slot), work and
  secret tags, entity ids. Those come with M4/M5 and occupations.
- **Brain size:** sweep `hidden_units` 16 vs 32 with memory on, since inputs
  grow by more than half.
- **Measure:** retrain the nursery (2D and 4D) with memory on, then compare to
  today's nursery on the move-based metric (proposal 1 above), zone switches,
  food types per life and collapses. Also: how often `remember` fires, and
  whether memories get followed (distance to the freshest memory shrinking).
- **Tests:** stack order and eviction; sense size and contents in 2D and 4D;
  snapshot round trip; old snapshots load with memory off; mass unaffected.

**Other candidates**, one at a time, each judged with `sweep.py`, retraining the
nursery after a rule change:
- **Smaller, separate patches:** a smaller `food_patch_radius`, or a minimum
  distance between centers of different types. 5zorro's **biomes** idea
  (`openitems.md`: food 1 in "mountains", food 2 on "beaches") is the fuller
  version: name the zones, keep them apart, and make them readable to players.
- **A stronger same-food penalty** (`satiation_gain`), so staying on one patch
  stops paying sooner.
- **Carrying food** (pick up, eat later) already exists; check whether anyone uses
  it before adding anything. 5zorro's two-hands inventory idea (`openitems.md`) fits
  here if carrying matters.

## Known gaps carried from M1 (not M2's pass criteria)
- Body starvation is about a third of collapses: nutrients stay up but mass
  intake doesn't. Travel between zones may help or hurt this; watch it.
- Births still trail top-ups in 2D (M3).

## Open decisions (5zorro)
- ~~The criteria thresholds~~: settled 2026-11-03 (slice 2, "Thresholds").
- **Is the eat action's food choice OK as an instinct?** It picks the best food
  at a cell automatically. Keeping it makes M2 about *where* NPCs go, not *what*
  they choose to eat once there. The alternative is one eat action per food type,
  which grows the brain and needs a retrained nursery.
- **Judge M2 with nursery brains, like M1?** Recommended, since play worlds barely
  select. Retrain the nursery whenever M2 changes the rules.
- **Zone core threshold** (`zone_core`, 0.5 of `food_capacity` proposed): how big
  a "zone" is. Smaller cores make the metric stricter.

## Tuning log
| Date | Change | Why | Effect (seeds × ticks) |
|---|---|---|---|
