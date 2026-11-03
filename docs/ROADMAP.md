# Roadmap

The proof of concept "passes" when milestones 1 to 5 hold in the Python
prototype without scripting the behaviors directly. Then move toward 4D Miner.

## M0: Plumbing ✅
- N-dimensional world, conserved mass loop, tiny brains, aging, collapse/death,
  prayer and secrets, snapshots, headless runner, 2D viewer, tests.
- Current honest state: random brains collapse a lot and births are rare.
  Evolution happens mostly through hall-of-fame top-ups. That's expected at this stage.

## M1: Survival
**Pass:** collapses per NPC fall over generations; NPCs keep nutrients up
without help. Watch `clpse` and `gen` in the headless table.
Likely work: tune hunger/food numbers, maybe start brains with a mild
"eat when hungry" bias, try more hidden units.

## M2: Diet drives travel
**Pass:** `diet_diversity` stays high *and* NPCs move between food zones
(add a metric: distinct food zones visited per lifetime).

## M3: Stable population from real births
**Pass:** `run_headless.py --until-stable` stabilizes with births > 0 and
few top-ups (`spawn` near 0). The poop-fertilizer loop keeps it from booming
and crashing.

## M4: Trade emerges
**Pass:** gives happen well above the random-brain baseline, and gifts flow
from NPCs with surplus of a food type to NPCs lacking it. Add a reciprocity
metric. Compare against a run where `give` is disabled.

## M5: Secrets spread
**Pass:** prayers get answered (not just smitings), shared secrets get claimed,
and NPCs who learn a secret head toward it.

## M6: Instinct vs. learning
Implement the evolvable tradeoff (cheap decision tree vs. costly learning that
can find secrets). See whether populations settle on a mix.

## M7: Emergent signals and the universal translator
Add signal outputs/inputs, then a translator view (with the comedy patches).

## M8: Claude pawn and Claude deity
Implement `ClaudeController` with a bring-your-own key, plan caching, and
cost limits. Then a deity that answers prayers.

## M9: Finite resources with land memory
Renewable vs. finite items; consumed finite resources convert nearby land into
the inputs to regrow them.

## M10: Godot prototype (optional)
Same rules, nicer visuals, playable deity.

## M11: 4D Miner port
1. C++ brain forward pass + JSON loader, verified against Python outputs.
2. World fields and NPC loop in a 4DModLoader mod, NPCs as simple shapes.
3. Background-thread API calls for Claude features.
4. The 4D body (six eyes, six arms, sign language, rhino head) and directional sound.
5. Ship a baseline snapshot with the mod.
