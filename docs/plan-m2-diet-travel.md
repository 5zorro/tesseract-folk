# Plan: M2 Diet drives travel

Status (2026-11-05): **slices 1–3f and research slices R1–R6 done. 2D passes
all criteria (criterion 3 via the move metric, not yet accepted by 5zorro). 3D
fails food types per life (2.36-2.41 vs 2.5); 4D fails badly. Cause found in
3f: crumb grazing. Research (R): smell reach isn't the cause, training length
isn't, random-walk luck barely is in 3D; mutation is now lineage-adaptive at 30
per child (the default); a hall-of-fame track record (off) helps 2D a lot.
5zorro's two eat actions (slice 3g, built, off) make **3D meet every goal** and
cut 4D collapses 58%; 4D still fails. Next: decide defaults (two eat, track
record), then meal scent with two eat, then 4a.** Slices are ordered; each one ends with tests passing and a commit.
Open decisions (bottom) are 5zorro's.
**Since the GPU plan's G1 (2026-11-05)** the tick rules changed; the re-check
(`docs/plan-gpu-backend.md`, G1) gives the same verdicts within seed noise.
New M2 runs must use post-G1 nurseries.

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
  **5zorro's version (2026-11-04): give the choice to the brain** instead of
  fixing the instinct. Two eat actions replace one:
  - `eat_most`: the food with the most here (the biggest bite, for body mass).
  - `eat_need`: the food that best fixes deficits (today's rule, crumbs
    included).
  The brain picks which one, so "eat a full bite of anything when starving,
  eat the right food when a nutrient runs low" can emerge instead of being
  scripted. Cost: one more output (2D: 13 → 14 actions); inputs unchanged (the
  brain already senses each food in its cell and its own nutrients). Nursery
  retrain needed. Brain size: slice 3d found 8 hidden units enough for 47–65
  inputs, so one more output shouldn't need more; check 8 vs 16 when it runs.
  This also makes the M2 question cleaner: today the eat instinct does part of
  the diet work for every brain (`gotchas.md`, bite-based metrics).
- **B. A meal scent** (5zorro's idea; the 4D patch-edge cause): food smells only
  above a full bite (emission ∝ amount beyond one bite), so crumbs have no smell
  and the gradient leads to meals. Same inputs, so brain shape is unchanged.
  Lets "skip crumbs, follow the meal smell" emerge rather than be scripted.

**Test B ran: meal scent alone does nothing (2026-11-04).**
`Config.scent_min_food` (default 0, today's behavior; 0.2 = only food beyond a
bite smells). `python scripts/ladder.py --worlds time --hidden 8 --set
scent_min_food=0.2` (`runs/2026-11-04-meal-scent.csv`), compared with slice
3e's 8-hidden-unit rows:
| | Collapses (before → meal scent) | Body starvation | Food types / life | Approach excess | Births |
|---|---|---|---|---|---|
| 2D nursery | 1.01 → 1.08 | 35% → 30% | 2.80 → 2.72 | 0.104 → 0.105 | 90 → 89 |
| 3D nursery | 0.94 → 0.95 | 26% → 24% | 2.30 → 2.18 | 0.062 → 0.051 | 14 → 7 |
| 4D nursery | 7.14 → 7.07 | 88% → 86% | 0.70 → 0.69 | 0.029 → 0.025 | 0 → 0 |
The probes agree (`--set scent_min_food=0.2`): 4D NPCs still spend 53% of their
time on crumb cells, the mean bite is still 8% of a full one, and eat rates
are still flat whatever is underfoot.

Why, likely: the sense was never the missing piece. Nibbling crumbs is good
enough. Each crumb gives a little food, and eating counts as busy, so it also
dodges the idle-hunger penalty. And when an NPC does reach a meal, the eat
instinct still often takes a crumb of the needed food (cause A). Following a
smell only pays once eating where it's rich pays better than eating anywhere.
So A (5zorro's two eat actions) comes first; meal scent may help once A is in.
Keep `scent_min_food` as an option (default off).

**Candidate tests (for 5zorro; each changes the rules, so nurseries retrain):**
- For 1: patches with a hard edge (food only where capacity is at least a bite,
  like 5zorro's biomes); or `eat` ignores cells with less than some minimum.
- For 2: `eat` takes from the inventory when the ground has only a crumb.
- For 3: re-measure food types per life after 1 is fixed, before changing
  the metric.

### Slice R: Research before levers (5zorro, 2026-11-04)
5zorro: settle what the research says ("standing on the shoulders of giants")
before adding features or levers. Two candidates from `docs/research-tuning.md`.

**R2. Smell reach per dimension: measured, not the cause.**
`python scripts/probe_scent.py`. Part 1 (one food cell, steady smell): the
derived decay lengths hold (2.74 / 2.24 / 1.95 cells in 2D/3D/4D), and smell
drops below 10% of its peak at 5 / 3 / 2 cells. Scaling `scent_diffusion` by
dims / 2 keeps the decay length but barely moves those numbers (5 / 3 / 2;
1%: 10 / 7 / 5), because a point's smell also thins out over more directions.
Part 2 (travel-time worlds after 1,000 ticks of grazing): stepping toward the
strongest smell of a food brings an NPC closer to that food's nearest core
**92–100% of the time in every dimension**, even 6+ cells away (chance:
22–52%). Scaling changes nothing (within 0.01).
Why: NPCs sense the scent *difference* between neighbors relative to its sum,
so even a faint smell points the right way; the sim has no noise floor.
So 4D NPCs aren't lost for lack of a signal; the smell is there and points the
right way. The scaling setting was removed again (no lever without an effect);
`scent_diffusion` and `stink_diffusion` are now checked to be within 0–1.
Smell reach would matter if senses get noise or a detection threshold.

**R1. Mutations per birth: the textbook rule loses; 10-100 is a flat plateau.**
`Config.mutations_per_birth` (0 = off, the per-weight `mutation_rate` as
before; it applies to every mutated copy, births and hall-of-fame top-ups).
`python scripts/ladder.py --worlds time --dims 2 3 --hidden 8 16 --set
mutations_per_birth=K` for K = 1, 3, 10, 30 (`runs/2026-11-04-mut{K}.csv`),
against slice 3e's rows (today: ~52 at 8 hidden units, ~102 at 16). Nursery
means over 2 nurseries x 5 seeds (collapses / food types per life / approach
excess):
| Per child | 2D h8 | 2D h16 | 3D h8 | 3D h16 |
|---|---|---|---|---|
| today (52 / 102) | 1.01 / 2.80 / 0.104 | 1.10 / 2.78 / 0.123 | 0.94 / 2.30 / 0.062 | 1.15 / 2.06 / 0.048 |
| 1 | 1.46 / 2.65 / 0.059 | 0.99 / 2.84 / 0.067 | 1.87 / 1.71 / 0.027 | 1.88 / 1.60 / 0.019 |
| 3 | 1.22 / 2.72 / 0.045 | 1.14 / 2.80 / 0.057 | 1.64 / 1.87 / 0.027 | 1.64 / 1.84 / 0.030 |
| 10 | 0.86 / 2.78 / 0.137 | 1.25 / 2.74 / 0.067 | 1.01 / 2.14 / 0.030 | 1.32 / 1.94 / 0.029 |
| 30 | 1.27 / 2.71 / 0.084 | 0.94 / 2.78 / 0.096 | 1.03 / 2.17 / 0.068 | 0.76 / 2.29 / 0.045 |
Noise: the two nurseries of one cell differ by up to ~0.4 collapses and ~0.5
food types, so only big gaps count.
- **1-3 per child is worse, clearly, in 3D** (both nurseries: collapses
  1.6-2.2 vs 0.9-1.2, food types 1.3-2.0 vs 2.0-2.4, approach excess halved).
  In 2D the loss is milder. The 1/L rule doesn't fit our nursery.
- **10, 30 and today's 52-102 are within noise** of each other. The best 3D
  cell is 30 per child at 16 hidden units (collapses 0.84 / 0.69 per nursery,
  both better than today's 16-unit 1.17 / 1.12).
- **Brain size, with mutations held equal:** 16 hidden units are no longer
  worse than 8 (better at 30 per child, worse at 10, about even at 1-3). So
  slice 3d's "bigger is worse" was at least partly "more mutations is worse".
- **Not the 3D fix:** no setting reaches 2.5 food types per life in 3D. Crumb
  grazing (slice 3f) is still the lead cause.
- **Why the textbook rule loses (hypothesis):** 1/L is the optimum for long
  runs on smooth problems. Our nursery is short (20,000 ticks) and noisy (a
  brain is judged by one life in a random world), so a one-weight change is too
  small for selection to notice: copies of hall-of-fame brains are near-clones.
  Ochoa (2002) notes the best rate rises with noise and selection pressure. The
  1/5 success rule (research §2) would test this directly: log how often a
  copy outlives its parent at 1, 10, 30 and 100 per child.
- **Proposed (for 5zorro):** make `mutations_per_birth = 30` the default for new
  worlds (old snapshots keep per-weight rates via `LEGACY`), so brain sizes
  compare fairly from now on. Retrains nurseries; results otherwise unchanged
  within noise.

**R3. Do copies beat their parents? Mostly luck (2026-11-04).**
`python scripts/mutation_success.py` (`runs/2026-11-04-mutation-success.csv`):
harsh nurseries (2D/3D x 8/16 hidden units x 8 seeds, 20,000 ticks) where every
copy gets a random 1-150 mutated weights; 17,544 finished lives. Each life is
scored by collapses per 1,000 ticks lived, against its parent's when it was
copied. Copies (top-ups) only; births were too few in 3D.
- **Copies beat their parent only 8-12% of the time, at every count.** Even
  near-clones (1-5 mutations) did worse 76-83% of the time.
- **Why: the parents' scores are mostly luck.** 70-85% of chosen parents had
  never collapsed (rate 0), yet their near-clones collapse 1.2-1.6 per 1,000
  ticks, close to the population's 1.5-1.8. So ~85-90% of a chosen parent's
  apparent edge doesn't carry over. Parent-child correlation is 0.06-0.26.
  This is 5zorro's "lucky ones" (openitems: lucky brains in the hall of fame).
- **So the 1/5 success rule can't be used as-is:** most parents score 0, which
  a child can only tie, and luck swamps the rest.
- **What it does show: the cost of mutating.** Late lives (after tick 10,000),
  child collapse rate by mutated weights:
| | 1-5 | 5-20 | 20-60 | 60-150 |
|---|---|---|---|---|
| 2D h8 | 1.22 | 1.26 | 1.53 | 1.97 |
| 2D h16 | 1.43 | 1.51 | 1.69 | 2.03 |
| 3D h8 | 1.64 | 1.61 | 1.72 | 2.44 |
| 3D h16 | 1.64 | 1.65 | 1.85 | 2.11 |
  Flat up to ~20, then worse. With R1 (1-3 per child gave worse *nurseries*):
  a few mutations cost a child almost nothing, but too few starve the search
  over generations. Sweet spot ~10-30 per child.
- **Biggest lever this points at:** selection is judging brains on one noisy
  life. Re-testing the hall of fame (a track record per entry) or 5zorro's
  lineage-proven ranking should make selection far more accurate. Proposed as
  the next slice.

**R4. 5zorro's lineage-adaptive mutation: a real 3D gain (2026-11-04).**
`Config.mutation_lineage` (off by default): each child's mutated weights are
`mutations_per_birth` x (its ancestors' collapse rate / the population's now),
within 1/4x-4x. Ancestors: parents 1/2, grandparents 1/4, and so on. Relative
to the population, so a thriving lineage mutates less and the rate doesn't just
follow how harsh the world is. `python scripts/ladder.py --worlds time --dims 3
--hidden 8 --nursery-seeds 100 101 102 103 104 105 --set
mutations_per_birth=30[,mutation_lineage=true]`
(`runs/2026-11-04-mut30*.csv`). 3D, 8 hidden units, 6 nurseries x 5 seeds each:
| | Collapses | Food types / life | Approach excess | Lowest nutrient | Births |
|---|---|---|---|---|---|
| Fixed 30 per child | 1.03 ± 0.09 | 2.12 ± 0.06 | 0.057 | 0.42 | 8 |
| 30, lineage-adaptive | **0.75 ± 0.10** | **2.36 ± 0.07** | 0.056 | 0.47 | 32 |
- Paired by nursery seed: collapses lower or equal in 6 of 6, food types higher
  in 6 of 6 (chance of that by luck ~3%). 2 of the 6 nurseries reach 2.5 food
  types; the mean doesn't yet.
- 2D and 3D at 16 hidden units (2 nurseries each): within noise of fixed 30.
- Approach excess is unchanged, so the gain is in survival and diet, not in
  steering.
- Why it may work: struggling lineages get big jumps (up to 120 weights),
  thriving ones are left nearly alone (down to 7.5), so selection's few good
  finds aren't scrambled. It also partly offsets the luck in a single life
  (R3), since the score averages over ancestors.
- **Base 10 loses (5zorro's "keep it under 20" idea, tested):** same rule, base 10
  (2.5-40 per child), same 6 nursery seeds (`runs/2026-11-04-mut10-lineage-3d.csv`):
  collapses 1.30 ± 0.11, food types 2.00 ± 0.06, worse than base 30 in 6 of 6
  pairs and worse than fixed 30. Per-child cost above ~20 weights (R3) is real,
  but the nursery's search needs the bigger jumps.
- **Adopted 2026-11-04 (5zorro):** `mutations_per_birth = 30` and
  `mutation_lineage = true` are the defaults (old snapshots keep per-weight
  rates via `LEGACY`). Nurseries need retraining. Next levers from R3: re-test the hall of fame (track
  record) and a gentle-to-harsh nursery ramp (5zorro, `openitems.md`).

**R5. Hall-of-fame track record (5zorro): a big 2D gain, steadier 3D (2026-11-04).**
`Config.hall_of_fame_track_record` (off by default): each entry is scored by its
own life and every finished life of its copies (collapses per 1,000 ticks vs
the population's at the time), with 3 average lives added as a prior so one
lucky life can't outrank a proven entry; copies are picked by that score. Floor
(5zorro): after 5 copies, an entry whose copies do worse than the population is
dropped. It applies in nurseries *and* play worlds. Under the new defaults,
6 nurseries x 5 seeds, 8 hidden units (`runs/2026-11-04-{defaults,track}-{2d,3d}.csv`,
nurseries in `snapshots/ladder2`):
| | Collapses | Scratch | Food types / life | Lowest nutrient | Approach excess | Goals |
|---|---|---|---|---|---|---|
| 2D, new defaults | 0.95 ± 0.06 | 1.77 | 2.83 | 0.47 | 0.094 | all |
| 2D, + track record | **0.60 ± 0.05** | 1.43 | **2.89** | 0.52 | **0.142** | all |
| 3D, new defaults | 0.75 ± 0.10 | 2.39 | 2.36 ± 0.07 | 0.47 | 0.056 | not types |
| 3D, + track record | 0.73 ± 0.04 | 2.37 | 2.41 ± 0.02 | 0.46 | 0.058 | not types |
- 2D: better or equal in 6 of 6 nursery pairs; the best 2D result yet. Part of
  it is play-world selection (scratch worlds improve too, 1.77 -> 1.43).
- 3D: same mean, much less spread (every nursery 0.59-0.87 vs 0.47-1.08).
  Still short of 2.5 food types.
- Known gap: the hall of fame churns (most lives never collapse, so fresh
  "perfect" lives keep arriving), and a copy that finishes after its source
  was pushed out loses its credit (counted as `hall_of_fame_credit_lost`). An
  archive of displaced entries would keep those records.

**Regression check (5zorro: does what passed still pass?).** The new defaults
reproduce slice R4's lineage runs exactly (same seeds, same numbers). 2D under
the new defaults: collapses 0.95 vs 1.01 before, food types 2.83 vs 2.80, every
goal still met. 1D (coverage world, 2 nurseries): 4.46 vs 4.54 collapses,
unchanged; 1D never passed (diet 0.78).

**Proposed (for 5zorro):** turn the track record on by default.

**R6. Does a random walk's "bad luck" explain higher dimensions? (5zorro, 2026-11-05)**
5zorro: more dimensions mean more ways for a random walk to miss, so scratch brains
get less reward to learn from; train exponentially longer per dimension (base
2? e?), or spawn near food and widen the distance slowly.
`python scripts/probe_random_walk.py [--scaling]`.
- **The base is the world, not a constant.** Same width, same target (radius 2),
  same start, only dims changing: each extra dimension multiplies the mean
  search time by ~3.5x at width 10 and ~4.8x at width 14, steady from 2D to 4D:
  about 0.7 x width / target radius. Theory agrees: on a grid of N cells a walk
  needs ~N^2 steps in 1D, ~N log N in 2D, and ~N / (target size) in 3D and up
  (time follows volume, and volume = width^dims).
- **Our travel-time worlds already shrink width with dims,** so the walk from
  one food's core to another's grows only mildly: 10x the shortest trip in 2D,
  14x in 3D, 23x in 4D, landing within the hunger clock 98% / 97% / 84% of the
  time. 1D (1,024 cells) is the outlier: ~10,000 steps, 9% (gotchas.md).
- **Longer training doesn't help 3D:** 40,000-tick nurseries (6 seeds,
  `runs/2026-11-05-defaults-3d-40k.csv`) match 20,000-tick ones (collapses 0.74
  vs 0.75, food types 2.35 vs 2.36). 3D nurseries plateau by 20,000 ticks.
- **So luck isn't 3D's problem;** 3D brains already collapse 3x less than
  scratch. 4D's walk is 2x slower than 3D's and misses the hunger clock 16% of
  the time, so a spawn-near-food curriculum may matter there. If training time
  ever needs scaling, scale it by the measured walk time per world (here 3D
  x1.4, 4D x2.9 over 2D), not a fixed base.

### Slice 3g: 5zorro's two eat actions: 3D passes (2026-11-05)
`Config.two_eat_actions`: `eat` becomes `eat_most` (biggest pile here) and
`eat_need` (the old rule). New defaults, 6 nurseries x 5 seeds, 8 hidden units
(`runs/2026-11-05-twoeat.csv` vs `runs/2026-11-04-defaults-{2d,3d}.csv` and
`runs/2026-11-05-defaults-4d.csv`; `scripts/compare_runs.py`):
| | Collapses | Scratch | Food types / life | Diet | Lowest nutrient | Body starvation | Births | Goals |
|---|---|---|---|---|---|---|---|---|
| 2D base | 0.95 | 1.77 | 2.83 | 0.97 | 0.47 | 27% | 45 | all |
| 2D two eat | 1.02 | 1.44 | **2.94** | 0.92 | 0.45 | **2%** | **185** | all |
| 3D base | 0.75 | 2.39 | 2.36 | 0.97 | 0.47 | 22% | 32 | not food types |
| 3D two eat | 0.82 | 1.43 | **2.69** | 0.92 | 0.41 | **3%** | 76 | **all** |
| 4D base | 6.32 | 8.98 | 0.69 | 0.88 | 0.34 | 82% | 0 | fails 3 |
| 4D two eat | **2.63** | 3.99 | 1.72 | 0.82 | 0.31 | **9%** | 2 | fails 3 |
- **3D meets every goal for the first time;** body starvation nearly vanishes
  everywhere; 4D collapses fall 58%. Scratch worlds improve too.
- **Caveats:** 3D's lowest nutrient (0.41) sits on the 0.40 line; diet
  diversity dips (0.97 -> 0.92); 3D approach excess halves (0.056 -> 0.032),
  though still above scratch on every run.
- **Brains don't choose by situation** (probe, 3 nurseries x 2 seeds per
  dims): the share of eat_most vs eat_need is flat whether the cell holds only
  crumbs, a full bite of the needed food, or a crumb of it beside a full bite
  of another. 2D/3D brains lean eat_need (2-4 : 1), 4D brains eat_most (~3 : 1).
  So the gain is from having a full-bite option, with evolution tuning a
  fixed habit per dimension, not from context-sensitive choice. Meal scent
  (slice 3f, B) or a sharper signal may be what makes context matter.
- **4D still fails** nutrient, diet and food types.

### Slice R7: Brain width and the anneal nursery (2026-11-06)
Today's defaults (two eat actions and track record on, float32 + plug), worlds
matched on travel time (3D size 14, 4D size 10), 2 nurseries x 5 play seeds x
10,000 ticks per row. `runs/ladder-width.csv`, `runs/anneal-20k.csv`,
`runs/anneal-40k.csv`; nurseries in `snapshots/ladder3`, `snapshots/anneal`.

**Width sweep** (5zorro's "1 layer vs 2-3 vs a manager?"; width 0 = no hidden
layer, inputs straight to outputs, new; fixed-rules nursery, 20,000 ticks):

| Hidden units | 3D collapses | 3D food types | 4D collapses | 4D food types |
|---|---|---|---|---|
| 0 (linear) | 0.71 | 2.77 | 2.50 | 1.89 |
| 4 | **0.37** | 2.83 | **2.11** | 1.98 |
| 8 | 0.46 | 2.89 | 2.73 | 1.74 |
| 16 (today) | 0.68 | 2.83 | 2.50 | 1.96 |
| 32 | 0.94 | 2.76 | 3.44 | 1.43 |
| scratch (16) | 1.19-1.37 | | 3.56-4.10 | |

- **3D passes every goal at every width, even linear.** 4D fails nutrient, diet
  and food types at every width, by about the same margin.
- **Relationship:** collapses are U-shaped in width with the bottom at 4 in both
  dimensions, and 32 is worst. Past ~4 units, extra weights cost more (more to
  tune with the same 30 mutations per child and the same nursery) than they
  give. So depth wouldn't help today: the task is close to linear, and 4D's
  limit isn't brain capacity. Revisit when a second behavior arrives.

**Anneal nursery** (5zorro's population explosion then anneal,
`scripts/anneal.py`; 16 hidden units). Three changes from the brainstorm, all
found by probes: (1) "infinite age" = no aging with time (only collapses age, so
the third collapse kills) and adults from birth, because only elders die and
mating needs age 300; (2) hunger = nutrient decay *and* body burn on one dial,
because with low nutrient decay alone 4D scratch bodies still starved; (3) a
searching thermostat (up above 150 NPCs, down below 75, step halves on each
reversal, waits 750 ticks after a change), because deaths lag hunger by
thousands of ticks and "only raise" overshot into a crash to the top-up floor.

| Nursery | 3D collapses | 3D nutrient | 3D types | 3D goals | 4D collapses | 4D types | Hunger settled (x play) |
|---|---|---|---|---|---|---|---|
| Fixed rules, 20k | **0.68** | 0.44 | 2.83 | all 5 | **2.50** | 1.96 | 1.0 (fixed) |
| Anneal, 20k | 1.23 | 0.40 | 2.69 | 4 of 5 | 3.48 | 1.55 | 3D 0.56, 4D 0.37 |
| Anneal, 40k | 1.53 | 0.38 | 2.78 | 2 of 5 | 3.10 | 1.56 | 3D 0.51-0.62, 4D 0.20-0.25 |
| Scratch | 1.19 | | | | 3.82 | | |

- **The anneal loses to the fixed nursery, and a longer anneal loses more** (3D
  40k is worse than scratch on collapses).
- **Why (reading, not yet tested):** with a population line of 150, hunger
  settles at 0.2-0.6x play, so the anneal trains brains in a gentler world than
  they'll play in, and spends its boom with no selection at all (no deaths).
  The fixed nursery is harsher than play (collapse penalty 600). This fits R3
  (a parent's score is mostly luck): gentle worlds make luck matter more.
- **Relationship to measure next:** settled hunger is a carrying capacity, set
  by the population line. Lower lines force higher hunger. A sweep of the line
  (e.g. 40, 75, 150) gives hunger vs. population per dimension, and play score
  vs. settled hunger is 5zorro's "how much survival intensity crowds out good
  behavior" curve.
- **Ramp mode (5zorro: no thermostat, hunger only rises, lean on the ranked
  hall of fame).** Hunger climbs from 0.15x to an end level over 12,000 ticks,
  then phase 2 as above; the top-up floor (`min_population`) at 30 or 100.
  `runs/ramp-e*-f*.csv`.

  | Ramp end | Top-up floor | 3D collapses | 3D goals | 4D collapses | 4D types |
  |---|---|---|---|---|---|
  | 1.0x | 30 | 0.95 | all 5 | 2.91 | 1.67 |
  | 1.0x | 100 | 1.32 | 3 of 5 | 2.83 | 1.75 |
  | 1.5x | 30 | 1.16 | all 5 | 2.70 | 1.78 |
  | 1.5x | 100 | 1.01 | all 5 | **2.51** | 1.94 |
  | fixed nursery | 30 | **0.68** | all 5 | **2.50** | 1.96 |

  No ramp beats the fixed nursery; the best ties it in 4D only. **Relationship
  across every nursery so far:** the more ticks spent at full pressure, the
  better (thermostat at 0.2-0.6x < ramps, which spend 8,000 ticks at the end
  level < fixed, 20,000 ticks at play hunger plus a doubled collapse penalty).
  A gentle start spends budget without selection. A heavier hall-of-fame floor
  helps only at the harsher end. Differences of ~0.3 collapses between ramps may
  be noise (10 runs each).
- Brain diversity (mean distance from the mean brain) barely moves in any
  anneal (6.0 -> 5.5), so a "brains have converged" stopping rule wouldn't fire.
- **Found on the way:** the rounding plug posted to the median soil cell, which
  is empty after a boom; a negative entry made it negative and leaked 2.5e-5 of
  all mass in a tick. The plug's own check caught it; fixed (it now posts to
  the median of the cells that can absorb the entry). The first run of this
  slice was redone on the fix.

### Slice R8: Are the 4D senses the problem? No (2026-11-06)
5zorro: "can we look at the 4D senses? I think those may be giving bad results."
Test: a hand-written forager that sees only the sense vector, like a brain
(`sim.controllers.SenseController`; it also knows which nutrient each food is
rich in, as an instinct would). It climbs the scent gradient of the food for its
lowest nutrient, eats when it's on that food, and poops when full.
`scripts/probe_senses.py`, worlds matched on travel time, 5 seeds x 10,000 ticks.

| Dims | Forager | Collapses | Lowest nutrient | Diet | Food types | Goals (nutr, diet, types) |
|---|---|---|---|---|---|---|
| 2 | sense-only | 7.74 | 0.73 | 0.97 | 3.00 | all 3 |
| 3 | sense-only | 6.43 | 0.70 | 0.97 | 2.98 | all 3 |
| 4 | sense-only | 3.70 | 0.64 | 0.96 | 2.97 | all 3 |
| 4 | best evolved brains (R7) | 2.11 | 0.32 | 0.86 | 1.98 | none |
| 4 | `scripted` (reads the world) | 9.05 | 0.39 | 0.53 | 1.37 | none |

- **The senses carry enough information in 4D.** The oracle never once lacked a
  scent direction for its needed food (0% "blind" in every dimension), and its
  diet goals barely slip from 2D to 4D. So 4D's failure is learning, not the
  senses or the world.
- **What the brain has to learn** is a product: for each move, sum over food
  types of (my need for its nutrient) x (its scent gradient on that axis). A
  product isn't linear in the inputs; the number of terms grows with dims x
  food types (2D: 2 axes x 3 types; 4D: 4 x 3), and so does the number of
  move outputs to tune. That fits 3D passing and 4D failing at every width.
- The oracle collapses a lot (it never mates or avoids stink, and only eats
  when a nutrient is under 0.7), so it isn't a collapse benchmark; only its
  diet numbers matter here.
- **Crossover top-ups (5zorro; `topup_crossover`, built, off).** Fixed
  nursery, `--set topup_crossover=true` (so play worlds' top-ups cross too, and
  scratch rises with it). `runs/ladder-cross.csv`.

  | Dims | Hidden | Collapses, clones | Collapses, crossover | Food types, clones | Food types, crossover |
  |---|---|---|---|---|---|
  | 3 | 4 | 0.37 | 0.45 | 2.83 | 2.78 |
  | 3 | 16 | 0.68 | 0.49 | 2.83 | 2.74 |
  | 4 | 4 | 2.11 | 2.41 | 1.98 | 1.95 |
  | 4 | 16 | 2.50 | 2.51 | 1.96 | 1.93 |

  No consistent effect (two better, two worse, within ~0.3), and 4D's food
  types don't move. **Found on the way:** at the end of a 20,000-tick nursery,
  28-30 of the 30 NPCs are top-ups and only 0-3 were born. The fixed nursery
  sits on its top-up floor, so its selection is almost entirely the ranked hall
  of fame already; local breeding barely happens.
- **Lever this suggests (not built; 5zorro's call):** a "craving" sense that
  hands the brain that product directly: the scent gradient of the food it
  needs most, one number per axis (d inputs). Perception, not a scripted
  behavior (rule 6): the brain still decides whether to follow it.

- **Craving sense (built, `craving_sense`, off; 5zorro: "probably good").**
  Fixed nursery, `--set craving_sense=true`, worlds matched on travel time.
  `runs/ladder-crave*.csv`; 2D's no-craving baseline is `runs/ladder-width-2d.csv`.

  | Dims | Hidden | Collapses, no craving | Collapses, craving | Food types, no craving | Food types, craving | Goals with craving |
  |---|---|---|---|---|---|---|
  | 2 | 0 | 0.88 | 0.93 | 2.97 | 2.96 | all 5 |
  | 2 | 4 | 0.75 | 0.50 | 2.97 | 2.96 | all 5 |
  | 2 | 16 | 0.45 | 0.61 | 2.96 | 2.94 | all 5 |
  | 3 | 0 | 0.71 | 0.90 | 2.77 | 2.66 | all 5 |
  | 3 | 4 | 0.37 | 0.75 | 2.83 | 2.79 | all 5 |
  | 3 | 16 | 0.68 | 0.59 | 2.83 | 2.79 | all 5 |
  | 3 | 32 | 0.94 | 0.64 | 2.76 | 2.68 | all 5 |
  | 4 | 0 | 2.50 | 2.67 | 1.89 | 1.86 | 2 of 5 |
  | 4 | 4 | 2.11 | 2.80 | 1.98 | 1.75 | 2 of 5 |
  | 4 | 16 | 2.50 | 2.80 | 1.96 | 1.53 | 2 of 5 |
  | 4 | 32 | 3.44 | 2.68 | 1.43 | 1.83 | 2 of 5 |

  - 2D and 3D pass at every width with or without it; 4D fails at every width
    with or without it. The craving sense doesn't fix 4D, even for linear brains,
    for which "follow the craving input" is now a straight-line rule.
  - The one hint of 5zorro's "brains may need to scale with inputs": at 32 units
    craving helps (3D 0.94 -> 0.64, 4D 3.44 -> 2.68, 4D food types 1.43 -> 1.83);
    at 4 it hurts. Within noise of the other rows, so not a finding yet.
  - So 4D's gap isn't information or the shape of the computation. Left: the
    action draw (outputs are sampled at temperature 0.5 over 14 actions in 4D,
    so a right brain still mis-steps) or the search (R3: selection is mostly
    luck). **Next diagnostic:** hand-build a linear brain that follows the
    craving and eats on food, and run it through the normal action draw. If it
    passes 4D, the brain exists and evolution misses it; if not, it's the draw.
- **The diagnostic (2026-11-06, 5zorro: "yes, run it").**
  - *Hand-built linear brain* (`scripts/probe_handbrain.py`: follow the craving,
    eat on food, poop when full; mutation off) fails even in 2D (food types 1.7
    in 2D, 0.2 in 4D), at every sharpness. A linear brain can't say "eat only
    the food I need": it eats whatever is underfoot and parks on the first
    patch. So the forager's *eating* rule is a product too (need x what's
    here), like its movement rule; a working brain needs a hidden layer.
  - *Noisy forager* (`probe_senses.py --follow`): the sense-only forager does its
    own choice with chance p, else a random action.

    | Dims | p = 1 | 0.9 | 0.7 | 0.5 | 0.3 |
    |---|---|---|---|---|---|
    | 2 food types | 3.00 | 3.00 | 3.00 | 3.00 | 2.97 |
    | 4 food types | 2.97 | 2.99 | 3.00 | 2.98 | 2.95 |
    | 4 lowest nutrient | 0.64 | 0.69 | 0.73 | 0.73 | 0.65 |

    All diet goals hold in 2D-4D down to p = 0.3. **The action draw isn't the
    limit:** a policy that's right 30% of the time still passes 4D. So the 4D
    gap is the search: evolution doesn't find the policy. (The forager's
    collapse rate swings oddly with p, e.g. 4D 3.7 at p = 1, 0.01 at p = 0.3;
    not explained, and not what this probe measures.)
  - **5zorro's reading (2026-11-06):** 14 actions with 8 under direct
    selection pressure make the search harder, and time to equilibrium may
    grow per dimension (2D ~10,000 ticks, 3D ~30,000, so 4D ~90,000-120,000);
    the 4D anneal results were then mostly noise. Tested: 4D fixed-rules
    nurseries at 20,000-120,000 ticks (`runs/ladder-4d-t*.csv`):

    | 4D nursery ticks | Collapses, 16 units | Food types, 16 | Collapses, 4 units | Food types, 4 |
    |---|---|---|---|---|
    | 20,000 | 2.50 | 1.96 | 2.11 | 1.98 |
    | 40,000 | 2.36 | 1.99 | 2.10 | 2.02 |
    | 80,000 | 2.24 | 2.16 | 2.62 | 1.82 |
    | 120,000 | 2.08 | 2.23 | 2.61 | 1.80 |

    **5zorro was right that 20,000 ticks isn't 4D's equilibrium**, at 16 units:
    collapses and food types improve steadily to 120,000 ticks (still short of
    every 4D goal: nutrient 0.33, diet 0.86, types 2.23 of 2.5). **4 units
    plateau, then get worse** (and lose diet seeking in 1-2 of 10 runs). So the
    "best width is 4" of the 20,000-tick sweep was a short-budget result: small
    brains learn fast and stop; bigger ones keep going. (3D: R6 found 40,000 =
    20,000 ticks, so 3D's equilibrium is shorter.) Rough extrapolation, food
    types +0.15 per e-fold of ticks: 2.5 would take ~6x more (~700,000 ticks).
- **Movement is axis steps only** (5zorro asked): `move+k` / `move-k` per axis,
  2 x dims moves, no diagonals; distances are wrapped axis steps. Diagonals would
  mean 3^dims - 1 moves (80 in 4D), or a multi-axis step per tick from the same
  2 x dims outputs. Held until the diagnostic above.

### Slice R9: Finding a mate per dimension (2026-11-06)
5zorro: "there is probably a lot of distance between every 4D creature and
other creatures... is there a different measure for mating? ... a lot more
population density needed for the breeding?" `scripts/probe_mating.py`: play
worlds matched on travel time, ladder nursery brains (2D: scratch, no 2D
nursery yet), 4 seeds x 5,000 ticks. A mate must be in the same cell or one
step away (1 + 2 x dims cells), both must pick "mate" within 5 ticks, and each
must be an adult (300) with body >= 1.2, health > 0.5, off cooldown. There's no
"that neighbor is ready to mate" sense, only a count of neighbors.

| Dims | NPCs | NPCs per cell | Someone within reach | (if scattered at random) | Nearest NPC (steps) | Births per 1,000 NPC-ticks |
|---|---|---|---|---|---|---|
| 2 | 37 | 0.037 | 17.1% | 16.2% | 3.3 | 0.22 |
| 3 | 39 | 0.014 | 9.6% | 9.1% | 3.3 | 0.04 |
| 4 | 35 | 0.0035 | 3.3% | 3.0% | 3.9 | 0.00 |

Why mate attempts fail (share of attempts; "partner ready" was 0% everywhere):

| Dims | Too young | Too thin (< 1.2) | Health <= 0.5 | No one within reach | Neighbor not ready |
|---|---|---|---|---|---|
| 2 | 28% | 20% | 21% | 24% | 4% |
| 3 | 24% | 17% | 12% | 41% | 5% |
| 4 | 30% | 39% | 17% | 13% | 0% |

- **5zorro is right about density:** the same ~35 NPCs are 10x sparser in 4D,
  and the chance anyone is within reach falls 17% -> 3%. NPCs sit about where
  random scatter would put them (they don't seek each other).
- **Formula:** chance someone is within reach ~ 1 - (1 - (1 + 2d) / cells)^(N - 1),
  about N (1 + 2d) / cells when small. Matching 2D's 17% in the 4D world (10,000
  cells, 9 within reach) takes ~210 NPCs; in general N grows as cells / (1 + 2d).
- **But density isn't the first wall:** most attempts come from NPCs that
  couldn't mate anyway (too young, thin or unwell: 69% in 2D, 86% in 4D), and
  no attempt in any dimension found a ready, eligible partner. Births are rare
  everywhere (0.22 per 1,000 NPC-ticks in 2D), not only in 4D. That matches
  slice R8's finding that nurseries are almost all top-ups.
- **A "ready to mate" sense** would help with the 5-tick timing, but timing is
  the smallest failure today (0-5%). It matters once eligible NPCs meet often.
- Levers, not tested: more NPCs in 4D (`max_population`, density matched by the
  formula), a longer `mate_window`, a mate-ready sense, and a scent NPCs give off
  (like food scent) so they can find each other at a distance.

- **Mating sense (built, `mate_sense`, off; 5zorro, 2026-11-06).** 3 + dims
  inputs: I can mate now; a ready partner within reach; and a pheromone
  (5zorro's idea, replacing a first draft that pointed at the nearest partner
  anywhere, which was omniscient). Callers (signaled `mate` and can mate) add
  `pheromone_emission` to their cell each tick; it spreads and fades like stink
  (`pheromone_diffusion`, `pheromone_decay`), and NPCs sense its level and
  relative gradient like food scent. Only callers emit, so a seeker on the move
  doesn't follow its own trail.
- **4D, 120,000-tick nurseries with the new senses** (`runs/ladder-4d-*.csv`):

  | 4D nursery (120k ticks) | Collapses | Food types | Seeks diet |
  |---|---|---|---|
  | no new senses, 16 units | 2.08 | **2.23** | 10/10 |
  | craving only, 16 | 2.82 | 1.80 | 6/10 |
  | mating only, 16 | 2.58 | 1.99 | 7/10 |
  | both, 16 | 2.35 | 2.01 | 9/10 |
  | **both, 32** | **1.89** | 2.11 | 10/10 |

  - At 16 units the extra inputs make 4D worse; at 32 units with both, the
    fewest 4D collapses so far (types still short). Fits 5zorro's "brain size
    may need to scale up with the added inputs" (one row, 10 runs: a lead,
    not a finding).
  - **Zero births in every 4D nursery, mating sense or not** (all 30 NPCs are
    top-ups at the end). The pheromone can't help while almost no one is
    eligible (R9: too young, thin or unwell under nursery rules). A mating test
    needs worlds where NPCs can be eligible: play rules, or a gentler nursery.
- **Outputs vs training time (5zorro: "I want to get that relationship down and
  tested").** `scripts/outputs_vs_time.py`: the task fixed, outputs changed by
  switching off optional actions (`actions_off`) or adding do-nothing `stay`
  copies (`extra_stay_actions`); nurseries saved at 2.5k-40k ticks and scored in
  play; fit ticks-to-target ~ outputs^k.

  First 2D run (`runs/outputs-vs-time-2d-first.csv`; 2 nurseries x 5 seeds):

  | Arm | Outputs | Scratch | 2.5k | 5k | 10k | 20k | 40k |
  |---|---|---|---|---|---|---|---|
  | 5 actions off | 11 | 1.88 | 1.82 | 1.54 | 1.42 | 1.68 | 1.66 |
  | today | 16 | 1.60 | 1.14 | 0.88 | 0.72 | 0.47 | 0.44 |
  | +8 stay copies | 24 | 2.43 | 1.85 | 1.53 | 1.30 | 1.08 | 0.70 |
  | +16 | 32 | 3.16 | 2.04 | 1.46 | 1.17 | 0.93 | 0.75 |
  | +32 | 48 | 4.92 | 3.51 | 3.23 | 2.24 | 1.67 | 0.56 |

  - **Confound 1: extra stay copies aren't neutral at the start.** Random brains
    idle more and starve more (scratch 1.6 -> 4.9), so "ticks to a fixed
    score" (fit k = 2.2) mostly measured a worse start. Ticks to close each
    arm's *own* gap (its scratch -> 0.44): **k ~ 0.5 at both 50% and 70% of the
    gap, i.e. training time ~ sqrt(outputs)**, with noisy points (+16 faster
    than +8).
  - **Confound 2: "5 actions off" dropped `pick_up`,** and carried food is eaten
    when the ground is bare, so that arm changed the task (it never learned).
    Rerun with only give, pray, worship and share off, 8 seeds, then 3D.
  - Every arm ends near the same place given time (0.44-0.75 at 40k): more
    outputs cost time, not the final score, over this range.

  Rerun (only give, pray, worship, share off; 2D 8 seeds, 3D 5;
  `runs/outputs-vs-time-{2d,3d}.csv`). Fit of ticks to close each arm's own
  gap (its scratch -> its best) against outputs: **2D k = 0.50 (50% of the gap)
  / 0.72 (70%); 3D k = 0.03 / 0.14.** Not one relationship. Reading: a
  do-nothing output is learned away by lowering one bias, so dummy outputs
  understate what a real action costs; this method can't price real outputs.
  Fewer actions: in 3D the off4 arm learns best (0.48 at 40k); in 2D it peaks at
  10k (0.94) and slips. Kept as data; not a formula.

- **Brain size vs ideal training length (5zorro: "what was the ideal training
  tick size for each brain size? I want that relationship to be down").**
  `scripts/long_nursery.py --arms h4 h8 h16 h32 h64`, snapshots 2.5k-160k,
  today's senses, 2 nurseries x 5 seeds per point (`runs/sizes-{2d,3d}.csv`).

  | Hidden | Weights 2D | Best 2D (at ticks) | Knee 2D | Weights 3D | Best 3D (at ticks) | Knee 3D |
  |---|---|---|---|---|---|---|
  | 4 | 272 | 0.74 (80k) | 9.7k | 318 | 0.37 (20k) | 12.7k |
  | 8 | 528 | 0.65 (20k) | 9.9k | 618 | 0.46 (20k) | 12.5k |
  | 16 | 1,040 | **0.28** (80k) | 35k | 1,218 | 0.45 (40k) | 32k |
  | 32 | 2,064 | 0.60 (10k) | 8.4k | 2,418 | 0.60 (80k) | 53k |
  | 64 | 4,112 | 0.43 (160k, still improving) | 63k | 4,818 | 0.46 (80k) | 36k |

  (Knee = ticks to first get within 10% of the way from scratch to that size's
  best, in collapses.) **Ticks to the knee ~ weights^0.53 (2D) and ^0.52 (3D):
  training length grows as the square root of the brain's weight count**, the
  same exponent in both dimensions. Single points are noisy (2D 32 units).
  The best score doesn't simply improve with size.

- **4D, 700,000-tick baseline (5zorro: "use that as the baseline and take
  snapshots"; `runs/long-nursery-4d.csv`):**

  | 4D nursery ticks | 0 | 50k | 100k | 200k | 350k | 500k | 700k |
  |---|---|---|---|---|---|---|---|
  | 16 units, collapses | 3.82 | 2.33 | 2.09 | **2.07** | 2.41 | 2.41 | 2.78 |
  | 16 units, food types | 1.40 | 2.01 | 2.22 | **2.30** | 2.24 | 2.24 | 2.04 |
  | 32 + both senses, collapses | 4.16 | 2.11 | **1.94** | 2.41 | 2.70 | 2.80 | 2.85 |
  | 32 + both senses, food types | 1.27 | 2.18 | 2.18 | 1.95 | 1.90 | 1.94 | 1.82 |

  - **Nurseries peak, then get worse.** 16 units peak at 100-200k ticks, 32
    units with the new senses at ~100k; by 700k both are worse than at 50k.
    Longer isn't better past the peak, so 4D's goals aren't 700k ticks away by
    training alone (the 2026-11-06 extrapolation was wrong).
  - 4D's peak (100-200k at ~1,400 weights) is 3-6x the 3D knee for the same
    size (~32k), so dimension adds its own factor on top of sqrt(weights).
  - **Why they decay: not tested.** Candidates: brains fit the nursery's
    harsher rules (collapse penalty 600) rather than play's; the hall of fame
    or lineage-adaptive mutation drifts over a long run; or selection noise
    (R3) accumulates. Checking the nursery's own scores along the run, and
    play scores of nursery-rules worlds, would split these.
  - The 64-unit arm (both senses) is still running.
- **Directional movement (5zorro, 2026-11-06):** plans to test diagonal /
  directional movement per dimension ("plenty of games allow it"). The outputs
  curve above predicts what 3^dims - 1 move actions would cost in training.

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

- **Revised criterion 3** (slice 3c): nursery brains' approach excess above 0
  on every seed and above scratch. Proposed 2026-11-03, not yet accepted.
- ~~3D as the 4D Miner target~~: settled 2026-11-04 (5zorro): **two targets**.
  Land walkers ("flightless") live on 3D surfaces; 4D fish and birds move
  freely in 4D. So both 3D and 4D have to pass.
- **Two eat actions on by default?** (slice 3g: 3D passes, body starvation
  nearly gone; brains use a fixed habit, not situational choice.) Built,
  off. Pools would need retraining (one more output).
- **Hall-of-fame track record on by default?** (slice R5: 2D 0.95 -> 0.60
  collapses, 3D steadier.)
- ~~Mutation defaults~~: settled 2026-11-04 (5zorro): `mutations_per_birth = 30`
  with `mutation_lineage = true` are the defaults. Old snapshots keep
  per-weight mutation (`LEGACY`); `ladder.py` now refuses to reuse a nursery
  trained under other defaults. Every earlier run used the old rule, so rerun
  baselines before comparing with them.
- **Keyed randomness** (5zorro's "seed x tick" idea, `openitems.md` Speed): every
  random number from (seed, tick, entity, purpose). Its own slice, before or
  with batching? Changes every result once.

## Tuning log
| Date | Change | Why | Effect (seeds × ticks) |
|---|---|---|---|
| 2026-11-06 | `two_eat_actions` and `hall_of_fame_track_record` on by default | 5zorro: two eat actions get 3D past every goal (slice 3g); the track record keeps clones of lucky one-life entries from crowding the hall of fame, which the anneal nursery needs | Slices 3g and R5. Old snapshots stay off (`LEGACY`); nurseries trained without them must be retrained |
