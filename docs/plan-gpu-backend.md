# Plan: CPU/GPU-agnostic simulation

Status (2026-11-05): **G0 done, G1 in progress.** 5zorro agreed with the
approach (2026-11-05): D1-D3, D5, D6 as recommended. D4 (PyTorch) and anything
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
  2026-11-05 (54c162c); the M2 re-check is running.** New fingerprints:
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
- **G3. Many worlds in one array.** A leading world axis on every array;
  numeric tunables become per-world arrays, structural ones (dims, size,
  food types, brain size) must match within a batch. `sweep.py` groups runs
  by structure and runs one batch per process. Measure; if sweeps already hit
  about 5 minutes, G4 becomes optional (decide then).
- **G4. GPU backend.** First a probe in `.venv-gpu/`: run G3's batched tick
  on each candidate (PyOpenCL first, community ROCm PyTorch only if D4 allows)
  and time it against NumPy on the same sweep. Then the `xp` seam: `sim/`
  takes the array module as an argument, and the few operations array
  libraries disagree on (scatter-add, segment sums, sort-by-key) live in one
  small `sim/ops.py`. The backend is imported and chosen in `scripts/`, never
  in `sim/` (their drivers and kernel caches write to disk; D6).

## Guards and risks
- **Backends won't agree bit for bit.** Summation order and math libraries
  differ, and the sim amplifies a last-bit difference into a different run
  within a few hundred ticks. So: on NumPy, fingerprints must match exactly;
  NumPy vs GPU must match within about 1e-12 for the first few ticks and
  agree statistically over a sweep. A GPU run must repeat itself exactly:
  no floating-point atomics, use sorted segment sums.
- **float64 stays.** This card does float64 at 1/16 the float32 rate, but our
  work is limited by memory and launches, not arithmetic (D2).
- **Rule 7** gets one line: "except a re-baseline approved by 5zorro and
  recorded in the plan with old and new hashes."
- **Controllers** (the AI-model pawn, scripted controllers in sweeps) still
  decide per NPC; their NPCs are pulled out of the batch, decided on the host,
  and put back. Fine for a few NPCs.
- **M2 metrics** (`_record_approach`, zone switches) are 12-13% of a tick and
  must be vectorized too, or they become the bottleneck.

## Decisions (5zorro)
Settled 2026-11-05 ("I fully agree with the approach"): D1, D2, D3, D5, D6 as
recommended. Open: D4, and anything touching the C++ port (talk first).

- **D1. New tick rules (above) with one re-baseline?** Recommended: yes.
  Every batching path needs it; the rules are simpler to port, and the old
  results get re-checked in G1. The alternative (two engines, old one kept
  bit-for-bit) doesn't exist: one-at-a-time order can't be batched.
- **D2. Keep float64 everywhere?** Recommended: yes (see risks).
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
