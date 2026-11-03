# Plan: M1 Survival

Status: **slice 1 done (2026-11-02). Next: slice 2.** Slices are ordered; each
one ends with tests passing and a commit. Open decisions (bottom) are 5zorro's.

**For a new session:** read `handoff.md`, `gotchas.md` and this file. Do the
slices in order. Don't tune numbers (slice 4) before slices 1 to 3 exist: without
them you can't tell whether a change helped.

## Goal (from ROADMAP.md)
**Pass:** collapses per NPC fall over generations, and NPCs keep nutrients up
without help.

To make that testable, M1 passes when, **over 5 seeds × 10,000 ticks** (2D, default size):
1. Collapse rate (collapses per NPC per 1,000 ticks of lifetime) is lower for late
   generations than for generation 0–1, beyond seed-to-seed noise.
2. Mean of each NPC's lowest nutrient stays above `starving_threshold` in the last
   quarter of the run.
3. Starvation is no longer the top collapse cause (slice 1 measures this).
4. The same holds at `--dims 4 --size 10` (a shorter run is fine).

Births and a top-up-free population are M3's job, not M1's. Don't chase them here.

## What we know already (probe on 2026-11-02, single seed, 3,000 ticks)
| Run | Collapses, first 1k ticks | Collapses, last 1k ticks | Births |
|---|---|---|---|
| Baseline | 589 | 227 | 2 |
| `smite_damage=0` | 357 | 179 | 1 |
| ScriptedController (start NPCs only, see gotchas) | 505 | 396 | 0 |
| Scripted + `smite_damage=0` | 386 | 181 | 0 |

Reading: smiting causes ~40% of early collapses, and a sensible hand-coded forager
still collapses a lot. So the economy is harsh before brains even matter. The
probe script was a throwaway; slice 2 makes a real one.

## Slices

### Slice 1: Collapse-cause instrumentation ✅ (2026-11-02)
**Built:**
- `NPC.take_damage(cause, amount)` records damage by cause in `npc.damage`, which
  holds the damage since the NPC was last at full health (cleared on full heal
  and on collapse). Causes: `sim/npc.py: DAMAGE_CAUSES`.
- A collapse or death is blamed on `npc.main_damage_cause()`, the cause with
  the most damage in that record. Counters: `collapse_<cause>` and
  `death_<cause>` in `sim/stats.py`.
- `Stats.generation_lifetime` / `generation_collapses` and
  `collapse_rate_by_generation()`: cumulative for the whole run, not saved in snapshots.
- `run_headless.py` prints a cause breakdown and per-generation collapse rates
  after the table.
- Tests: `tests/test_causes.py` (sums per window in 2D and 4D, each cause is
  blamed correctly, the reset at full heal, generation totals).

**First readout** (default config, 3,000 ticks, seeds 0/1/2):
| | Seed 0 | Seed 1 | Seed 2 | 4D, 500 ticks |
|---|---|---|---|---|
| Collapses blamed on smite | 83% | 80% | 84% | 95% |
| … on starvation (nutrients + body) | 17% | 19% | 15% | 4% |
| Deaths blamed on smite | 68% | 72% | 76% | 91% |
| Collapse rate g0 → g2–g5 (per 1,000 NPC-ticks) | 17.6 → 6.7–10.7 | 16.4 → 4.3–6.8 | 15.8 → 4.7–7.5 | g0 only |

Reading:
- **Smiting, not hunger, is what knocks NPCs down.** That changes slice 4: the
  prayer trap is the main lever, and starvation tuning comes second.
- Collapse rates already fall with generation. Two confounds: generation 0
  lives through the chaotic opening ticks, and attribution favors big single
  hits (see `gotchas.md`). Slice 2's multi-seed harness should report rates
  within the same time window before we call this criterion met.
- "Deaths" are mostly smite-driven: collapse age penalties push NPCs past
  `old_age`, and then the next smiting kills them.

### Slice 2: Experiment harness (`scripts/sweep.py`, new)
- `--seeds 5 --ticks 10000 --set metabolism_rate=0.008 --set smite_damage=0.1`
  (repeatable `--set`, parsed through `Config.from_dict`).
- `--scripted` mode re-applies `ScriptedController` to every NPC each tick, so
  spawned and born NPCs are covered (fixes the gotcha without touching `sim/`).
- Output: one row per config with mean ± sd across seeds for: collapse rate by
  generation bucket, min-nutrient mean, cause shares, births, spawns, max generation.
- Also report collapse rate by generation **within the late time window only**
  (e.g. the last half of the run), so generation 0 isn't penalized just for
  living through the chaotic start.
  Optionally write CSV to `runs/` (gitignore it).
- Stays outside `sim/` (rule 4) and uses only `sim.rng` (rule 7).
- **Tests:** same seed + config gives the same summary twice.

### Slice 3: Honest stability check (`sim/simulation.py: is_stable`)
- Require `spawns` in the window to be at most a small fraction of births (new
  tunable, e.g. `stable_max_spawn_fraction` in `config.py`) **and** the population
  to sit above `min_population` on average.
- This will make `--until-stable` stop "succeeding" today. That's correct; note it
  in the README Status.
- **Tests:** a run pinned at the floor is not stable; a synthetic history with
  births and no spawns is.

### Slice 4: Economy tuning (`sim/config.py` only, no code)
Make **instinct viable first, then learning:**
1. Use `sweep.py --scripted` to find numbers where the forager rarely starves.
   Candidate knobs: `metabolism_rate`, `nutrient_decay`, `nutrition_per_bite`,
   `bite_size`, `food_growth_rate`, `idle_hunger_multiplier`.
2. Soften the prayer trap for random brains: lower `smite_damage`, or raise
   `smite_decay`. Keep smiting meaningful: it should still be a cost evolution can
   learn to avoid.
3. Rerun with evolved brains and check the pass criteria.
- Record each kept change and its reason in a short table at the bottom of this
  file, so the tuning history isn't lost.

### Slice 5 (only if slice 4 isn't enough): brain capacity and starting bias (`sim/brain.py`, `sim/config.py`)
- Try `hidden_units` 24 or 32 first (no code change).
- Optional `init_output_bias` in config (default 0 = today's behavior): a small
  positive bias on the `eat` output at birth. That's an *instinct*, which ROADMAP
  M1 allows ("mild eat-when-hungry bias"). Rule 6 still applies: never bias
  `give`, `share`, `mate`, `pray`. Those must emerge.
- **Tests:** bias 0 gives bit-identical brains to today (the snapshot test still
  passes); the brain JSON format is unchanged.

## Open decisions (5zorro)
- Should M1 be judged with smiting softened, or must evolution learn to avoid
  praying under today's numbers? (It affects slice 4 step 2.)
- Is the `eat` starting bias acceptable as an "instinct", or should M1 pass on
  random initialization alone?
- Run length for the pass criteria: 10k ticks is ~35 s per seed in 2D today.

## Tuning log
| Date | Change | Why | Effect (seeds × ticks) |
|---|---|---|---|
