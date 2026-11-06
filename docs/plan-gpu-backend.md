# Plan: CPU/GPU-agnostic simulation

Status (2026-11-06): **G0-G3 done; float32 is the research default** (with
exact transfers and the rounding plug; same M2 verdicts). **G4 parked by
5zorro (2026-11-06):** sweeps already meet the 5-minute goal (40 runs x
10,000 ticks: ~75 s in 2D, ~3 min in 4D), and the mod's sim will likely run on
the CPU (the game uses the GPU). Revisit for much bigger experiments; the D4
options (PyOpenCL, PyTorch via DirectML or community ROCm, CuPy no, Taichi
unverified) are under G4 and D4.
Earlier status (2026-11-05): **G0-G3 done.** G1 passes its M2 re-check; G2's array
engine matches the reference bit for bit; G3 batches worlds (also bit for
bit). 2D sweeps are 2.5x faster and meet the 5-minute goal; 4D sweeps aren't
faster yet, because 4D maps now limit them through memory bandwidth (G3
results). G4 (or float32, D2) is what helps there; talk to 5zorro first. 5zorro agreed with the
approach (2026-11-05): D1, D3, D5, D6 as recommended; D2 (precision) reopened. D4 (PyTorch) and anything
about the C++ port get discussed with 5zorro before they're touched; neither is
needed before G4. Stages are ordered;
each ends with tests passing and a commit.

**For a new session:** read `handoff.md`, `gotchas.md` and this file. The
background (profile, nuances, keyed randomness) is in the private notes'
"Speed" section; everything needed to do the work is restated here.

## Goal
Sweeps in about 5 minutes instead of 15-45, by running one simulation's rules
as array operations over (world, NPC), on NumPy today and on a GPU array
library when that pays. "Agnostic" means `sim/` is written once against an
array module `xp`; the backend is picked outside `sim/`.

**Done when:**
1. A typical sweep (e.g. 8 variants x 5 seeds x 10,000 ticks, 2D) finishes in
   about 5 minutes, on whichever backend is fastest.
2. On NumPy, `scripts/fingerprint.py` hashes are unchanged by every stage after
   G1 (G1 is the one planned re-baseline, D1).
3. Mass checks stay at about 1e-13 on every backend; `tests/test_safety.py`
   stays green.
4. The M2 results still hold after G1 (2D passes; 3D passes with two eat
   actions), within seed noise. If one doesn't, explain why before going on.

## What we know (measured 2026-11-05, Windows `.venv`, NumPy 2.5.4)
- **Baseline fingerprints** (`scripts/fingerprint.py`, 600 ticks):
  2D `e2adb8c9c846f398` (3.0 s), 3D `be62f8c17c0b502c` (2.8 s),
  4D `17feee744fb26640` (3.4 s).
- **Where a tick goes** (cProfile, 600 ticks, about 30-50 NPCs):
  `sense` 38% (2D) / 33% (4D), `_decide` 21% / 15%, `_metabolize` 12% / 9%,
  `_record_approach` (M2 metric) 12% / 13%, `world.step` 22% in 4D (its
  `np.roll`s), the brain math itself 5%. About 115 microseconds per NPC per
  tick, almost all Python overhead on tiny arrays.
- **The worlds are tiny:** 1,024 cells in 2D, 10,000 in 4D, 30-250 NPCs. One
  world can't fill a GPU; a GPU only pays once many worlds run in one array
  (a sweep's variants x seeds). One world vectorized on NumPy should already
  be much faster than today, because the cost is per-call overhead, not math.
- **The tick is sequential today.** NPCs act one at a time in a random order,
  and each one senses the world as the earlier ones left it (food eaten,
  NPCs moved). Arrays can't do that. Any batching changes results, so a
  bit-identical refactor is impossible here; that's why G1 re-baselines once.
- **Randomness:** about 25 call sites draw from one shared `sim.rng` stream, in NPC
  order. Batching needs per-NPC randomness (keyed randomness).
- **GPU options for this machine** (RX 6800 XT = RDNA2, gfx1030; driver
  32.0.21045; `OpenCL.dll` and `vulkan-1.dll` present):
  - *ROCm (AMD's CUDA):* AMD's current lists don't include consumer RDNA2,
    on Windows or Linux; WSL has `/dev/dxg` but no `/dev/kfd`. Community
    builds run RDNA2 on Windows (an RX 6750 XT verified, the 6800 XT
    "pending"). So CuPy (needs ROCm) and PyTorch-on-ROCm are unofficial here.
  - *OpenCL (PyOpenCL):* the AMD driver ships it on Windows, a Python 3.13
    wheel exists, and it supports this card officially. Its array module is
    thin, so gathers and scatters need small hand-written kernels. float64
    support must be checked on the device (`cl_khr_fp64`).
  - *Vulkan (Taichi, wgpu):* runs on AMD; Taichi's Python 3.13 support and
    upkeep are unverified; WebGPU has no float64.
  - So **Windows-native is the likely route** (not WSL), and the choice is
    made in G4 from a measured probe, not now.
- **Windows vs WSL:** G1-G3 are NumPy on the CPU and run from the Windows
  `.venv` as today. G4's probe uses a separate `.venv-gpu/` (gitignored by
  `.venv-*/`). WSL only matters if a ROCm route is chosen.

## The new tick rules (G1, D1)
Simple enough to state in the C++ port's comments, and they give arrays
nothing order-dependent to fight:
1. **Sense and decide together.** Every NPC senses the world as it was at the
   start of the tick (neighbor counts already work this way) and picks one
   action (brain, or its controller in `sim.overrides`).
2. **Resolve in fixed phases**, in this order: moves (with secret claims and
   the approach metric) -> eats and pick-ups -> give, mate, share -> poop,
   pray, worship -> metabolism -> deaths and births.
3. **Conflicts go by priority.** Each NPC gets a priority each tick from keyed
   randomness. Where NPCs compete (several eaters on one cell, two NPCs
   picking the same partner), the higher priority goes first. Eaters on one
   cell are resolved in "rounds" (the first eater of every cell, then the
   second...), so arrays reproduce the one-at-a-time result exactly.
4. **Keyed randomness.** Every draw comes from a hash of
   (seed, tick, NPC id, purpose), computed with integer operations that give
   the same bits on any backend. World creation keeps `default_rng(seed)`,
   so maps stay identical to today's and the comparison isolates behavior.

### The seam for 5zorro's reaction-time queue
5zorro's idea (private notes, "Reaction time and an action queue"): neurons
fire now, the action takes effect a few ticks later, and a stack of queued
decisions keeps an NPC acting while it lags; an AI-model pawn could fill the
queue a few actions ahead, or inject inputs instead. Rule 1 above is that
queue with a delay of zero: decisions are made from one tick's state and
resolved afterwards. So G1 splits the code into "decide" (writes each NPC's
chosen action) and "resolve" (reads it), and G2 keeps the chosen action as a
per-NPC array. A queue then means resolve reads an action decided k ticks ago
(a small ring buffer per NPC) instead of this tick's; nothing else changes.
Not built here; it gets its own plan, since it changes behavior (re-measure).

## Stages
- **G0. Freeze the old numbers. Done 2026-11-05, no new runs needed:** the
  slice 3g ladder runs used today's rules (the only later `sim/` change,
  fc498fe, adds input checks). Baseline = `runs/2026-11-05-twoeat.csv` (two
  eat) and `runs/2026-11-04-defaults-{2d,3d}.csv` + `runs/2026-11-05-defaults-4d.csv`
  (one eat): 6 nurseries (seeds 100-105) x 5 seeds, 8 hidden, `--worlds time`.
  Means over nurseries (plan-m2 slice 3g):
  | | Collapses | Scratch | Food types / life | Diet | Lowest nutrient | Births | Goals |
  |---|---|---|---|---|---|---|---|
  | 2D one eat | 0.95 | 1.77 | 2.83 | 0.97 | 0.47 | 45 | all |
  | 2D two eat | 1.02 | 1.44 | 2.94 | 0.92 | 0.45 | 185 | all |
  | 3D one eat | 0.75 | 2.39 | 2.36 | 0.97 | 0.47 | 32 | not food types |
  | 3D two eat | 0.82 | 1.43 | 2.69 | 0.92 | 0.41 | 76 | all |
  | 4D one eat | 6.32 | 8.98 | 0.69 | 0.88 | 0.34 | 0 | fails 3 |
  | 4D two eat | 2.63 | 3.99 | 1.72 | 0.82 | 0.31 | 2 | fails 3 |
  Re-run after G1 with the same command into new folders:
  `python scripts/ladder.py --worlds time --hidden 8 --nursery-seeds 100 101 102 103 104 105
  [--set two_eat_actions=true] --out snapshots/ladder-g1[-twoeat] --csv runs/2026-11-05-g1[-twoeat].csv`,
  then `scripts/compare_runs.py` per dims.
- **G1. New tick rules + keyed randomness, still per-NPC Python code. Built
  2026-11-05 (54c162c); passes the M2 re-check (below).** New fingerprints:
  2D `2ab287e453c4e17f` (2.6 s), 3D `ce0acf01d4e46e2f` (2.5 s), 4D
  `c5f8ec78c59fc41b` (3.1 s), old ones under "What we know". Also done:
  choices among neighbors (gift takers, mates) and top-up candidates are
  sorted by id, so results don't depend on `sim.npcs` order (tested by
  reversing it every tick); the fingerprint hashes the tick instead of the old
  rng state; `scripts/ladder.py` refuses pre-G1 nursery folders. Re-check runs:
  `runs/2026-11-05-g1-twoeat.csv` and `runs/2026-11-05-g1.csv` (nurseries in
  `snapshots/ladder-g1-twoeat`, `snapshots/ladder-g1`). The
  one planned re-baseline: record old and new hashes here. Write
  `sim/keyed.py` (hash -> uniforms, normals) and route all 25 draws through
  it. Snapshots: brains load as before (nursery seeding works); resuming a
  pre-G1 full snapshot is refused with a clear message (D5). Validate against
  G0 over seeds, not single runs. This scalar code stays as the reference
  engine (D3).
- **G2. One world as arrays, on NumPy.** NPC state moves into a population of
  arrays (fixed capacity with an alive mask; brains stacked as (N, hidden,
  inputs)). Senses become gathers, the brain one batched matmul, sampling
  one vectorized draw, actions masks. Rare actions (give, mate, share, pray)
  may stay a small loop over the NPCs that chose them. `sim.npcs` remains as
  a view for scripts, controllers and snapshots. Guard: fingerprints identical
  to G1, and a test that steps both engines on small worlds and compares
  every field. If batched matmul changes the last bit (BLAS summation order),
  compare within 1e-12 instead and say so here. Then measure.
- **G2 done (2026-11-05).** What was built:
  - `sim/population.py`: every NPC field as a column (fixed capacity, grows if
    needed; `alive` marks used slots; brains stacked as `w1` (N, hidden,
    inputs) etc.). `NPCView` gives one slot NPC's attribute names, so
    scripts, controllers, snapshots and most tests didn't change. A view
    checks its NPC's id on every use and raises once the slot is reused.
  - `sim/simulation.py` is the array engine; `sim/reference.py` is G1's
    per-NPC engine, unchanged apart from the name (D3).
    `tests/test_engines.py` runs both on 8 busy configs (1D-4D, two eat, track
    record, smiting, harsh, controllers) for 300 ticks and compares every NPC
    field, the world, deity, hall of fame and stats exactly; it catches an
    injected change in eating order or healing within 50 ticks.
  - Exactness tricks: shared-cell additions go through `np.add.at` in priority
    order; eaters on one cell take turns in rounds; batched `np.matmul` on
    stacked brains equals the per-NPC `@` on this machine (checked; batched
    `einsum` doesn't); every reduction keeps the reference's order.
  - Before G2, two rule details changed in both engines, hash-neutral under
    the defaults: deaths and collapses happen after everyone's metabolism,
    and the fingerprint sorts NPCs by id.
  - Probes that hook per-NPC methods (`probe_crumbs`, `probe_eat_choice`,
    `probe_nutrients`, `probe_supply`) now run on the reference engine.
  - **Speed** (fingerprint runs, 600 ticks, same hashes): 2D 2.4 -> 0.8 s,
    3D 2.4 -> 0.8 s, 4D 3.0 -> 1.2 s; tests 31 -> 21 s. What's left per tick
    is NumPy call overhead (about 100 small calls), and in 4D `world.step`'s
    `np.roll`s (40%). A bit-identical slicing version of the neighbor mean is
    only 25% faster, so it waits for G3, where one call covers every world.
- **G3. Many worlds in one array.** A leading world axis on every array;
  numeric tunables become per-world arrays, structural ones (dims, size,
  food types, brain size) must match within a batch. `sweep.py` groups runs
  by structure and runs one batch per process. Measure; if sweeps already hit
  about 5 minutes, G4 becomes optional (decide then).
- **G3 done (2026-11-05).** What was built:
  - `sim/simulation.py`: `Simulation` is now one world's facade, and `Batch`
    steps many worlds in one set of arrays: maps stacked on a world axis (each
    `World` keeps views of its row), one Population with a `world` column,
    numeric settings as per-world arrays (`Batch.par`), keyed draws with
    per-world seeds. `Simulation(cfg)` alone is a batch of one, so nothing
    outside changed. Worlds in a batch must share `STRUCTURAL` settings and the
    tick; stepping one steps all.
  - `tests/test_engines.py`: mixed batches (5 worlds: seeds, rates, smiting,
    track record, a controller in one world; 2D, 4D, two eat without scent)
    equal their worlds run alone, exactly, over 300 ticks.
  - `scripts/sweep.py`: `Run` measures one world while it steps; `run_batch`
    runs jobs as one batch; `run_jobs` groups jobs that can share a batch
    and makes about one batch per process. Results equal the old one-by-one
    runner exactly (checked on 5 jobs, 1 and 3 processes). `ladder.py` trains
    nurseries and plays worlds in batches the same way.
  - The world step goes about one 4D map (10,000 cells) at a time
    (`WORLD_STEP_CELLS`), and the neighbor mean adds in place; both
    bit-identical. Without the grouping, 32 stacked 4D maps fell out of cache
    and a batched 4D world cost 3.5 ms per tick, more than alone (2.1 ms).
  - **Measured** (one process, ms per world per tick): 2D 1.4 alone, 0.58 in
    8, 0.49 in 32; 4D 2.1 alone, 1.47 in 8, 1.37 in 32. Before G1: 2D ~4, 4D ~5.
  - **Sweeps** (40 runs = 8 variants x 5 seeds, 16 processes, wall time):
    2D x 3,000 ticks: 55 s before G1 -> 22 s now (so ~75 s for 10,000 ticks:
    the goal is met in 2D). Fewer, bigger batches didn't help (8 processes
    23 s, 4 processes 25 s). 4D x 1,000 ticks: 36 s -> 34 s, barely faster.
    **Then one 4D map per world-step pass instead of four** (the shared L3
    cache is ~1 MB per process under full load): 4D 34 s -> 24 s, 2D unchanged,
    bit-identical. The loaded 4D world step per world: 3.05 -> 1.39 ms.
  - **Why 4D didn't speed up:** in 4D the world step (stink and scent
    spreading over 10,000 cells x 4 fields) is 59% of a tick even alone, and
    it's memory-bound: 16 processes streaming 4D maps share one memory bus and
    L3 cache, so per-process gains vanish under full load. The relationship:
    per-world tick cost ~ a + b x cells, where `a` (Python per NPC and per
    call) is what G1-G3 cut and `b` (memory traffic per cell) is now what's
    left. `b` is what a GPU (hundreds of GB/s) or float32 (half the bytes) cuts.
- **G4. GPU backend.** First a probe in `.venv-gpu/`: run G3's batched tick
  on each candidate (PyOpenCL first, community ROCm PyTorch only if D4 allows)
  and time it against NumPy on the same sweep. Then the `xp` seam: `sim/`
  takes the array module as an argument, and the few operations array
  libraries disagree on (scatter-add, segment sums, sort-by-key) live in one
  small `sim/ops.py`. The backend is imported and chosen in `scripts/`, never
  in `sim/` (their drivers and kernel caches write to disk; D6).

### G1's M2 re-check (2026-11-05): same verdicts, within seed noise
Same command as G0, nurseries retrained under the new rules (so pairs by
nursery seed are different brains; compare means). `scripts/compare_runs.py`,
means over 6 nurseries x 5 seeds, +- standard error:
| | Collapses before -> after | Food types / life | Lowest nutrient | Births | Goals |
|---|---|---|---|---|---|
| 2D one eat | 0.95 ± 0.06 -> 0.74 ± 0.10 | 2.83 -> 2.87 | 0.47 -> 0.51 | 45 -> 90 | all -> all |
| 2D two eat | 1.02 ± 0.07 -> 1.06 ± 0.05 | 2.94 -> 2.88 | 0.45 -> 0.45 | 185 -> 121 | all -> all |
| 3D one eat | 0.75 ± 0.10 -> 0.85 ± 0.11 | 2.36 -> 2.32 | 0.47 -> 0.45 | 32 -> 9 | not food types (both) |
| 3D two eat | 0.82 ± 0.11 -> 0.76 ± 0.07 | 2.69 -> 2.68 | 0.41 -> 0.42 | 76 -> 112 | all -> all |
| 4D one eat | 6.32 ± 0.40 -> 6.86 ± 0.37 | 0.69 -> 0.67 | 0.34 -> 0.35 | 0 -> 0 | fails 3 (both) |
| 4D two eat | 2.63 ± 0.08 -> 2.53 ± 0.17 | 1.72 -> 1.81 | 0.31 -> 0.31 | 2 -> 2 | fails 3 (both) |
- **Every goal verdict is unchanged**, and the gaps are within about 2
  standard errors with no consistent direction (collapses go down in 3 rows,
  up in 3). So one-at-a-time order wasn't driving M2's results.
- **Births swing most** (2D one eat 45 -> 90, 2D two eat 185 -> 121, 3D one eat
  32 -> 9), up in some rows and down in others. Births are few and lumpy per
  run, so this reads as noise, but they're the number to watch if a later
  stage seems to change behavior.
- Files: `runs/2026-11-05-g1{,-twoeat}.csv`, logs `runs/g1{,-twoeat}.log`.

## Known gaps (review, 2026-11-06)
Fixed in the review: crafted snapshot NPCs (out-of-world positions, zone or
patch indices out of range, unknown damage causes or origins, wrong vector
lengths) now fail clearly at load (`Population.check_record`); before, some
failed mid-run and a negative index would have wrapped silently. A stale NPC
view now also checks its world (ids repeat across a batch's worlds). The
list-order test runs on the reference engine (on the array engine `npcs` is
rebuilt by id, so reversing it tested nothing; `test_engines.py` reshuffles
slots instead). Left as is:
- **Rules live twice** (reference.py and simulation.py, plus `World.step` vs
  `Batch._world_step_part`). `tests/test_engines.py` catches any drift, but a
  rule change costs two edits.
- **`sim/simulation.py` is ~1,150 lines** (Simulation and Batch); splitting
  Batch into `sim/batch.py` would read better. No behavior change needed.
- **Social actions rebuild a cell index of every living NPC** each tick
  anyone gives, mates or shares: O(NPCs) Python per tick in big batches.
  Fine at today's sizes; first thing to vectorize if 2D batches grow.
- **The plug raises mid-sweep** on a real leak, which ends the whole sweep
  (ProcessPool). Deliberate (loud beats wrong), but a long run is lost.
- **Probe scripts on the reference engine** are ~3x slower than they'd be on
  the array engine; they're rarely run.
- **Per-NPC record checks** run on every add (births, top-ups, batch merges):
  a little Python per birth; not measurable in the fingerprint runs.

## Guards and risks
- **Backends won't agree bit for bit.** Summation order and math libraries
  differ, and the sim amplifies a last-bit difference into a different run
  within a few hundred ticks. So: on NumPy, fingerprints must match exactly;
  NumPy vs GPU must match within about 1e-12 for the first few ticks and
  agree statistically over a sweep. A GPU run must repeat itself exactly:
  no floating-point atomics, use sorted segment sums.
- **Precision (D2, reopened):** float64 until G2's bit-for-bit check is done,
  then float32 measured, not assumed.
- **Rule 7** gets one line: "except a re-baseline approved by 5zorro and
  recorded in the plan with old and new hashes."
- **Controllers** (the AI-model pawn, scripted controllers in sweeps) still
  decide per NPC; their NPCs are pulled out of the batch, decided on the host,
  and put back. Fine for a few NPCs.
- **M2 metrics** (`_record_approach`, zone switches) are 12-13% of a tick and
  must be vectorized too, or they become the bottleneck.

## float32 measured (D2, 2026-11-05/06)
`Config.precision` ("float64" default, "float32"): the array engine's float
arrays, settings and brains at that width (reference engine: float64 only).
A batch can't mix them (`STRUCTURAL`). Tests: `tests/test_precision.py`.
- **Speed** (40-run sweeps, 16 processes): 2D x 3,000 ticks 20 s either way
  (2D is limited by Python, not memory); 4D x 1,000 ticks 27 s -> 18 s
  (1.5x). The loaded 4D world step alone: 1.39 -> 0.62 ms per world (2.2x).
- **Mass drift** (one world, relative to the total; float64 is ~3e-13 at
  100,000 ticks):
  | float32 | 1,000 | 10,000 | 30,000 | 100,000 ticks |
  |---|---|---|---|---|
  | 2D | -9e-8 | -3.4e-5 | -1.0e-4 | -2.4e-4 |
  | 4D | +1e-6 | -1.9e-5 | -5.9e-5 | -1.4e-4 |
  Always a loss, growing about linearly (`runs/f32-drift.log`).
- **Why:** the loss is biggest with no NPCs at all (2D -3e-4 in 20,000
  ticks), so it's the world step: a tiny growth step added to a food cell
  near 1-2 rounds away, while the same amount leaves near-empty soil
  exactly. The pattern: float32 loses mass wherever a small amount moves into a
  much larger pool.
- **Fix, measured** (patched in a scratch script, not in `sim/` yet): move what
  the receiving pool actually gained (`food += g; soil -= (food - before)`;
  the same for poop -> soil). No NPCs: drift -3e-4 -> -4e-8 (2D), -6e-5 ->
  +4e-7 (4D), signs now random. With NPCs: 2D -7e-5 -> +5e-6, 4D -4e-5 ->
  +1e-5 over 20,000 ticks; the rest comes from NPC transfers (eating,
  metabolism), which the same rule would fix. In float64 this changes last
  bits, so applying it everywhere is a re-baseline (5zorro's call); it's also
  how the C++ mod should move mass in float32.
- **M2 verdicts in float32: unchanged in all 6 rows.** Same ladder command as
  G1's re-check plus `precision=float32` (`runs/2026-11-06-f32{,-twoeat}.csv`,
  nurseries `snapshots/ladder-f32{,-twoeat}`); today's float32, without the
  transfer fix. Means over 6 nurseries x 5 seeds, float64 (G1) -> float32:
  | | Collapses | Food types / life | Lowest nutrient | Births | Goals |
  |---|---|---|---|---|---|
  | 2D one eat | 0.74 ± 0.10 -> 0.86 ± 0.04 | 2.87 -> 2.83 | 0.51 -> 0.49 | 90 -> 63 | all, both |
  | 2D two eat | 1.06 ± 0.05 -> 1.14 ± 0.08 | 2.88 -> 2.90 | 0.45 -> 0.45 | 121 -> 200 | all, both |
  | 3D one eat | 0.85 ± 0.11 -> 1.00 ± 0.10 | 2.32 -> 2.18 | 0.45 -> 0.44 | 9 -> 9 | not food types, both |
  | 3D two eat | 0.76 ± 0.07 -> 0.84 ± 0.08 | 2.68 -> 2.61 | 0.42 -> 0.42 | 112 -> 58 | all, both |
  | 4D one eat | 6.86 ± 0.37 -> 6.45 ± 0.30 | 0.67 -> 0.68 | 0.35 -> 0.34 | 0 -> 0 | fails 3, both |
  | 4D two eat | 2.53 ± 0.17 -> 2.49 ± 0.16 | 1.81 -> 1.83 | 0.31 -> 0.31 | 2 -> 2 | fails 3, both |
  Every gap is within about 1.5 standard errors. Collapses are higher in 4 of
  6 rows (2D and 3D) and lower in both 4D rows; 4 of 6 is what chance gives
  (p ~ 0.7), so no direction is shown. Births swing as in G1's re-check
  (noise). Each float32 ladder took a few minutes (the float64 ones before G2:
  ~11 min each).
- **So for research runs, float32 looks safe for behavior**, and the remaining
  question is mass bookkeeping (the transfer fix) and whether to make it the
  default (5zorro).

### Applied 2026-11-06 (5zorro: "Yes, both")
- **Exact transfers, both engines, both precisions:** food growth out of the
  soil, poop -> soil, digestion (body -> bowel), new secrets and top-up NPCs
  out of the soil (`World.take_from_soil` now returns what it removed; the
  newcomer's body is that). The second planned re-baseline. Fingerprints,
  float64: 2D `2ab287e453c4e17f` -> `277074ed77bc4e97`, 3D `ce0acf01d4e46e2f`
  -> `2b31b06269db5ebd`, 4D `c5f8ec78c59fc41b` -> `996422ed88b12562`; float32
  (new line in `scripts/fingerprint.py`): 2D `f50dff43ea5efde0`, 3D
  `cd20cfb81a81bca9`, 4D `17e8299a93b51ef8`.
- **Later re-baseline (2026-11-06, not an engine change):** two eat actions and
  the hall-of-fame track record became defaults. Fingerprints, float64: 2D
  `3426bd65dc54b903`, 3D `dcde46a3c61d5393`, 4D `1447aa17ab5ffa6c`; float32: 2D
  `c25bebb90a9a550a`, 3D `c5977561ea6614b6`, 4D `82286d860933f3b2`.
- **float32 is the research default** (`RESEARCH_DEFAULTS` in `scripts/sweep.py`,
  used by `ladder.py`); `Config()` stays float64 (tests, reference engine,
  snapshots; `LEGACY` loads old snapshots as float64).
- **Drift after the fix**, 100,000 ticks (before -> after):
  | | float64 | float32 |
  |---|---|---|
  | 2D | 2.3e-13 -> 3.7e-15 | -2.4e-4 -> +4.5e-5 |
  | 4D | 3.3e-13 -> 5.5e-14 | -1.4e-4 -> +7.2e-5 |
  float32 improves 2-5x over a long run, not 10,000x: the fix removed the
  rounding-away at the receiver, and what's left grows, so a per-phase ledger
  was run (float32, 2D, 20,000 ticks, float64 sums around each phase): the
  world step's growth transfer makes +5.2e-6 of the +5.3e-6 total;
  decomposition -9e-9, eating +1e-7, metabolism and the rest below 1e-8. So
  it's the soil's subtraction of three food types' gains, summed and
  subtracted in float32; no cell goes negative. Fixing NPC transfers wouldn't
  help. **For the C++ mod:** exact conservation at any width means integer
  mass units (fixed point), not float bookkeeping; float32 with exact
  transfers drifts ~5e-5 per 100,000 ticks.
- **M2 re-check (float32 + exact transfers): same verdicts in all 6 rows.**
  `runs/2026-11-06-exact{,-twoeat}.csv`, nurseries `snapshots/ladder-exact{,-twoeat}`.
  Collapses, float64 (G1) / float32 / float32 + exact: 2D one eat 0.74 /
  0.86 / 0.85, two eat 1.06 / 1.14 / 0.92; 3D one eat 0.85 / 1.00 / 0.88,
  two eat 0.76 / 0.84 / 0.77; 4D one eat 6.86 / 6.45 / 6.87, two eat 2.53 /
  2.49 / 2.41. Food types per life within 0.1 everywhere (3D one eat 2.32 /
  2.18 / 2.24, still short of 2.5). Births swing as before.

### The rounding plug (5zorro, 2026-11-06): built
`Config.mass_plug_every` (0 = off, the default; sweeps and the ladder use 100
via `RESEARCH_DEFAULTS`) and `mass_plug_max` (1e-5). Each world keeps its true
total in `Batch.mass_target` (float64); every N ticks `Simulation.plug_mass`
posts the difference to the median soil cell, counts it in
`stats.mass_plugged`/`mass_plugs` (and the sweep CSV's `mass_plugged`), and
raises above `mass_plug_max`. Mass changed from outside a tick (`sim.npcs = ...`,
a snapshot load, a spawn by hand) restarts the ledger; top-ups inside a tick
don't (a bug that let drift through, caught by measuring, now tested).
Measured (`scripts/mass_drift.py`, float32, plug every 100): drift at plug
ticks ~1e-12 after 3,000 ticks, vs ~1e-6 without; plugged -3.7e-7 (2D) and
-1.0e-6 (4D) of the total. The array engine only (the reference engine is
float64 and needs none). Not re-checked on the M2 ladder: it moves ~1e-9 of
the mass per post.

Original note:
Like an accountant's suspense entry: keep the true total mass in float64; every
N ticks compare the arrays' total with it and post the difference (rounding,
~1e-8 of the total) to one soil cell (5zorro: the median cell, so it never
lands on empty dirt) or spread it in proportion to the soil (what climate
models' "mass fixers" do). Count the plug in stats, and treat a difference
above a materiality threshold (e.g. 1e-5 of the total) as an error, not a
plug, so a real conservation bug can't hide in it. Works the same in the C++ mod.

## Decisions (5zorro)
Settled 2026-11-05 ("I fully agree with the approach"): D1, D3, D5, D6 as
recommended. Open: D2 (reopened), D4, and anything touching the C++ port
(talk first).

- **D1. New tick rules (above) with one re-baseline?** Recommended: yes.
  Every batching path needs it; the rules are simpler to port, and the old
  results get re-checked in G1. The alternative (two engines, old one kept
  bit-for-bit) doesn't exist: one-at-a-time order can't be batched.
- **D2. Precision. Reopened by 5zorro (2026-11-05):** "our hardware is good
  enough" isn't a reason to spend 16x. Revised proposal (his call): float64
  stays only as the reference while porting (G2's bit-for-bit check needs one
  precision on both sides); `sim/` gets a dtype switch next to `xp`; G3/G4
  measure float32 (speed, mass drift per 100,000 ticks, the M2 verdicts) and
  float32 becomes the default if they hold. The mod uses float32 regardless
  (game convention, half the memory, 2x SIMD lanes on the CPU), and exact
  mass conservation there may be better done with integer mass units than
  with float width.
- **D3. Keep G1's per-NPC engine as the reference** (test oracle on small
  worlds, and the readable spec for the C++ port)? Recommended: yes. Cost:
  each rule change is made twice, and a test catches when they disagree.
- **D4. Rule 3 ("no ML frameworks") for the backend.** Rule 3 is about brains
  staying plain arrays for the port. Using PyTorch only as an array library in
  research scripts would keep that true, but it's your rule. Recommended:
  allow it as a G4 candidate only, never imported by `sim/`.
- **D5. Old snapshots after G1:** brains-only seeding keeps working; full
  resume of a pre-G1 snapshot is refused. Recommended: yes.
- **D6. Safety (SAFETY.md):** `sim/` keeps no outside I/O by taking `xp` as an
  argument; GPU libraries are imported only in `scripts/`. Recommended: yes,
  plus a SAFETY.md note.
- **Order vs M2's open defaults** (two eat actions, track record): G1 re-runs
  the M2 checks anyway, so those can be decided from post-G1 numbers.

Sources for the GPU facts: AMD's ROCm system requirements
(rocm.docs.amd.com, Linux and Windows HIP SDK pages), ROCm/TheRock issue 7480
(RDNA2 on Windows), PyPI's pyopencl page (cp313 Windows wheel). Re-check
before G4; this changes fast.
