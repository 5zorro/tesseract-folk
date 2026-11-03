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
- **The stats window resets `npc.eaten`.** `diet_diversity` is per sampling window,
  not per lifetime.

## Time and aging
- **Collapses add `collapse_age_penalty` (150) of age.** With ~2 collapses per NPC
  per 250 ticks, NPCs hit `old_age` (1500) in roughly 700 ticks. Most "deaths" are
  collapse-accelerated aging, not real old age.
- `age` only advances while `clock.aging_active` is true. Headless runs default to
  `player_active=True`, so they age normally. `lifetime` always advances.

## Environment
- A venv doesn't survive being moved: its `Scripts/*.exe` launchers hard-code
  the old path. After moving the folder, delete `.venv` and recreate it.
- Commit from Windows git: it uses the GitHub noreply identity. WSL git is set
  to a personal email, which shouldn't go into this public repo's history.
- `.venv/` is created on the Windows side (`.venv/Scripts/python`). A WSL shell
  needs its own venv (`.venv/bin/python`); don't share one between the two.
