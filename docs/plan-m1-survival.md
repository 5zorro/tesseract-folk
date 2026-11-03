# Plan: M1 Survival

Status: **slices 1–3, 4b (nursery) and 6 (food scent) done; criteria settled
(2026-11-02). Criteria 1–2 met; 3 (nutrients above 0.4) is the gap; 4 (4D) not
yet measured.** Slices are ordered;
each one ends with tests passing and a commit. Open decisions (bottom) are 5zorro's.

**For a new session:** read `handoff.md`, `gotchas.md` and this file. Do the
slices in order. Don't tune numbers (slice 4) before slices 1 to 3 exist: without
them you can't tell whether a change helped.

## Goal (from ROADMAP.md)
**Pass:** collapses per NPC fall over generations, and NPCs keep nutrients up
without help.

To make that testable, M1 passes when, **over 5 seeds × 10,000 ticks** (2D, default size)
(criteria settled by 5zorro, 2026-11-02):
1. **The nursery learns.** Under nursery rules (`collapse_age_penalty=600`), the
   collapse rate (collapses per NPC per 1,000 ticks of lifetime) falls from g1–2
   to later generations in the late window, beyond seed-to-seed noise.
2. **Play worlds benefit.** Gentle play worlds started from the nursery's brains
   (`--brains-from`) collapse less than worlds started from scratch, beyond seed
   noise. Births and top-ups are reported alongside, not required (M3 owns them).
3. **NPCs keep nutrients up.** In those play worlds, the mean of each NPC's lowest
   nutrient stays above **0.4** (the level at which NPCs heal) in the last quarter.
4. The same holds at `--dims 4 --size 10` (a shorter run is fine).

Why judged this way: pillar 4 ("young can't die") keeps play worlds gentle, so
they have almost no selection and can't show a trend over generations. Evolution
happens in the nursery; play worlds show what it bought.
Dropped: "starvation is no longer the top cause". With smiting off, starvation is
nearly all that's left, so it just repeated criterion 1.
No `eat` starting bias for now: food scent (slice 6) is tried first, so we learn
whether brains can forage unaided.

Births and a top-up-free population are M3's job, not M1's. Don't chase them here.

**Smiting is off for M1** (5zorro, 2026-11-02: `Config.smiting = False`). M1 is
judged on hunger alone; piety and smiting come back for M5.

**Where the criteria stand** (2026-11-02, after food scent; nursery-4, slice 6):
1. **Met:** the scent nursery's rate fell 3.2 (g0) → about 1.7–2.2 (g5+) in
   stage 1, and sat around 1.5 in stage 2.
2. **Met:** 2.7 ± 0.1 from nursery-4 vs 4.1 ± 0.3 from scratch.
3. **Not met:** the lowest nutrient is 0.34 ± 0.01 (nursery-4), against a bar
   of 0.4. Scent barely moved it (0.33 with nursery-2). The diagnosis under slice 6
   found the cause is intake (small bites, idle penalty while eating), not diet
   balance, and that the scripted forager only reaches 0.40–0.42.
4. **Not measured** with a 4D nursery yet. 4D from scratch is flat (3.0 → 3.1).

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

### Slice 2: Experiment harness ✅ (2026-11-02)
**Built:** `scripts/sweep.py`, as specified below:
- `--variant` / `--set` overrides are typed and validated against `Config`.
- The `controller=scripted` pseudo-key re-covers every NPC each tick.
- Late-window per-generation rates, CSV output to `runs/` (gitignored).
- Runs in parallel across CPU cores: 15 runs × 10,000 ticks in about 1 minute.
- Tests: `tests/test_sweep.py`.

**First sweep, 2D** (5 seeds × 10,000 ticks; `runs/2026-11-02-m1-first.csv`, local only):
| | Baseline | `smite_damage=0` | Scripted forager |
|---|---|---|---|
| Collapses / 1,000 NPC-ticks, whole run | 6.9 ± 0.5 | 4.6 ± 0.2 | 6.9 ± 0.9 |
| Late window: g1–2 → g3–5 → g6–10 | 6.8 → 4.9 → 4.6 | 4.1 → 3.8 → 2.9 | 6.7 → 6.4 → 6.5 (flat) |
| Causes: smite / nutrient / body / stink | 70 / 25 / 5 / 0% | 0 / 77 / 23 / 0% | 0 / 90 / 0 / 10% |
| Mean lowest nutrient, last quarter | 0.33 | 0.30 | 0.39 |
| Births / top-up spawns | 13 / 328 | 7 / 276 | 0 / 360 |

**First sweep, 4D** (`--set dims=4,size=10`, 5 seeds × 4,000 ticks):
| | Baseline | Scripted forager |
|---|---|---|
| Collapses / 1,000 NPC-ticks | 7.6 ± 0.6 | **0.0** |
| Late window: g1–2 → g3–5 → g6–10 | 5.2 → 5.2 → 4.4 (n=2) | no collapses |
| Causes: smite / starvation | 80 / 19% | none |

Reading:
- Evolution is working in 2D. Late-generation brains (4.6) now collapse less
  than the hand-coded forager (6.5), and the forager's flat line is the control
  that proves it.
- In 4D the forager never collapses, so the 4D economy is easy, and smiting
  (80%) is all that stands between evolved brains and the forager's record.
  In 2D the forager starves (90% of its collapses), so the 2D economy is harsh.
  Slice 4 should tune these separately rather than assume one fix fits both.
- Smiting off cuts collapses by a third, but starvation then takes over.
- Top-up spawns (~330 per run) still dwarf births (~13). That's M3, as expected.

**Hunger-only baseline** (smiting off; 5 seeds; `runs/2026-11-02-m1-nosmite*.csv`):
| | 2D brains | 2D scripted | 4D brains (8k ticks) | 4D scripted |
|---|---|---|---|---|
| Collapses / 1,000 NPC-ticks | 3.9 ± 0.2 | 6.9 ± 0.9 | 3.1 ± 0.1 | 0.0 |
| Late window: g1–2 → g3–5 → g6–10 | 3.5 → 3.5 → 3.7 | 6.7 → 6.4 → 6.5 | 3.0 → 3.1 → – | 0 → 0 |
| Causes: nutrient / body / stink | 92 / 7 / 1% | 90 / 0 / 10% | 89 / 11 / 0% | – |
| Mean lowest nutrient, last quarter | 0.30 | 0.39 | 0.32 | 0.66 |
| Births / top-up spawns | 21 / 250 | 0 / 360 | 7 / 184 | 0 / 99 |

Reading:
- Turning smiting off halves collapses, and births rise from about 13 to 21.
- **Evolution isn't improving foraging.** Brains are better than the 2D forager
  from generation 0 onward (4.7 vs 8.1), but they don't get better over
  generations. Selection pressure on hunger looks too weak. Possible reasons to
  check in slice 4/5:
  - Top-up fitness (`offspring × 500 + lifetime − collapses × 100`) barely
    separates good foragers from bad ones.
  - Collapses are forgiving (respawn at 0.5 health with nutrients reset to 0.4).
  - Mutation and selection are mostly happening through top-ups, not births.

**Original spec:**
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

### Slice 3: Honest stability check ✅ (2026-11-02)
**Built:**
- `Simulation.stability_problems()` returns the reasons a population isn't
  stable, and `is_stable()` is true only when there are none.
- New tunables `stable_window`, `stable_max_cv` and `stable_max_spawn_fraction`
  (0.1 top-ups per birth) are in `config.py`.
- A population whose mean sits at or below `min_population` is never stable.
- `run_headless.py --until-stable` prints the reasons when it gives up, and warns
  if it saves a snapshot that never stabilized.
- `sweep.py` has a `stable%` column.
- Tests: `tests/test_stability.py`.

Today's default world now fails with "too many top-ups (95 spawns vs 3
births)" and "population sits on the top-up floor". Before this slice it
reported "Stable at tick 2750".

**Original spec:**
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
2. ~~Soften the prayer trap.~~ Resolved: smiting is off for M1 (5zorro,
   2026-11-02). Revisit in M5.
2b. **New, from the hunger-only baseline:** check selection pressure before
   tuning food numbers. The trend is flat even though brains beat the forager.
   Try variants such as a harsher collapse (lower respawn health or nutrients)
   or a bigger `collapse_age_penalty`. Rule 6 still applies: don't add fitness
   rewards for specific behaviors.

   **Probe, 2026-11-02** (throwaway script that patched `_collapse`; 5 seeds × 8,000 ticks, 2D, smiting off):
   | Variant | Late window: g1–2 → g3–5 → g6–10 | Lowest nutrient | Births | Top-ups |
   |---|---|---|---|---|
   | Today (collapse = respawn) | 3.5 → 3.8 → 3.6 (flat) | 0.30 | 16 | 198 |
   | Collapse = death | 2.7 → 2.0 → 1.6 | 0.42 | 29 | 478 |
   | 3rd collapse = death | 3.8 → 3.1 → 2.8 | 0.33 | 21 | 270 |
   | `collapse_age_penalty=400` | 3.1 → 2.8 → 2.5 | 0.33 | 21 | 268 |
   | Easier births (`adult_age=150`, `reproduce_min_mass=1.0`) | 4.1 → 4.0 → 4.2 (flat) | 0.30 | 44 | 187 |

   Reading:
   - **The flat trend is weak selection, and costlier collapses fix it.** All
     three harsher variants bring the generational improvement back.
   - Collapse = death works best (it would even meet a 0.4 nutrient bar), but it
     breaks DESIGN pillar 4 ("young NPCs can't die permanently"). It also more
     than doubles top-ups, so evolution would run through hall-of-fame copies
     instead of births. That pulls against M3.
   - A bigger age penalty gets part of the effect from one config number, and
     the pillar survives.
   - More births alone don't help. Births aren't selective enough, since easier
     rules let anyone breed. Selective births (M3) and costly collapses (M1)
     are separate levers.
   - **Decision (5zorro):** which way? (a) keep the pillar and tune
     `collapse_age_penalty` (plus maybe N strikes), or (b) make collapse = death
     and rewrite pillar 4. **Decided: (a), keep the pillar** (2026-11-02).

   **Penalty sweep, 2026-11-02** (5 seeds × 10,000 ticks, 2D; `runs/2026-11-02-m1-penalty.csv`).
   `collapse_health` and `collapse_nutrient_floor` moved into config at the same
   values (0.5 and 0.4), so they can be swept too.
   | `collapse_age_penalty` | Late window: g1–2 → g3–5 → g6–10 | Lowest nutrient | Births | Top-ups |
   |---|---|---|---|---|
   | 150 (today) | 3.5 → 3.5 → 3.7 (flat) | 0.30 | 21 | 250 |
   | 300 | 3.1 → 2.8 → 3.4 (noisy) | 0.33 | 27 | 300 |
   | 400 | 3.1 → 2.6 → 2.5 | 0.33 | 27 | 330 |
   | 600 | 2.9 → 2.2 → 2.0 | 0.35 | 20 | 366 |
   | 900 | 2.5 → 2.0 → 2.0 | 0.36 | 25 | 411 |
   | 1200 | 1.9 → 1.6 → 1.4 | 0.38 | 21 | 471 |

   The bigger the penalty, the steeper the improvement, but it works the same
   way collapse = death did: NPCs age out sooner and top-ups replace them. Selection
   needs deaths. The open question is where those deaths happen.

   **5zorro's reframe, and a probe:** we aren't starting from scratch, so evolve
   brains under harsh rules first, then play under gentle ones. The probe
   (5 seeds) trained for 10,000 ticks, switched `collapse_age_penalty` back to
   150, and measured the next 5,000 ticks:
   | Training | Collapses / 1,000 NPC-ticks in the gentle phase |
   |---|---|
   | Gentle all along (control) | 3.19 ± 0.38 |
   | Penalty 600 | **2.65 ± 0.42** (about 17% fewer, ~2 SE) |
   | Penalty 1200 | 2.82 ± 0.25 |

   So pretrained brains carry their advantage into gentle play, even after short
   training. This reconciles the two goals: deaths happen in an offline
   "nursery", and the game world keeps pillar 4. Next step: the nursery slice
   below. The play-time default for `collapse_age_penalty` stays 150 for now.

### Slice 4b: Nursery, a pretrained brain pool ✅ (2026-11-02)
**Built:**
- `sim/nursery.py: load_brain_pool, seed_brains`.
- `run_headless.py --brains-from <snapshot>` and `--set KEY=VALUE`.
- The sweep pseudo-key `brains_from=<snapshot>`.
- Override parsing moved to `sim/config.py: parse_overrides`.
- Tests: `tests/test_nursery.py`.

**First nursery** (local, gitignored, ~1 MB each):
- `snapshots/nursery-1`: seed 100, `collapse_age_penalty=600`, 20,000 ticks.
  The rate fell from 3.3 (g0) to about 1.8 (g3+).
- `snapshots/nursery-2`: seeded from nursery-1, seed 101, same rules,
  20,000 ticks. It plateaued at about 1.7–2.0.

**Payoff under gentle play rules** (default config; 5 seeds × 10,000 ticks on
maps the nursery never saw; `runs/2026-11-02-nursery.csv`):
| | Scratch | Nursery-1 | Nursery-2 | Scripted |
|---|---|---|---|---|
| Collapses / 1,000 NPC-ticks | 3.9 ± 0.2 | **2.8 ± 0.2** | **2.9 ± 0.1** | 6.9 ± 0.9 |
| Births | 21 | 57 | **156** | 0 |
| Top-up spawns | 250 | 190 | **130** | 360 |
| Max generation | 6.6 | 11.0 | 13.6 | 6.8 |
| Late window by generation | 3.5 → 3.5 → 3.7 | 3.6 → 2.7 → 2.8 → 3.9 | 1.9 → 2.4 → 3.5 (g3–5 → g6–10 → g11+) | flat |

Reading:
- **Pretrained brains generalize to new maps** and collapse about 28% less.
- **Births beat top-ups for the first time** with nursery-2 (156 vs 130). That's
  a real step toward M3: healthier NPCs reach breeding condition.
- **The advantage erodes in gentle worlds.** Generations born there get worse
  (nursery-2 late window: 1.9 → 2.4 → 3.5). With weak selection, mutations pile
  up. Options, none built yet:
  - Re-seed from the nursery periodically.
  - Use a lower `mutation_rate` in play than in the nursery.
  - Keep mild selection in play (e.g. `collapse_age_penalty` around 300).
- The second nursery stage barely beat the first. Longer or harsher training,
  or more hidden units (slice 5), may be needed to go further.
- ~~Criteria question for 5zorro~~ Decided: judge M1 on the nursery's trend plus
  play-world collapse rate (see Goal).

**Seasons probe** (5zorro's question: can harsh and gentle alternate?). Throwaway
script that switched `collapse_age_penalty` between 600 and 150 on a cycle,
starting from nursery-2 brains, on 5 unseen maps × 20,000 ticks, measured over
the second half:
| Variant | All phases | Gentle phases only | Births | Top-ups |
|---|---|---|---|---|
| Gentle always | 2.77 ± 0.38 | 2.77 ± 0.38 | 114 | 144 |
| Harsh always | 1.70 ± 0.09 | – | 115 | 214 |
| 1,000 harsh / 1,000 gentle | 2.21 ± 0.06 | 2.64 ± 0.07 | 117 | 179 |
| 2,500 / 2,500 | 2.11 ± 0.25 | 2.57 ± 0.36 | 134 | 160 |
| 1,000 harsh / 3,000 gentle | 2.50 ± 0.07 | 2.66 ± 0.11 | 110 | 164 |

Reading:
- Seasons work mechanically: rules can change mid-run (`sim.cfg` is live).
- What players would see (gentle phases) improves only a little, about 4–7%,
  within noise.
- The clearer effect is **consistency**: seed-to-seed spread falls from ±0.38 to
  ±0.07–0.11, so fewer worlds drift badly. That's the drift problem, partly solved.
- Not built as a feature yet. If it is, a config schedule (e.g.
  `season_length`, `harsh_fraction`, and which knobs change) would replace the
  probe's hand-rolled loop. A more immersive harsh season would be a famine or
  winter (less food growth) rather than an abstract penalty. Untested.

**Original proposal:**
- `run_headless.py --brains-from <snapshot>`: start a **fresh** world (any seed
  or config) whose starting NPCs and hall of fame carry the best brains from a
  snapshot, ranked by fitness. Fail clearly if the brain shapes don't match
  (dims, hidden units, memory units).
- Training runs: harsh settings (e.g. `collapse_age_penalty=600`), long, saved
  with `--save`, and chainable (train → save → train more from those brains).
- Measure with `sweep.py`: add a `brains_from=<path>` pseudo-key so pretrained
  and from-scratch worlds can be compared over seeds.
- Tests: brains load into a fresh world unchanged; mismatched shapes fail;
  mass stays conserved; determinism holds.
- Ties into DESIGN §12 ("baseline snapshot"): the shipped baseline would come
  from the nursery.
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

### Slice 6: Food scent (`sim/world.py`, `sim/simulation.py: sense`, `sim/config.py`)
5zorro's idea (2026-11-02): an NPC short on a nutrient can smell the food that has
it, so brains that follow the right scent get rewarded. Today NPCs only sense
food in the cells right next to them, so a patch a few cells away is invisible.
- **World:** a `scent` field per food type, shaped like `food`. Each tick, food
  emits scent in proportion to how much is there, and the scent spreads and fades
  like stink, but fades slower so it reaches farther. It's a signal, not mass.
- **Senses, per food type:** the scent level here, squashed to 0..1
  (`s / (s + scent_half)`), and a relative gradient per axis,
  `(s+ - s-) / (s+ + s-)`. The relative gradient points uphill at any distance,
  the way real noses compare concentrations. 2D: 38 → 47 inputs; 4D: +15.
- **No scripting:** the brain gets the raw scents and its own nutrient levels.
  Linking "short on nutrient 2" to "follow scent 2" is for evolution to find.
- **Config:** `food_scent` (on/off; fixed for a world's life, because it changes
  the brain shape), `scent_emission`, `scent_diffusion`, `scent_decay`, `scent_half`.
- **Old snapshots:** snapshot format 2 saves the scent field. Format-1 snapshots
  load with `food_scent=False`, so they resume exactly as before, and their
  brains still fit. `--brains-from` an old pool needs `--set food_scent=false`.
- **Tests:** scent spreads and points toward food; scent doesn't change mass;
  sensor size matches at dims 2 and 4; off gives today's 38 inputs; old
  snapshots still load.
- **Measure:** from scratch, scent vs no scent (5 × 10k). Then retrain the nursery
  with scent and compare play worlds against nursery-2, mainly on criterion 3.

**Built** (2026-11-02): as proposed. Tests: `tests/test_scent.py`. Run cost +8%.

**From scratch, scent doesn't help** (5 seeds × 10,000 ticks, gentle rules;
`runs/2026-11-02-scent-scratch.csv`): 4.1 ± 0.3 collapses with scent vs 3.9 ± 0.2
without, lowest nutrient 0.30 both. Expected: gentle worlds barely select, so
nobody learns to use a new sense, and nine extra random inputs are just noise.

**Through the nursery, it does.** New nursery with scent, same recipe as
nursery-1/2 (local, gitignored):
- `snapshots/nursery-3`: seed 100, `collapse_age_penalty=600`, 20,000 ticks.
  3.2 (g0) → 1.7–2.2 (g5+), about like nursery-1.
- `snapshots/nursery-4`: from nursery-3, seed 101, same rules. About 1.5,
  a little below nursery-2's 1.7–2.0.

Play worlds on unseen maps (5 seeds × 10,000 ticks, gentle rules;
`runs/2026-11-02-scent-nursery.csv`):
| | Scratch (scent) | Nursery-2 (no scent) | **Nursery-4 (scent)** |
|---|---|---|---|
| Collapses / 1,000 NPC-ticks | 4.1 ± 0.3 | 2.9 ± 0.1 | **2.7 ± 0.1** |
| Lowest nutrient, last quarter | 0.30 | 0.33 | 0.34 |
| Births | 15 | 156 | **243 ± 31** |
| Top-up spawns | 258 | 130 | **64 ± 20** |
| Max generation | 6.2 | 13.6 | 30.4 |
| Late window, oldest buckets | 3.6 → 4.1 | 2.4 → 3.5 (g6–10 → g11+) | 2.2 → **2.5** |
| Passes `--until-stable`'s check | 0 of 5 | 0 of 5 | **1 of 5** |

Reading:
- Scent-trained brains breed far more (births +56%, top-ups halved). Births now
  outnumber top-ups almost 4 to 1. One world in five passed the stability check,
  a first.
- **Drift is much smaller:** late generations get worse by 0.3 instead of 1.1.
- The collapse rate improved only a little (2.9 → 2.7), and the **lowest nutrient
  barely moved (0.33 → 0.34)**. NPCs find food better but still run one nutrient
  low. Criterion 3 is still the gap.
- Stink collapses rose to 13% (from 9%): more NPCs make more poop.

**Diagnosis: why the lowest nutrient sits at 0.34** (2026-11-02,
`scripts/probe_nutrients.py`: nursery-4 brains and the scripted forager, 3 seeds,
last quarter of 10,000 ticks):
| | Nursery-4 brains | Scripted forager |
|---|---|---|
| Nutrients, lowest / middle / highest | 0.34 / 0.38 / 0.43 | 0.39 / 0.42 / 0.45 |
| Lowest < 0.4, so no healing | 68% of the time | 46% |
| Starving (lowest < 0.1) | 9% | 20% |
| Idle long enough for the hunger penalty | 10% | 55% |
| Eats (share of actions) | 14% | 58% |
| Nutrition per bite (max 0.165) | 0.068 | 0.017 |
| Food left in the world (vs capacity) | 68–79% | 64–74% |

Findings:
1. **Not a diet-balance problem.** All three nutrients sit low together, and
   which one is lowest rotates evenly across the three types. NPCs aren't
   neglecting one food.
2. **Not a food shortage.** About 70% of capacity stands uneaten, and NPCs stand
   on some food 97% of the time (the thin layer that grows everywhere).
3. **It's intake.** Brains take 0.14 bites per tick worth 0.068 each, about 0.0096
   of nutrition per tick, against at least 0.012 lost (0.004 × 3 nutrients, more
   when idle). They run a deficit, and collapses (which refill to 0.4) hold the
   average up.
4. **Bites are small.** A bite takes at most what's in the cell. NPCs mostly
   graze the thin everywhere-layer (0.1 per type per cell, half a bite) instead of
   living in patches, and satiation trims another 20%.
5. **Eating counts as standing still.** After 5 ticks without moving, hunger runs
   2.5× faster, even while eating. The scripted forager eats 58% of the time, is
   "idle" 55% of the time, and starves 20% of the time. Brains also spend about
   12% of actions on prayer, worship, share and give (useless with smiting off),
   and 20% on mate.

Testing finding 5 (5 seeds × 10,000 ticks, gentle rules;
`runs/2026-11-02-idle-probe.csv`):
| | Collapses | Lowest nutrient | Births | Top-ups | Passes stability check |
|---|---|---|---|---|---|
| Nursery-4, today | 2.7 ± 0.1 | 0.34 | 243 | 64 | 1 of 5 |
| Nursery-4, `idle_hunger_multiplier=1` | **2.1 ± 0.0** | 0.36 | **350** | **19** | **3 of 5** |
| Scripted, today | 6.9 ± 0.9 | 0.40 | 0 | 362 | 0 of 5 |
| Scripted, `idle_hunger_multiplier=1` | 3.2 ± 0.3 | 0.42 | 0 | 249 | 0 of 5 |

- The idle penalty for eating is a big drag: removing it cuts collapses 22% for
  brains and 54% for the scripted forager.
- The lowest nutrient still barely moves (0.34 → 0.36). Even the scripted
  forager, which eats whenever it's below 0.6, only reaches 0.40–0.42. **Under
  today's rules, 0.4 is about the ceiling of a pure forager**, not a bar brains
  are failing to reach.
- Not changed yet: both the idle rule and the 0.4 bar are 5zorro's call (below).

## Open decisions (5zorro)
- ~~Raise criterion 2's nutrient bar?~~ Decided: 0.4 (now criterion 3).
- ~~Reword or drop "starvation is no longer the top cause"?~~ Decided: dropped.
- ~~Judge M1 with smiting softened or not?~~ Decided: smiting off for M1.
- ~~Judge criterion 1 in the play world?~~ Decided: in the nursery; play worlds
  are judged on collapse rate vs scratch.
- `eat` starting bias as an "instinct": deferred until food scent is measured.
- **Should eating count as standing still?** Today it does, so foragers pay the
  2.5× idle hunger while they eat. Options: eating resets the idle streak (only
  loafing is punished, as pillar 2 meant), or keep it. Removing the penalty
  entirely was the probe; the targeted fix is untested. Changes the rules the
  nursery trained under, so retrain afterwards.
- **Is 0.4 the right nutrient bar?** A scripted forager reaches only 0.40–0.42
  under today's rules. Either keep 0.4 and change the economy so it's reachable
  (eating not idle, bigger bites in thin food, slower decay), or set the bar
  relative to the scripted forager (e.g. "brains match or beat it").
- Run length for the pass criteria: 10k ticks is ~35 s per seed in 2D today.

## Tuning log
| Date | Change | Why | Effect (seeds × ticks) |
|---|---|---|---|
| 2026-11-02 | `food_scent = True` (new; slice 6) | 5zorro: NPCs short on a nutrient should be able to smell the food that has it | Scratch: no change. Nursery-4 play worlds vs nursery-2: collapses 2.9 → 2.7, births 156 → 243, top-ups 130 → 64, lowest nutrient 0.33 → 0.34 (5 × 10k) |
| 2026-11-02 | `smiting = False` (new flag; was effectively on) | 5zorro: judge survival on hunger first; smiting caused ~70% of collapses | 2D collapses 6.9 → 3.9; births 13 → 21; generation trend went flat (5 × 10k) |
| 2026-11-02 | `collapse_health`, `collapse_nutrient_floor` moved to config (same values) | Rule 5; makes respawn harshness sweepable | none (refactor) |
