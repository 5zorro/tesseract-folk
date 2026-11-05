# Agent conventions

Working rules for anyone changing this repo, human or coding agent.

Read `handoff.md` first instead of searching around, and `gotchas.md` before
measuring anything. Stray ideas go in a private notes file, not into the current
plan. Feature plans live in `docs/plan-*.md` (current:
`docs/plan-m2-diet-travel.md`).

- The maintainer (5zorro) does all git pushes. Agents may commit locally.
- No Co-Authored-By or other AI attribution lines in commits or PRs.

## What this is
A Python prototype of an artificial-life society (tiny neural-net NPCs,
aging, hunger, poop/stink/fertilizer, prayer and stale secrets, conserved
mass). It will later be ported to a C++ mod for the 4D voxel game 4D Miner
(via the community 4DModLoader / 4dm.h framework). Read `docs/DESIGN.md`
for the full design and `docs/ROADMAP.md` for milestones.

## Commands
- Tests: `python -m pytest`
- Headless run: `python scripts/run_headless.py --ticks 3000`
- Until stable + save baseline: `python scripts/run_headless.py --until-stable --max-ticks 20000 --save snapshots/baseline`
  (honestly fails until M3; the default `--max-ticks` of 100,000 takes ~5 minutes to say so)
- Viewer (2D only): `python scripts/view.py`
- Compare configs over seeds: `python scripts/sweep.py --seeds 5 --ticks 10000 --variant metabolism_rate=0.008`
  (uses every CPU core; `--jobs N` to limit). Tuning claims come from here, not single runs.
- Nursery: `python scripts/run_headless.py --set collapse_age_penalty=600 --ticks 20000 --save snapshots/nursery-1`,
  then start fresh worlds from it with `--brains-from snapshots/nursery-1` (or sweep with
  `--variant brains_from=snapshots/nursery-1`). Full chain in `run_headless.py`'s docstring.
- Dimensions ladder: `python scripts/ladder.py --help` (train nurseries and score them in 1D-4D).

## Rules that keep the C++ port easy
1. **Mass conservation is an invariant.** Soil + food + poop + secret caches +
   NPC body/bowel/inventory must stay constant. Any new mechanic that moves
   matter must move it between these pools, never create or delete it. The
   tests check this; keep them passing.
2. **Stay N-dimensional.** Never hard-code 2D. Use `cfg.dims`, `world.neighbor`,
   `world.adjacent`, `wrapped_delta`. New features should be tested at dims=4.
3. **No ML frameworks.** Brains are plain NumPy arrays with a simple forward
   pass and JSON serialization. No PyTorch/TensorFlow.
4. **`sim/` never imports rendering code.** Viewers live in `scripts/`.
5. **Tunables go in `sim/config.py`,** not as magic numbers.
6. **Don't script the emergent behaviors.** Don't add fitness rewards for
   trading, sharing, etc. The point is to see whether they emerge.
7. **Determinism:** all randomness goes through `sim.rng` so snapshots resume
   identically. A speed change must leave `scripts/fingerprint.py`'s hashes unchanged.
8. **Safety:** `sim/` has no outside I/O (no network, processes, pickle, eval);
   `tests/test_safety.py` enforces it. Integrations (e.g. the AI-model pawn) live
   outside `sim/`. Read `docs/SAFETY.md` before adding I/O, an AI-model
   integration, a file format, or a release pipeline.

## Current state
See `handoff.md` (Status) and the current plan.
