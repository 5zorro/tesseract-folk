# Gotchas

Traps that already bit us, by area. Add to this when something surprises you.

## Measuring evolution
- **`--until-stable` used to be satisfied by the population floor** (fixed in M1
  slice 3). The old check passed a population held at exactly `min_population`
  by top-ups (zero variance) as long as one stray birth occurred. Now
  `stability_problems()` rejects top-up-heavy windows and populations on the
  floor. Expect `--until-stable` to run to `--max-ticks` and report why until M3
  is solved; that's honest, not broken.
- **`ScriptedController` overrides don't survive the top-up.** Overrides are keyed
  by NPC id. Spawned and born NPCs get new ids and run their random or evolved
  brain, so a "scripted population" run is scripted only for the starting NPCs.
  Use `scripts/sweep.py --variant controller=scripted`, which re-covers every NPC
  each tick (`cover_with`).
- **One seed is an anecdote.** Collapse counts swing a lot between windows and
  seeds. Compare configs with `scripts/sweep.py` (5+ seeds).
- **Generation 0 is gone by the late window.** By halfway through a 10,000-tick
  run, every generation-0 NPC has died. So late-window comparisons start at g1–2,
  and a "-" in the g0 column there is expected, not a bug.
- **`sweep.py` uses every CPU core by default** (one process per run). Pass
  `--jobs N` if the machine needs to stay responsive.
- **Cause attribution favors big single hits.** A collapse is blamed on the cause
  with the most damage since the NPC was last at full health. One smiting
  (0.3) outweighs 14 ticks of starvation (0.02 each), so an NPC weakened by
  hunger and finished by a smiting counts as "smite". Read cause shares as
  "what finished them off", not as the only reason.
- **Per-generation collapse rates are confounded by time.** Generation 0 lives
  through the chaotic start of a run; later generations live later. Compare
  generations within the same time window (M1 plan, slice 2).
- **Old snapshots resume with today's defaults for new config fields.**
  `Config.from_dict` fills missing keys with current defaults, so a snapshot
  saved before `smiting` existed resumes with smiting off. Resumes are
  identical only within one code version.
- **Per-generation tallies aren't saved in snapshots.** A `--load` run starts its
  `generation_lifetime` and `generation_collapses` from zero.
- **The stats window resets `npc.eaten`.** `diet_diversity` is per sampling window,
  not per lifetime.

## Time and aging
- **Collapses add `collapse_age_penalty` of age** (300 since 2026-11-02, 600 in
  the nursery). A few collapses can use up most of the 1,500 years before
  `old_age`, so many "deaths" are collapse-accelerated aging, not real old age.
  (Under the old rules, 150 per collapse and ~2 collapses per 250 ticks, NPCs
  hit `old_age` in roughly 700 ticks.)
- `age` only advances while `clock.aging_active` is true. Headless runs default to
  `player_active=True`, so they age normally. `lifetime` always advances.

## Environment
- **Editing docs by script: replace exact anchors, never slice to a marker.** A
  script that rebuilt `handoff.md` as `head + new text` (without the old tail)
  silently cut its Setup, table and rules sections (commit b6101ad; restored in
  3d0c8af). Assert each anchor occurs once, and diff before committing.
- **Bash heredocs can fail on Python with quotes or backslashes** ("unexpected
  EOF"). Write the script to the scratchpad with the Write tool and run it.
- A venv doesn't survive being moved: its `Scripts/*.exe` launchers hard-code
  the old path. After moving the folder, delete `.venv` and recreate it.
- Commit identity: the repo's own `.git/config` pins `user.name`/`user.email`
  to the GitHub noreply identity (2026-11-05), so Windows and WSL git both
  commit as 5zorro. WSL's global git identity is personal: never remove the
  repo-local setting, and set it in any new clone.
- `.venv/` is created on the Windows side (`.venv/Scripts/python`). A WSL shell
  needs its own venv: use `.venv-wsl/` (gitignored), not `.venv/`.
- Line endings: Windows git has `core.autocrlf=true`, WSL git has nothing.
  `.gitattributes` (`* text=auto`) keeps both seeing a clean tree on the same
  checkout; keep it.
- An agent's shell here may be Windows (the desktop app's Bash is Git Bash, and
  plain `python` is Windows Python without pytest: use `.venv/Scripts/python`).
  To run in WSL from it: `wsl.exe -e sh -c 'cd "/mnt/c/Users/.../tesseract-folk" && ...'`.
- The local `commit-msg` hook (`.git/hooks`, untracked) rejects attribution
  lines from any AI tool. It can also reject a harmless message such as "fix
  made by moving the cursor" ("made by ... cursor"); reword it, never
  `--no-verify`. A reinstallable copy lives outside the repo.

## Nursery
- **Probe scripts were throwaway.** The deadlier-collapse, pretraining and seasons
  probes (2026-11-02) ran from a temp folder that's gone now. Their results and
  methods are in the M1 plan. Rebuild them with `sweep.py` features, not from memory.
- **Gentle worlds slowly lose the nursery's advantage.** Generations born under
  the play rules get worse (1.9 → 2.4 → 3.5 collapses per 1,000 NPC-ticks with
  nursery-2), because weak selection lets mutations pile up. Compare whole-run
  rates or early windows when judging a brain pool, not just the late window.
- **Generation numbers carry over** from the pool, so a seeded world starts at
  generation ~5–10, and its g0 column is empty. That's expected.
- **Brain shapes must match:** `dims`, `n_food_types`, `n_nutrients`,
  `hidden_units` and `memory_units` must equal the nursery's, or `seed_brains`
  refuses. A 2D nursery can't seed a 4D world.
- **Pools saved before food scent need `--set food_scent=false`** (nursery-1/2):
  scent adds brain inputs, so `seed_brains` refuses them otherwise. Old
  snapshots `--load` fine: format 1 loads with scent off automatically.
- **In 4D at size 10, default patches cover everything.** Radius 4 reaches every
  cell, so every food grows everywhere and foraging is trivial. Use
  `--set food_patch_radius=2.0` for 4D runs (about half the map per food, like 2D).
- **"Patches" cover most of the map.** With `food_patch_radius=4`, Gaussian tails
  reach ~8 cells, so each food type can hold a full bite on 44–71% of the map,
  even with no thin layer. "Standing on food" checks pass almost everywhere.
- **Results before 2026-11-02 used older rules:** eating counted as idle (2.5×
  hunger while eating), a thin food layer grew everywhere, hunger was faster
  (`nutrient_decay` 0.004) and collapses cheaper (`collapse_age_penalty` 150).
  Don't compare numbers across those changes; the plan's tables say which rules
  each used. Old snapshots
  still resume that way (`snapshot.py: LEGACY`, `food_baseline_fraction` saved
  in their config).
- **A new sense shows nothing from scratch.** Gentle worlds barely select, so a
  sense only pays off after nursery training. Judge senses through the nursery.
- **Pool fitness comes from the nursery's rules.** The hall of fame starts with
  fitness scores earned under harsh rules, so new deaths in a gentle world
  must beat those numbers to get in.
- **A control world changes more than the one thing.** `food_layout=shared`
  also cuts the number of zones from 9 to 3 and crowds NPCs into stink. Always
  run scratch brains in both worlds too: if scratch shows the same gap, it's
  geometry, not learning (M2 slice 3).
- **Bite-based travel metrics inherit the eat instinct.** `eat` picks the food
  that fixes the NPC's deficit, so anything recorded at a bite (zone switches,
  "did it reach the needed food") looks diet-directed even for brains that
  know nothing of diet; the scripted forager scores highest. Measure moves, not
  bites, and compare with scratch brains (M2 slice 3b).
- **Random walks aren't neutral toward targets.** A random step drifts away
  from near targets faster than from far ones, so "moved toward the far,
  needed food" scores positive by chance. Always subtract the random-step null
  (`approach_null`, M2 slice 3c), and treat "scratch" brains as partly
  evolved, not blank.
- **Matching cell counts across dimensions shrinks the world.** ~1,000 cells is
  32 wide in 2D but 10 in 3D and 6 in 4D, so every food is a few steps away and
  diet needs no travel. Match distances between foods too, not just coverage
  (M2 slice 3d). Bigger brains also evolve slower: 16 hidden units was never
  better than 4.
- **Crumbs are everywhere, and `eat` takes them.** Gaussian patches never reach
  zero, so almost every cell grows a crumb. `eat` takes ground food before
  carried food (so carried food is never eaten while any crumb is underfoot),
  and it picks food by need per unit, ignoring amount. In higher dimensions most
  of a patch is thin edge, so bites shrink (4D: 7% of a full bite). Check bite
  sizes (`scripts/probe_supply.py`) before blaming brains.
- **`mutation_rate` is per weight, so bigger brains get more mutations per
  birth** (~52 at 8 hidden units, ~102 at 16, ~200 at 32). Comparing brain
  sizes at one rate also changes how disruptive each birth is
  (`docs/research-tuning.md`). Use `mutations_per_birth` to hold it fixed; and
  don't go by the textbook 1 per child: it loses here (plan-m2 slice R1).
- **Runs before 2026-11-04's default change aren't comparable to later ones.**
  Mutation became lineage-adaptive at 30 per child; earlier CSVs and
  `snapshots/ladder` nurseries used ~52-102 per weight. Compare against the
  new baselines (`runs/2026-11-04-defaults-*.csv`, `snapshots/ladder2`).
- **1D's ladder world is too big to compare.** Matched on cell count (1,024
  cells), its shortest trip between foods is 82 steps and a random walk takes
  ~10,000, so it fails for world size, not brain size (plan-m2 slice R6). A 1D
  world matched on trip time would be needed before judging 1D brains.
- **One life is a noisy score.** A brain picked for a perfect life (no
  collapses) has near-clones that are barely better than average (plan-m2
  slice R3). Judge brains over several lives or lineages, and don't read much
  into "child beat parent".
- **Smell isn't weak in 4D, whatever the decay length says.** NPCs sense the
  scent difference relative to its sum, so even a faint smell points the right
  way (92-100% in 2D-4D, `scripts/probe_scent.py`). Don't "fix" reach unless
  senses get noise or a threshold.
- **Speed refactors must keep the hashes.** Run `scripts/fingerprint.py` before
  and after; they must match. Since G1 (2026-11-05) draws are keyed, so an
  extra draw no longer shifts the others, but a changed key does (a different
  id, tick or purpose). New purposes go at the end of `sim/keyed.py`'s list;
  never renumber one.
- **A world's arrays are views into its batch (G3).** Write them in place
  (`sim.world.food[...] = x`), never rebind (`sim.world.food = x` detaches
  the world from the engine), then call `sim.world_changed()`. Stepping any
  Simulation in a batch steps all of them. Worlds in a batch must share
  `STRUCTURAL` settings and the tick.
- **4D speed is memory-bound now, not Python-bound** (G3). More processes don't
  help 4D sweeps much; the world step's 4D maps share the memory bus. Measure
  with the whole machine loaded, not one process.
- **Don't keep `sim.npcs` entries across ticks.** They're views into array
  slots, and a dead NPC's slot is reused; a stale view raises `LookupError`
  rather than read the newcomer. Keep ids. `sim.npcs` is rebuilt (by id) on
  every access, so `sim.npcs.pop()` or `.reverse()` changes nothing: set
  `npc.alive = False`, or assign `sim.npcs = [...]`.
- **Hooks on per-NPC methods only fire in the reference engine.** The array
  engine never calls `_decide`/`_act` per NPC; a probe that wraps them must
  build `sim.reference.ReferenceSimulation` (same results, slower).
- **The engines test is bit-exact, and that depends on the math library.**
  Batched `np.matmul` equals per-NPC `@` with this machine's NumPy/OpenBLAS.
  If `tests/test_engines.py` fails on another machine with only last-bit
  differences, that's why; check with a tolerance before suspecting the rules.
- **Nothing may depend on the order of `sim.npcs`.** Arrays (G2 of the GPU
  plan) won't keep it. Choices among neighbors sort by id; every phase of a
  tick goes in the keyed priority order. `tests/test_tick_rules.py` reverses
  the list every tick and expects the same run.
- **Snapshots from before G1 (format < 4) don't resume** (other tick rules);
  `--brains-from` still takes their brains. Old nursery folders under
  `snapshots/` are pre-G1: retrain into a new `--out` (ladder.py refuses to
  reuse them).
