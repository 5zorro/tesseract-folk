# Tesseract Folk

An artificial-life society prototype: every NPC has a tiny neural net
(like *Creatures*' norns), ages, eats a balanced diet, poops, avoids stink,
prays to an all-knowing deity for secrets, and (hopefully) learns to trade.
Mass is conserved, so the economy comes from a real resource loop:

```
soil -> food -> NPC body -> bowel -> poop (stinks) -> soil
```

The world is N-dimensional (1D to 4D). 2D is for prototyping; the eventual
4D Miner mod needs two kinds of movers: land walkers on the 3D surface of the
4D world, and fish and birds that move freely in all four dimensions.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest                                   # all tests should pass
python scripts/run_headless.py --ticks 3000        # stats table, no graphics
python scripts/view.py                             # watch it in 2D (needs pygame)
```

More:

```bash
python scripts/run_headless.py --dims 4 --size 10 --ticks 500     # try 4D
python scripts/run_headless.py --until-stable --max-ticks 20000 --save snapshots/baseline
python scripts/run_headless.py --load snapshots/baseline --ticks 2000
python scripts/sweep.py --seeds 5 --variant metabolism_rate=0.008   # compare configs over seeds
python scripts/run_headless.py --set collapse_age_penalty=600 --ticks 20000 --save snapshots/nursery-1  # evolve offline
python scripts/run_headless.py --brains-from snapshots/nursery-1 --ticks 5000   # fresh world, trained brains
python scripts/ladder.py --help                     # train nurseries and score them in 1D-4D worlds
```

Viewer keys: SPACE pause, A toggle AFK (aging pauses), F turn the clock
(+500 ticks), S reveal secrets, +/- speed.

## Layout

```
sim/            engine-agnostic simulation core (no rendering)
  config.py     every tunable number
  world.py      N-d soil, food, poop, stink fields
  brain.py      tiny neural nets (plain arrays, JSON-serializable)
  npc.py        NPC state and the action list
  simulation.py tick loop: sense -> think -> act -> metabolize (array engine)
  reference.py  the same rules one NPC at a time (the spec and the test oracle)
  population.py every NPC's state as arrays
  keyed.py      keyed randomness: every draw follows from (seed, tick, id, purpose)
  deity.py      prayer, piety, smiting, stale secrets
  clock.py      activity-gated aging
  trials.py     hall-of-fame trials (clone lives before a brain is admitted)
  work.py       occupations: posts, shifts, the fallback walk, wages
  snapshot.py   save/load baseline worlds
  nursery.py    start fresh worlds from a snapshot's best brains
  controllers.py scripted / LLM-controlled NPC hooks
  stats.py      metrics for the roadmap pass criteria (incl. collapse causes)
scripts/        headless runner, multi-seed sweep, dimensions ladder, probes, pygame viewer
tests/          pytest suite (includes the mass-conservation invariant)
docs/           DESIGN.md (all ideas), ROADMAP.md (milestones), SAFETY.md (threat model),
                plan-*.md (feature plans and results), research-tuning.md (what the
                literature says vs. what we measured)
handoff.md      current status; gotchas.md: traps to know before measuring
```

## Status

Milestones 0 to 3 are done: plumbing, survival, diet drives travel (2D, 3D
and 4D), and populations that hold on their own births in 2D, 3D and 4D (they cycle,
boom and bust on stink, rather than settle). `docs/ROADMAP.md` says what
"proof of concept passes" means; the plans in `docs/plan-*.md` have the
results.

Experimental, off by default, and not yet learned by evolution:
- a reaction queue (actions take effect a few ticks after they're chosen) and
  memory slots written by a memory net (`docs/plan-memory-reaction.md`);
- occupations: posts with shifts, a fallback walk for late workers, wages
  (`docs/plan-occupations.md`). Next is training a worker net on its own.

`handoff.md` has the current status.

## License

Copyright (C) 2026 5zorro

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version (`AGPL-3.0-or-later`). See [LICENSE](LICENSE).

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.
