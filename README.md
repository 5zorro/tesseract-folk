# Tesseract Folk

An artificial-life society prototype: every NPC has a tiny neural net
(like *Creatures*' norns), ages, eats a balanced diet, poops, avoids stink,
prays to an all-knowing deity for secrets, and (hopefully) learns to trade.
Mass is conserved, so the economy comes from a real resource loop:

```
soil -> food -> NPC body -> bowel -> poop (stinks) -> soil
```

The world is N-dimensional. It runs in 2D for prototyping and 4D for the
eventual 4D Miner mod.

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
python scripts/run_headless.py --until-stable --save snapshots/baseline
python scripts/run_headless.py --load snapshots/baseline --ticks 2000
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
  simulation.py tick loop: sense -> think -> act -> metabolize
  deity.py      prayer, piety, smiting, stale secrets
  clock.py      activity-gated aging
  snapshot.py   save/load baseline worlds
  controllers.py scripted / Claude-controlled NPC hooks
  stats.py      metrics for the roadmap pass criteria
scripts/        headless runner and pygame viewer
tests/          pytest suite (includes the mass-conservation invariant)
docs/           DESIGN.md (all ideas), ROADMAP.md (milestones), SAFETY.md (threat model)
```

## Status

Milestone 0 (plumbing) is done. See `docs/ROADMAP.md` for what "proof of
concept passes" means and what comes next.
