# Plan: M2 Diet drives travel

Status: **slices 1–3 done (2026-11-03); thresholds settled. The control can't
separate diet-seeking from geometry (slice 3, Reading). Next: 5zorro decides on
slice 3b, a direct "deficit-directed travel" metric.** Slices are ordered; each one ends with tests passing and a commit.
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
Most likely failure: overlap lets NPCs eat well without travel. Candidates, one at
a time, each judged with `sweep.py`, retraining the nursery after a rule change:
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
