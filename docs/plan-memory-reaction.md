# Plan: Reaction queue and memory net (2026-11-10)

5zorro (2026-11-10): "i think the next steps is some kind of expansion of both
the memory stack and the reaction time stack and to see how training uses
these." Then 5zorro's design (same day, replacing Claude's first draft):
1. "create the reaction time stack (maybe 3 actions). the stack itself from
   last tick is the inputs to this tick"
2. "create a memory net that manages maybe 8 memories in it. it does not have
   to be a stack. It gets all the inputs of the base forager, but it only has
   ... remember in x (overwriting whatever is there) or forget in x or do
   nothing to the memories."
3. "train those up and get a hall of fame."

The memory net is separate because "im afraid of what would happen if we try
to split the 'move and eat and avoid stink' net to also have another axis to
manage inputs" (catastrophic forgetting: teaching a trained net a new job
wrecks old skills; modular nets forget less, Ellefsen, Mouret & Clune 2015,
from memory). The single-brain version is kept as the comparison (MR4).

A research plan, not a milestone. It feeds M4 (trade needs memories of where
and who) and the game layer (the queue is where the LLM pawn or an
occupation takes over; see "The LLM pawn").

## Settled with 5zorro (2026-11-10)
- **Memory writes are chosen by a memory net,** not automatic. Automatic
  writes on each meal would turn every slot over within 8 meals ("very short
  memories which is less than ideal").
- **Think rate: every tick for now.** Slower thinking for far NPCs waits until
  the sim tick's length in game time is known.
- **Numbers:** 3 queued actions and 8 memory slots. 5zorro called them
  arbitrary; Claude's check:
  - 8 slots is close to the 9 places worth returning to (3 food types x 3
    patches; the rule is enough slots for the distinct targets). Human
    working memory, ~4 items (Cowan 2001), is a different thing: these are
    long-term place memories, and caching birds keep thousands.
  - 3 ticks of delay has no law until a tick has a length in seconds (human
    reaction time ~0.2-0.3 s). Control theory only says the delay must be
    well under the world's response time; crossing a food patch takes ~8
    ticks (radius 4), so 3 is safely under. A delay ladder (MR1) shows the
    curve.
- **Memory net outputs: 17,** not 9: remember in slot x (8), forget slot x
  (8), do nothing (1). Forget lets it clear a patch found empty.
- **Scoring:** M2's top-up worlds first (no boom and bust), births worlds
  second. 2D and 4D first, 3D later.

## Design
**One NPC = one genome with two nets:** the forager (today's brain, with more
inputs) and the memory net. Both are inherited, mutated and crossed over
together; a hall-of-fame entry holds both. They have to evolve together: a
memory net is useless until the forager reads memories, and the other way
round.

**Reaction queue (`Config.reaction_queue` Q, 0 = off, LEGACY 0):**
- A ring of Q pending actions per NPC. Each tick the forager decides an
  action and appends it; the oldest one resolves. So an action takes effect Q
  ticks after it was chosen, on senses Q ticks stale.
- **The forager senses the queue** (5zorro: "the stack itself from last tick
  is the inputs to this tick"): one-hots of the Q pending actions. Biology
  calls this an efference copy (a copy of the motor command, used to predict
  its effect); control theory's Smith predictor (1957) is the same fix for
  dead time. Both from memory.
- A newborn's queue is all "stay". Saved in snapshots. No mass.
- Q = 0 is today's rule exactly (fingerprints unchanged).

**Memory slots (`Config.memory_slots` K, 0 = off, LEGACY 0):**
- Stored per slot: position, tick, and the food amounts there (one per food
  type). Empty or full. Saved in snapshots; no mass.
- **The forager reads them** (it has to, or memories are useless): per slot,
  filled (0/1), direction (`wrapped_delta / half`), freshness
  `exp(-age / memory_tau)`, and the remembered food amounts. 2D: 1+2+1+3 = 7
  per slot; 4D: 9.
- **The memory net writes them.** It gets all of the forager's inputs
  (including the slots and the queue) and picks one of 17 outputs each tick:
  remember here in slot x, forget slot x, or nothing. Its choice resolves at
  once (thinking about memory isn't an action in the world, so no queue).
- **Starting bias:** a random net would write on ~16 of 17 ticks, and every
  slot would hold "here, just now". So a new memory net's "nothing" bias
  starts high enough that writes are ~5% of ticks (`memory_write_bias`).
  Mutation can move it.

**Input sizes** (forager): 2D 47 -> 47 + 3x14 (queue) + 8x7 (slots) = 145;
4D 65 -> 65 + 3x18 + 8x9 = 191. The memory net has the same inputs and 17
outputs. Rule of thumb hidden ~ sqrt(inputs x outputs): ~50-60 for the
forager, so 16 vs 32 hidden is tested (MR2).

**Warm start (Net2Net, Chen et al. 2016, from memory):** the forager starts
from today's hall of fame with zero weights on its new inputs, so it begins
exactly as skilled as now and only learns to use the queue and slots. The
memory net starts random, with the "nothing" bias.

## The LLM pawn (5zorro: a slow model on the player's API key)
5zorro (2026-11-10): an AI model "wants to respond to the inputs, but it is
slow. sometimes taking as many as 12 seconds... The LLM is also better able
to 'see' all the inputs and queue up several hundred queued reactions. Would
that still work with how we are building this? ... it would be cool if it was
compatible from day 1."

**Yes, with three seams built now (cheap) and the model integration later:**
1. **The queue stays Q long; long plans sit above it.** A controller (today's
   `sim.overrides` hook, `sim/controllers.py`) already supplies the action an
   NPC appends each tick instead of its brain. The LLM pawn's 300-step plan
   lives in its controller, which hands over one step per tick; the queue's Q slots
   are still the reflex lag. When the plan runs out before the next reply
   arrives, the controller returns nothing and the NPC's own brain takes
   over: the just-in-time change-out. Built now: a controller may return
   "no action" (falls back to the brain), and may replace the pending queue
   (cancel what the brain queued).
2. **The brain keeps running under a controller.** Its memory net still
   writes, and because the forager senses the queue, a brain taking back
   control sees what was queued for it. Built now: under a controller, the
   forager and memory net still run each tick; only the appended action
   changes.
3. **Replies are inputs, recorded by tick.** A reply that arrives 12 s late
   applies at the next tick boundary, and the tick it applied at is
   recorded, so a replay is exact (rule 7) and snapshots save the pending
   plan. The model call itself stays outside `sim/` (rule 8,
   `docs/SAFETY.md`; the key is never saved).

**Steering by memory, not just actions.** The LLM pawn can also write memory
slots ("there's food at this cell", or later "your post is here, shift in 40
ticks"), and the forager follows memories it was trained to follow. That
steers an NPC without the model choosing every step. Built now: a world-side
`write_memory(npc, slot, pos, food)` that controllers (and later occupations)
can call.

**Settled (5zorro, 2026-11-10): the LLM pawn's main lever is assigning
occupations,** not queuing raw actions. "the llm pawn has most power for
higher level goals when assigning an 'occupation'." An occupation overrides
most of what the forager does: the manager net may switch the forager off and
switch on a net that works through the occupation's sandbox queues while the
NPC is on the clock. Occupations the LLM pawn assigns carry no frazzled
debuff. Raw-action plans (seam 1) stay as the low-level fallback.
What this means for MR1-MR4:
- `write_memory` is the occupation's first interface: a post's location (and
  later its shift time) lands in a memory slot the forager already follows.
- **A switch of the net in charge drains the queue.** The Q actions already
  queued still play out after a switch; that Q-tick window is the natural
  place for the reaction audio and reaction animation 5zorro wants at each
  switch ("the interactions and switches between the neural nets in charge
  are great locations to queue up 'reaction audio' and 'reaction
  animations'").
- **Later (game layer, not MR1-MR4):** the manager net, the occupation duty
  net, the frazzled debuff, and an event emitted on every switch of who is
  in charge (brain, occupation net, LLM pawn, player), which the game turns
  into barks and animations. The examples are in `openitems.md`.

## Measuring (removing the noise)
5zorro (2026-11-09): "If we test, we have to test in a manner that removes the
noise, but that is doable."
- **Paired:** every variant trains on the same nursery seeds and is scored on
  the same world seeds; report each pair's difference and how many pairs
  agree in sign.
- **Metrics:** collapses, diet, food types per life, lowest nutrient,
  approach excess (plan-m2 3c), and speed (us per NPC-tick).
- **Physics tags:** new rules default off; result names carry a tag when one
  is on (`ladder.PHYSICS` pattern).

## Slices
**MR0. Baseline: do brains use today's 2 recurrent units?** Scripts only.
Score trained 2D/4D nursery brains with memory inputs held at 0 vs as trained,
and rank how much each sense group sways the action choice (a "which senses
matter" table). ~10 minutes. Prediction: barely; the senses already point the
way each tick.

**MR0 result (2026-11-10; `scripts/probe_memory.py`, 5 seeds x 10k ticks,
M2 top-up worlds at each dimension's M2 hunger, soil 0.1; `runs/mr0-memory*.txt`,
~7 min).** Paired: memory held at 0 minus trained (seeds agreeing out of 5):
| Nurseries | Collapses | Diet | Food types / life | Lowest nutrient | Births |
|---|---|---|---|---|---|
| 2D n100 | +0.007 (3) | -0.006 (4) | -0.002 (3) | -0.009 (3) | +9 (4) |
| 2D n101 | -0.054 (5) | +0.007 (4) | -0.004 (2) | +0.017 (4) | -53 of 123 (5) |
| 4D M2 n100 | +0.014 (5) | -0.042 (5) | -0.17 (4) | -0.091 (5) | +620 of 254 (5); pop 73 -> 203 |
| 4D M2 n101, n103 | ~0 | -0.006 to -0.008 | -0.02 to -0.03 | ~0 | 0 |
| 4D M2 n102 | ~0 | -0.016 (5) | -0.18 (5) | -0.015 (5) | 0 |
| 4D births n100-103 | +0.001 to +0.011 | -0.001 to -0.010 | -0.03 to +0.05 | ~0 | ~0 of ~1,200 |
- **Used, but little and briefly.** Holding memory at 0 changes foraging by
  less than seed noise in 2D and in 6 of 8 4D nurseries. Two 4D M2 nurseries
  lose ~0.17 food types per life (5/5 and 4/5 seeds). One (n100) uses memory
  to *hold back mating*: cut it and births rise from 254 to ~870 while diet
  and nutrients drop. In 2D n101 it does the opposite (births halve).
- **What memory holds:** mostly a per-NPC set-point (spread between NPCs
  0.19-0.51 vs within an NPC 0.08-0.22, over 30-tick windows) plus a short
  echo of recent senses: within-NPC r 0.3-0.8 at lag 1, ~0.1-0.2 at lag 5,
  gone by 10. Nothing that could hold a place or a heading for long.
- **Senses that sway the choice** (permutation importance, mean change in
  action probabilities): memory ranks 2nd-8th of 20 (0.04-0.16). The
  **shrine sense ranks 1st in 8 of 10 nurseries** (0.10-0.23), then scent
  gradient, body, satiation and moved. Why the shrine matters isn't known:
  a landmark for moving, or just pray/worship near shrines (split the change
  by action to tell; not done).
- **Prediction check:** right for 2D and most of 4D; missed the one 4D
  nursery that uses memory for mating.
- **A probe bug found on the way:** NPC ids repeat across a batch's worlds,
  so following NPCs by id interleaved worlds and faked a 2-tick clock in the
  first readout. Fixed (followed by world and id, with a test); the ablation
  numbers were never affected.
- **Open decision 2 (keep the 2 units?):** ablating them hurts in 2 of 4 4D M2
  nurseries, so by the rule above they stay. The 0/2/8-unit retraining ladder
  was not run: the units hold a few ticks at most, so their count won't change
  the memory net's design. Run it only if 5zorro wants the law.

**MR0b. Clocks and rhythms (5zorro, 2026-11-10).** 5zorro: "humans have a
circadian rhythem, so maybe having a 'rythem' that is a simple modulo 'clock'
in each npc based on tick alone", and "there is two rythems in a human:
circidaian rythem and ultradian rythem. ultradian is like 90 mins".
- **Correction:** the idea first came with a smoke-test finding that the
  2 recurrent units had become a 2-tick clock. That was a probe bug (NPCs
  followed by id, and ids repeat across a batch's worlds, so two worlds'
  values interleaved). Followed correctly, memory decays smoothly (4D: r 0.81
  at lag 1, ~0 by lag 7; 2D slower). No clock evolved. The ideas stand on
  their own merits.
- **Circadian = an outside clock, shared.** Sin and cos of 2pi x tick / day
  (`Config.clock_periods`, empty = off), one phase for the whole world (set by
  the sun). Its job comes with occupations: shifts ("start at hour 9"). Day
  length waits for the sim tick's game-time length (Minecraft's day is
  24,000 game ticks).
- **Ultradian = rhythms the body makes itself.** The ~90-minute
  rest-activity cycle (Kleitman's BRAC; sleep cycles; from memory) comes
  from internal feedback, not a clock. Our NPCs already have such loops:
  hunger, nutrients and the bowel rise and reset, and in 4D the bowel sense
  swings with a period of roughly 15-25 ticks (its correlation turns negative
  by lag 7). The rule-6 way to add one: a *need* (fatigue that builds; rest
  resets it), and the rhythm emerges, rather than a clock input.
- **In net terms: memory on several timescales.** Today's units forget within
  a few ticks. Leaky units with fixed time constants (e.g. 5, 50 and 500
  ticks) give a brain fast and slow memory: the fast ones for steps, the slow
  ones for "where am I in my foraging round". In robots, fast and slow units
  divided the work into motor primitives and their sequencing (Yamashita &
  Tani 2008, multiple-timescale recurrent nets; leaky-integrator nets, Jaeger
  2007; both from memory). A candidate to test against the memory net (MR2).
- **When:** the day clock comes with occupations. Multi-timescale units are
  a cheap MR2 variant (no new action, just different decay per unit).

**MR1. Reaction queue.** **Engine built 2026-11-10** (both engines;
`tests/test_reaction_queue.py`, 3 `test_engines.py` cases; all six
fingerprints unchanged with the queue off):
- `Config.reaction_queue` Q (0-64; LEGACY 0; structural). `npc.queue` holds the
  pending actions oldest first; each tick the decision is appended and the
  oldest resolves. Newborns start with "stay" queued (so Q needs the stay
  action). Sensed as Q one-hots at the very end of the sense vector.
- **Seams for the LLM pawn, built:** a controller returning None leaves the
  brain's choice; the brain (and its memory) runs under a controller too; a
  controller may rewrite `npc.queue` during decide. Controller actions and
  rewritten queues are range-checked; snapshots check queued actions too.
  Not built (lives with the integration, outside `sim/`): recording replies
  by the tick they apply.
- **Warm start:** `Brain.widen` appends zero-weight inputs; `seed_brains`
  widens a pool brain that lacks exactly the queue's inputs, so pre-MR1
  nurseries seed queued worlds and choose exactly as before.
- **Cost:** +13-16% per tick at Q = 3 (2D 2.44 -> 2.84 ms, 4D 3.04 -> 3.43 ms,
  ~180 NPCs; inputs 2D 47 -> 89, 4D 65 -> 119).
- **Behavior change for controllers:** before MR1, an NPC under a controller
  didn't update its recurrent memory; now it does (seam 2). No fingerprint or
  test depends on it.

Still to do in MR1:
- ~~Build Q in both engines, the queue sense, snapshots, LEGACY, seams;
  tests~~ (above).
- **Delay ladder, running 2026-11-10** (`scripts/mr1_ladder.py`): M2
  nurseries (2D n100/101 at 1x, 4D persist n100-103 at 0.36x), Q = 0, 1, 3, 5,
  each scored *as is* (widened brains, so only the delay differs) and
  *trained* (a 20,000-tick warm-start nursery at that Q; trained at Q = 0 is
  the more-training control), 5 seeds x 10,000 ticks in M2's top-up worlds.
- **Prediction (Claude, written before the results):**
  - As is, Q = 1 costs almost nothing. Q = 3 costs a little: 2D collapses
    up ~20-40%, 4D diet down ~0.02 and food types per life down ~0.1 (4D
    hardly collapses at 0.36x, so diet carries the signal). Q = 5 costs about
    twice Q = 3. No cliff before Q ~ 8 (crossing a food core).
  - Why small: a food core is ~8 cells across and food scent points the same
    way for many ticks, so a stale step is usually still a good step. Eating
    is the risk: an eat queued on a food cell lands after the NPC has moved
    on, unless it stays.
  - Trained (20k ticks) wins back about half the as-is loss at Q = 3,
    mostly by learning to stay on food (more "stay" queued after an eat).

**Delay ladder result (2026-11-10; `runs/mr1-ladder.log`, `.json`; 12 min on
16 cores).** Means over nurseries x 5 seeds; change from Q = 0 (pairs
agreeing in sign):
| Arm, Q | 2D collapses | 2D diet | 2D types | 4D diet | 4D types | 4D lowest nutrient |
|---|---|---|---|---|---|---|
| As is, 0 | 0.41 | 0.960 | 2.98 | 0.834 | 2.74 | 0.895 |
| As is, 1 | -0.035 (7/10) | +0.002 | -0.005 | +0.007 (16/20) | -0.011 | +0.008 |
| As is, 3 | -0.011 (5/10) | -0.002 | -0.003 | +0.005 (13/20) | -0.008 | +0.005 |
| As is, 5 | -0.061 (8/10) | +0.000 | +0.006 | +0.001 | -0.021 | -0.002 |
- **A delay of up to 5 ticks costs nothing measurable** for today's brains:
  every foraging change is within seed noise, and collapses even dip
  slightly in 2D. 4D's approach excess is a hair higher at every Q (15-18 of
  20 pairs). Delay is far below the time to cross a food core (~8 ticks),
  which control theory says is the safe zone; the cliff, if any, is past 5.
- **Prediction missed:** Claude expected 2D collapses up 20-40% and 4D
  types down ~0.1 at Q = 3. Measured: nothing. Likely reason (not measured):
  the brains' choices change slowly (keep heading up the scent), so an
  action chosen 5 ticks ago is usually still the right one. Checkable as
  how often an NPC's action equals its action Q ticks earlier.
- **Births and population swing, but not with Q.** They come from the two
  breeding nurseries only, and jump between a floor state and a boom state
  (M3's bistability): as-is 4D n100 has 254, 109, 84, 256 births at
  Q = 0, 1, 3, 5; trained 4D n100 at Q = 0 boomed to the cap (1,288 births,
  pop 250, types 2.00) and trained 2D n101 at Q = 3 boomed (652 births,
  collapses 1.33).
- **The trained arm says nothing yet:** each cell is one 20k-tick nursery,
  so one nursery's evolution (a boom) dominates its cell. The non-breeding
  4D nurseries (n101-n103) score the same at every Q, trained or not.
  Separating training from evolution noise needs several nursery seeds per
  cell.
- **For the game:** a reaction lag of 3 (and up to 5) is free, so the queue
  can be the LLM pawn's and the occupations' handoff point, with its Q-tick
  window for barks and animations, at no cost to survival.
- **Next:** no separate long anneal for Q = 3. The warm-started brains
  already play at Q = 3 as well as at 0, so MR2 starts from today's pools
  with the queue on (widened at load).

**MR2. Memory net.** **Engine built 2026-11-10** (both engines;
`tests/test_memory_slots.py`, 3 `test_engines.py` cases; fingerprints
unchanged with slots off):
- `Config.memory_slots` K (0-64, LEGACY 0), `memory_net_hidden` (8),
  `memory_tau` (500 ticks), `memory_write_start` (0.05). Per NPC: `mem_pos`,
  `mem_tick`, `mem_food` (per type, / food_capacity), `mem_filled`; saved and
  checked in snapshots (cells in the world, whole numbers, finite food).
- **One genome, two nets:** `Brain.memory` is the memory net. Mutation,
  crossover, JSON, hall-of-fame entries and pools carry it; the mutation
  count per child covers both nets' weights. A forager's own mutations are
  the same with or without a memory net (its draws come first).
- **Senses** (after the queue, last): per slot, filled, direction
  (`wrapped_delta / half`), freshness `exp(-age / memory_tau)`, remembered
  food. 2D: 7 per slot; 4D: 9.
- **The memory net** sees the forager's full senses and picks one of 2K + 1
  (remember here in slot k, forget slot k, nothing) with its own keyed draw
  (`keyed.MEMORY`), at the action temperature. It acts at once, before any
  controller, so the LLM pawn's `write_memory(npc, slot, pos, food)` wins.
  Counted as `memory_writes` and `memory_forgets` in the stats.
- **Start bias:** the "nothing" bias is set from `memory_write_start` and the
  action temperature. Measured: 0.05 gives writes or forgets on ~10% of
  ticks (the random weights' spread about doubles it), 0.2 gives ~34%.
- **Warm start:** `seed_brains` widens pool brains lacking the queue and/or
  slot inputs, and gives a brain without a memory net a new random one
  (keyed by pool index, so repeatable).
- **Cost:** Q = 3 with K = 8 (8 hidden) is +50-60% per tick over neither:
  2D 2.47 -> 3.90 ms, 4D 3.00 -> 4.55 ms (~180 NPCs). Genome 2D 1,040 ->
  3,929 weights, 4D 1,396 -> 5,101.

**MR2 experiment (proposed, not run).** MR1 showed one nursery per cell is
swamped by evolution noise, so:
- Two arms, both warm-started from the M2 pools at Q = 3: *control* (K = 0)
  and *memory* (K = 8). Three nursery seeds per pool per arm, paired by
  (pool, seed): 2D 2 pools, 4D 4 pools = 18 pairs.
- Train long enough for a random memory net to matter: 60,000 ticks.
- Score both in M2's top-up worlds (5 seeds x 10k), paired. Usage on the
  memory arm: writes and forgets per 1,000 NPC-ticks, how long a memory
  lives, the follow rate (moves toward a remembered cell holding the needed
  food, against 1 in 2·dims), and the score with slots held empty
  (ablation, like MR0).
- Then the ladders: hidden 16 vs 32, K = 4 vs 8.

- Build slots, the slot senses, the memory net (one genome, two nets:
  mutation, crossover, hall of fame, JSON), `write_memory`, both engines.
- Train: warm-start the MR1 hall of fame, random memory nets, co-evolve.
- Ladders: hidden 16 vs 32; K = 8 vs 4 (is 8 near the law?).
- Usage measures: writes per 1,000 ticks; how long a memory survives; the
  follow rate (share of moves closing distance to a remembered cell holding
  the needed food, against random 1 in 2·dims); the score with slots held
  empty.
- Prediction: writes fall to a few per life, near patch cores; 4D food types
  per life rise; memories live hundreds of ticks.
- Tests: write, forget, overwrite; sense size and contents in 2D/4D; genome
  round trip; old snapshots load with both off; mass unaffected; engines
  match.

**MR3. Hall of fame.** Anneal the winner of MR2 into a saved hall of fame
(2D and 4D), checked against M2's goals, as 5zorro's step 3.

**MR4. One brain vs two** (5zorro's complexity test). The same memory ops as
17 extra outputs of the forager (a second choice head on its hidden layer)
against the separate net. Compare score, how much the old foraging skill
drops while memory is learned, and compute.

**Later:** queues for slower think rates; goal-level model plans; memories
the world writes (occupation posts, shift times, gifts via `share`).

## Open decisions (5zorro)
1. ~~LLM pawn plans~~: settled 2026-11-10, occupations (above).
2. ~~Keep today's 2 recurrent units?~~ MR0 (2026-11-10): keep; ablating
   them hurts in 2 of 4 4D M2 nurseries.
