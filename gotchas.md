# Gotchas

Traps that already bit us, by area. Add to this when something surprises you.

## Measuring evolution
- **`--until-stable` can be satisfied by the population floor.** `is_stable()`
  checks low population variance plus births > 0. When the hall-of-fame top-up
  holds the population at exactly `min_population`, the variance is 0, and a
  single stray birth in the window passes the check. "Stable" then means "on life
  support". Check the `spawn` column before believing it (M1 plan, slice 2).
- **`ScriptedController` overrides don't survive the top-up.** Overrides are keyed
  by NPC id. Spawned and born NPCs get new ids and run their random or evolved
  brain, so a "scripted population" run is scripted only for the starting NPCs.
- **One seed is an anecdote.** Collapse counts swing a lot between windows and
  seeds. Compare configs over several seeds.
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
