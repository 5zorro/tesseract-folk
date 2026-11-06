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
- `--until-stable` honestly fails (top-ups, population on the floor) and prints
  why. Expect that until M3.
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
     refuses stale ones). **Hall-of-fame track record (R5, 5zorro, off by default):**
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
     situational choice. Pending 5zorro: two eat and track record as defaults.
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
   faster (goal met); 4D sweeps are memory-bound now and barely faster. Next:
   discuss G4 / float32 (D2, D4) with 5zorro before building. Post-G1 nurseries:
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
