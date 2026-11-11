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
- **M2 diet drives travel is done** (2026-11-07): passes in 2D, 3D and 4D, with
  4D's diet goal moved to 0.8 by 5zorro. Hunger: 2D 1x, 3D 0.9x, 4D 0.36x.
  4D recipe and the hints for revisiting 4D diet: plan-m2 slice R15.
- `--until-stable` honestly fails (top-ups, population on the floor) and prints
  why. Expect that until M3.
- **M3 started (2026-11-08):** `docs/plan-m3-births.md`.
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
    `snapshots/ladder/` holds the slice 3d/3e/3f nurseries, named by world
    (`d{dims}-s{size}-r{radius}-h{hidden}[-rule]-n{seed}`); `ladder.py` reuses
    one only if its saved settings match.
  - Nobody learns or shares secrets, and there's no channel for food
    locations. No social structure is measurable yet (`openitems.md`).
  - 4D needs `food_patch_radius=2.0`: at the default radius every 4D cell grows
    every food, and foraging is trivial (`gotchas.md`).

## Where to pick up
**Now (2026-11-10, 5zorro's design): reaction queue and memory net.** Plan:
`docs/plan-memory-reaction.md` (results, predictions, known gaps).
- **MR0 done:** today's 2 recurrent units are a few-tick echo plus a per-NPC
  offset; holding them at 0 hurts 2 of 8 4D nurseries (kept). The shrine
  sense sways choices most (why: open).
- **MR1 done:** `Config.reaction_queue` built (both engines, LLM pawn seams,
  warm start by widening brains). A delay of 1-5 ticks costs today's brains
  nothing measurable.
- **MR2 built:** `Config.memory_slots` + a memory net carried in the genome
  (`Brain.memory`), `write_memory` for controllers. **Experiment running or
  finished:** `scripts/mr2_experiment.py` (control K = 0 vs memory K = 8 vs
  blind, Q = 3, 3 nurseries per pool x 60k ticks). Read it with
  `python scripts/mr2_experiment.py --report-only` (`runs/mr2-experiment.json`,
  log `runs/mr2-experiment.log`); compare to the prediction in the plan.
  Then fix the plan's "Known gaps" (mutation budget split first).
- Next after MR2: MR3 (hall of fame), MR4 (one brain vs two). M3 history below.

**Now (2026-11-08): M3, stable population from real births.** Plan:
`docs/plan-m3-births.md` (goal rewritten with 5zorro: births 10x top-ups, off
the floor and the cap, cv < 0.15, in 2D/3D/4D at each dimension's M2 hunger).
S1 baseline done: 3 of 55 worlds pass (all 3D, nursery n100); most worlds fall
from 60 to the 30 floor over 30k ticks; 4D's trained brains have fewer births
than scratch (0-10 vs 35). S1b (`probe_births.py`): a steady world needs ~2
children per life, most sources have 0.3-1.2; 3 of 4 4D nurseries stopped
trying to mate; children of distant parents collapse more. Next: S3 (race for
births, 5zorro's cross-entry idea) or S4 (axes x brain size), 5zorro's pick.
**S3 done (2026-11-08):** scoring births in the race restores 4D mating (~1,100
births per play world), but worlds boom to the cap, then starve: the rich food
cores lose their soil (eaten there, pooped everywhere, nothing carries it
back). M3 needs a soil rule first (plan-m3 S3 result, open decision 6).
**S3b done (2026-11-08):** `Config.poop_diffusion` / `soil_diffusion` (off by
default; `scripts/trace_soil.py`). Soil diffusion (0.03 or more) keeps the
cores fertile; poop diffusion doesn't help. The births-race worlds now sit at
the cap (250) instead of crashing. 5zorro: soil diffusion as the default,
hunger may move, every world should pass M3, fix M2's 4D diet goal if the map
caused it. `soil_diffusion` 0.1 is the default since 2026-11-08 (re-baseline
in plan-m3 S3b; every earlier M2/M3 number was measured with soil mining).
**S3c (2026-11-08):** with the 250 cap every world sits on a rail; with it at
2,000, 4D births worlds pass M3 at 0.6x (12/12) and 0.75x (10/12), steady at
~1,500 / ~770 NPCs (stink-held). M3's 30-250 band is below 4D's viable density
(~0.08 NPCs per cell; 250 on 10,000 cells is 0.025). Near the floor, mating
fails on hunger and on density, not age. Smaller 4D maps (size 6-8) bring the
population into the band (84-267 NPCs) but it cycles (cv 0.45-0.95, stink
deaths ~95%), like 2D. **Next:** confirm stink as a delayed regulator (trace),
then a stink-rule test; S3e (small maps raise 4D diet to ~0.9), S3d.
**M3 closed by 5zorro (2026-11-09):** populations hold on births and boom/bust
on stink; "mark it done and move on" (ROADMAP, plan-m3 top). Next is 5zorro's
pick: M4 (trade), S3e (M2's 4D diet 0.9 via map shape), S3d (whole-meal
plants), or game-layer design (performance/LOD notes in `openitems.md`).

0. **State at 2026-11-06 (end):** results of the day are in
   `docs/plan-m2-diet-travel.md` slices R7-R9 and the laws table in
   `docs/research-tuning.md` ("Relationships we measured"). 2D and 3D pass M2
   (two eat actions and the track record are defaults now); 4D fails. Ruled out
   for 4D: senses (a sense-only forager passes), the action draw, brain size
   (4-64 units), crossover top-ups, anneal and ramp nurseries, the craving and
   mating senses. **4D nurseries peak at 50-200k ticks and then decay: mutation
   load under weak selection** (slice R10: not the nursery rules, not luck;
   freezing the hall of fame holds the peak; weights drift at the neutral rate).
   **Births can't carry selection yet:** today's 1x hunger is past 3D's and 4D's
   fertile range, and 4D births are density-limited (slice R11). Also built, off:
   hall-of-fame birth bonus, child credit, trials (`sim/trials.py`), frozen;
   `scripts/probe_decay.py`, `scripts/hunger_ladder.py`. **2026-11-07 (R12):** the
   travel-time worlds are sane (never-moving NPCs starve); at each dimension's
   fertile hunger 2D passes, 3D loses diet and collapses, 4D still fails diet
   and types: hunger isn't 4D's lever, but 4D at 0.36x has births. **R13 (2026-11-07):** trials lose in 4D at
   0.36x (no collapse signal to rank; half the generations); split hunger
   (body burn low, nutrient decay 1x) gives no births. **R14 (2026-11-07):**
   `scripts/arena.py` races the hall of fame on shared scenarios (common random
   numbers, successive halving). To 700k ticks in 4D at 0.36x: no advantage over
   the plain nursery; both level off at ~2.65 food types (types goal met after
   ~200-300k), diet stuck at ~0.80-0.86. Luck: after ~60k ticks the hall of
   fame's brains are near-equal and its own ranking predicts the race at chance;
   race verdicts are washed out within one 20k round (~1% of kept entries
   survive). With the picks made to persist (raced entries, arm `persist`):
   same types ceiling, diet +0.05 (0.85), still short of 0.9; luck isn't the
   cap (rescored 2026-11-08 after the review fixed raced marks leaking into
   seeded worlds: same numbers within 0.01 diet). **R15:** mutation size (inverted U at the default) and brain size
   (8-32, flat) don't move it either; diet ~0.78-0.80 in every cell. 4D's diet
   ceiling isn't a training-method limit. **5zorro moved 4D's diet goal to
   0.8 and closed M2 (2026-11-07);** revisit hints are in R15. Next: M3
   (births, `docs/ROADMAP.md`) or the manager nets (`openitems.md`), 5zorro's pick. Pick of hunger per dimension
   waiting on 5zorro: 2D 1x, 3D 0.9x, 4D 0.36x. Built and off by default: `topup_crossover`,
   `craving_sense`, `mate_sense` (pheromone call), `actions_off`,
   `extra_stay_actions`, `hidden_units=0`; `Simulation.set_rule`. 5zorro's open
   questions: the private `openitems.md` (2026-11-06 list).
   ~38 commits local, unpushed (5zorro pushes). Snapshots kept: only the ones
   that pass M2 under the current rules (2D/3D: `snapshots/ladder3`, `sizes`,
   `outputs`, `ramp-e1.0-f30`). Older folders named below are gone; rebuild
   them with the command next to them. CSVs aren't published: evidence = rerun
   the script.
1. **M2: diet drives travel.** Plan: `docs/plan-m2-diet-travel.md` (the history
   of slices 1–3f with every table lives there). Where it stands (2026-11-04):
   - **2D passes every criterion,** with criterion 3 measured by the move-based
     metric (slice 3c: nursery brains head for their needed food beyond random
     steps and beyond scratch). 5zorro hasn't accepted that revised criterion 3.
   - **Higher dimensions fail on food types per life:** 3D (size 14) 2.3 of 2.5,
     4D far worse. **5zorro (2026-11-04): don't move the goalposts; explain the
     trend first.**
   - **Found cause (slice 3f): crumbs.** Gaussian patches leave crumbs
     everywhere, and the eat instinct picks food by need *per unit*, so it takes
     a crumb of the needed food even beside a full bite of another (84% of crumb
     bites in 2D). In 4D, crumbs dominate (mean bite 7% of a full one, 88% body
     starvation). Brains don't learn to skip crumbs. Carried food is never eaten.
   - **Meal scent** (`Config.scent_min_food`, default off) was tested: no effect
     alone.
   - **Next (5zorro's design, plan slice 3f):** two eat actions, `eat_most` (biggest
     bite) and `eat_need` (today's rule), chosen by the brain; then meal scent
     on top; then the memory stack (slice 4a).
   - **Research slice R (2026-11-04, 5zorro: settle the research before new
     levers):** smell reach is *not* why 4D fails (the smell points the right way
     92-100% of the time in every dimension). Mutations per child: the textbook 1
     per child loses; 10-100 is a plateau; with mutations held equal, 16 hidden
     units are no longer worse than 8. A chosen parent's score is mostly luck
     (R3). **5zorro's lineage-adaptive mutation (R4) is the best 3D result yet:**
     collapses 0.75 vs 1.03, food types 2.36 vs 2.12 (6 of 6 pairs); base 10
     lost. **Now the defaults** (5zorro, 2026-11-04): `mutations_per_birth = 30`,
     `mutation_lineage = true`. Earlier runs and ladder nurseries used the old
     rule: rerun baselines before comparing, and retrain nurseries (`ladder.py`
     refuses stale ones). **Hall-of-fame track record (R5, 5zorro, on by default since 2026-11-06):**
     2D collapses 0.95 -> 0.60 (best yet); 3D same mean, steadier. Proposed as the
     default. 1D/2D regression check: nothing broke. New nurseries live in
     `snapshots/ladder2`. Next idea: gentle-to-harsh nursery ramp (`openitems.md`).
   - **Random-walk luck (R6, 5zorro):** search time per extra dimension grows by
     ~0.7 x width / target size at fixed width; our travel-time worlds keep 3D
     close to 2D. 40,000-tick 3D nurseries = 20,000-tick ones. Not 3D's limit.
   - **5zorro's two eat actions (slice 3g, 2026-11-05, built, off): 3D meets every
     goal** (food types 2.36 -> 2.69; lowest nutrient 0.41, on the line). Body
     starvation nearly gone everywhere; 4D collapses 6.3 -> 2.6 but 4D still
     fails. Brains use a fixed eat_most/eat_need habit per dimension, not
     situational choice. **Both two eat and the track record are on by default
     since 2026-11-06 (5zorro).**
   - **Slice R7 (2026-11-06): width and the anneal nursery.** 3D passes at every
     brain width, even linear (`hidden_units=0`, new); collapses are U-shaped in
     width with the best at 4 in 3D and 4D; 4D fails at every width (not brain
     capacity). 5zorro's anneal nursery (`scripts/anneal.py`) loses to the fixed
     nursery, because hunger settles at 0.2-0.6x play under a 150-NPC line.
     5zorro's ramp (hunger only rises, top-up floor 30/100) doesn't beat the
     fixed nursery either: more ticks at full pressure = better so far. Next
     proposed: crossover top-ups (a top-up is the child of two tournament
     winners), spawn-near-food as a separate switch.
   - **Slice R8 (2026-11-06): the 4D senses are fine.** A sense-only forager
     (`SenseController`, `scripts/probe_senses.py`) meets the diet goals in 2D-4D;
     brains fail to learn the need x gradient product. Proposed lever: a craving
     sense (needed food's scent gradient per axis). Crossover top-ups built
     (`topup_crossover`, off): no consistent effect. Nurseries end with 28-30 of
     30 NPCs being top-ups: selection there is already the hall of fame.
   - **Craving sense (`craving_sense`, built, off):** no fix for 4D at any width,
     even linear. 2D/3D pass everywhere. **R9:** 4D is 10x sparser for mates
     (someone within reach 3% vs 17% in 2D), but most mate attempts come from
     NPCs too young/thin/unwell to mate; births are rare in every dimension.
     **Next:** a hand-built craving-following brain through the normal action
     draw: does a working 4D brain exist? **Answered:** the action draw isn't
     the limit (a forager right 30% of the time passes 4D); the search is.
     **4D nursery length (5zorro):** at 16 units 4D improves steadily from
     20,000 to 120,000 ticks (types 1.96 -> 2.23, still failing); at 4 units it
     plateaus and worsens. **Mating sense with a pheromone call** built
     (`mate_sense`, off); no births in any 4D nursery with it. **Brain size vs
     training length:** ticks to the knee ~ sqrt(weights) in 2D and 3D.
     **4D 700k baseline peaks at 100-200k ticks, then decays** (cause untested).
     Outputs vs training time: no clean law (dummy outputs are cheap). 64 units
     peak at 100k too and never beat 16/32. Open with 5zorro: a second hidden layer; directional
     movement (5zorro plans to test).
   - **4D Miner targets (5zorro, 2026-11-04):** land walkers on 3D surfaces, 4D fish
     and birds in full 4D. Both 3D and 4D must pass.
   - Speed: ticks 27-39% faster (bit-identical); `scripts/fingerprint.py` checks
     refactors. 5zorro's keyed-randomness idea (seed, tick, entity) is an open
     decision (`openitems.md` Speed).
   - Tools: `scripts/ladder.py` (dims × brain size, `--worlds time`, `--set`),
     `scripts/travel_time.py`, `scripts/probe_supply.py`, `scripts/probe_crumbs.py`,
     `scripts/probe_scent.py`, `scripts/fingerprint.py`, `scripts/mutation_success.py`,
     `scripts/probe_random_walk.py`, `scripts/probe_eat_choice.py`, `scripts/compare_runs.py` (nursery-by-nursery
     tables). Nurseries under today's defaults: `snapshots/ladder2` (and
     `ladder2-40k`); `snapshots/ladder` is pre-default-change.
1b. **Next (5zorro, 2026-11-05): make the sim CPU/GPU-agnostic.** Start from
   `openitems.md` Speed (profile, the 4-step path, AMD-on-Windows nuances) and
   keyed randomness (needed for batched worlds). Shape: one array-module seam
   (`xp` = NumPy or a GPU array library) instead of NumPy calls scattered
   through `sim/`; struct-of-arrays NPC state; actions as masks. Guards:
   `scripts/fingerprint.py` must stay identical on the NumPy backend, mass
   checks stay at ~1e-13, `tests/test_safety.py` stays green. Hardware: AMD
   RX 6800 XT (RDNA2, gfx1030), i7-10700K. Environment facts (2026-11-05): WSL
   has `/dev/dxg` (GPU paravirtualization) but no `/dev/kfd`; whether ROCm on
   WSL supports this RDNA2 card is unverified (check AMD's ROCm-on-WSL
   compatibility list before planning on it). Windows-native options don't
   depend on that. Plan: `docs/plan-gpu-backend.md`. **2026-11-05: G0 and G1
   done** (new tick rules + keyed randomness, one re-baseline; the M2 re-check
   gives the same verdicts within seed noise). **G2 done:** array engine
   (`sim/simulation.py` + `sim/population.py`) bit-identical to the per-NPC
   reference (`sim/reference.py`), 2.5-3x faster. **G3 done:** `Batch` runs many
   worlds in one set of arrays; sweeps and the ladder use it. 2D sweeps 2.5x
   faster (goal met); 4D sweeps memory-bound (one map per pass got them 34 -> 24 s).
   **float32 measured** (`Config.precision`, default float64): 4D sweeps 1.5x
   faster, M2 verdicts unchanged in all 6 rows, mass drifts ~2e-4 per 100k
   ticks; a "move what the receiver gained" fix cuts the map leak ~10,000x
   (scratch-tested). **2026-11-06, 5zorro said yes to both:** exact transfers in both
   engines (new fingerprints in the plan), float32 the default for sweeps and
   the ladder (`Config()` stays float64); M2 verdicts unchanged in all 6 rows;
   float32 drift ~5e-5 per 100k ticks, almost all the soil's float32 sum (the
   mod would need integer mass for exactness). Post-change nurseries:
   `snapshots/ladder-exact{,-twoeat}`. **Then (5zorro, 2026-11-06): G4 parked**
   (goal met without it), and his **rounding plug** built: float32 research runs
   post rounding to the median soil cell every 100 ticks and raise on a real
   leak (`Config.mass_plug_every`, `scripts/mass_drift.py`). Pre-compaction review
   (2026-11-06): snapshot NPC records validated at load; stale views check their
   world; known gaps listed in the plan ("Known gaps"). Next real work is back
   on M2 (its open decisions above), not speed. Post-G1 nurseries:
   `snapshots/ladder-g1`, `snapshots/ladder-g1-twoeat` (older folders are pre-G1). Talk to 5zorro before PyTorch
   (D4) or anything C++.
2. Known gaps carried from M1: body starvation is ~35% of collapses; births
   still trail top-ups in 2D (M3's job).
3. Other levers: a harsher scarcity nursery (half food gave a mild win); **seasons** as a config schedule (famine winters, mostly for
   consistency); play-world drift fixes (re-seed, lower mutation in play).
   **Research (2026-11-04):** `docs/research-tuning.md` lists tuning rules
   that map onto our knobs (mutations per genome, the 1/5 success rule, Pólya's
   random walks, smell reach per dimension, the marginal value theorem) and
   similar projects (Polyworld, The Bibites, EvoJAX). Three candidate slices.
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
| Brain size vs dimension (nurseries + play worlds, verdicts per goal) | `scripts/ladder.py` (`--report-only` re-reads the CSV) |
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
- All randomness keyed through `sim/keyed.py`; nothing depends on `sim.npcs` order.
- 5zorro pushes. Agents may commit locally, with no Co-Authored-By or AI attribution
  lines (a local commit-msg hook in `.git/hooks`, not tracked, rejects them for any AI tool).
