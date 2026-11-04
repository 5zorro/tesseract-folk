# Plan: M2 Diet drives travel

Status: **slices 1–3c done (2026-11-03); thresholds settled. The move-based
metric (3c) shows diet-seeking in 2D (all criteria met there, with criterion 3
revised) but none in 4D. Next (5zorro): accept the revised criterion 3, then
slice 4a, the memory stack, aimed at 4D.** Slices are ordered; each one ends with tests passing and a commit.
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
  4D: 9 per slot (62 → 98).
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
