# Plan: Memory and reaction time (draft, 2026-11-10)

5zorro (2026-11-10): "i think the next steps is some kind of expansion of both
the memory stack and the reaction time stack and to see how training uses
these."

A research plan, not a milestone. It feeds M4 (trade needs memories of where
and who) and the game layer (an action queue is the AI-model pawn's interface;
deciding less often is the far level of detail, `openitems.md`). The question
is **how training uses memory and reaction time**, and the answers wanted are
relationships: score against memory size, against delay, against how often an
NPC thinks, and whether memory makes up for delay.

## What exists today
- **Memory: 2 recurrent units** (`Config.memory_units = 2`). The brain's extra
  outputs go through tanh and come back as inputs next tick
  (`Batch.decide_all`). **Never measured:** no run has ablated or swept them.
- **Memory stack:** designed (plan-m2 slice 4a; `openitems.md`, "Senses,
  memory, trust"), never built.
- **Reaction time:** none. Deciding and resolving are already separate steps
  (plan-gpu-backend, "The seam for 5zorro's reaction-time queue"), but every
  action resolves in the tick it is decided.
- **Think rate:** every NPC decides every tick.
- **History lesson:** actions that need a learned trigger tend not to evolve.
  `share` has never fired, and carried food is never eaten. A `remember`
  action may go the same way, so MR1 measures *writing* memories and *using*
  them separately.

## How we measure (removing the noise)
5zorro (2026-11-09): "If we test, we have to test in a manner that removes the
noise, but that is doable."
- **Paired runs.** Every variant trains nurseries on the same nursery seeds
  and is scored on the same world seeds. Keyed randomness keeps the worlds
  identical until behavior differs. Report each pair's difference and how
  many pairs agree in sign, not only the means.
- **Score in M2's top-up worlds** (`ladder.py --worlds time`). These have no
  boom and bust, so foraging scores aren't drowned by stink cycles. Births
  worlds (`m3_ladder.py`) are a second check only, with windows spanning
  several cycles.
- **Metrics:** collapses, diet, food types per life, lowest nutrient, and the
  move-based approach excess (plan-m2 3c). Each slice adds its own usage
  measures.
- **Dimensions:** 2D (the control) and 4D (where diet was lost; M2's 4D goal is
  0.8). 3D only if an effect shows.
- **Defaults stay off,** so fingerprints don't change and there is no
  re-baseline. Result names get a tag when a new rule is on (`ladder.PHYSICS`
  pattern, gotchas).

## MR0. Does training use today's 2 memory units? (scripts only, no rule change)
- **Ablation:** score trained nursery brains (2D and 4D M2 nurseries, 4D
  births nurseries) with their memory inputs held at 0 every tick, against the
  same brains as trained. The probe wraps `decide_all` the way
  `probe_mating.py` does; nothing in `sim/` changes.
- **Usage:**
  - Memory's lag-1 autocorrelation over a life: does it hold a state, or
    just echo the senses?
  - How much the action probabilities shift when the memory inputs are
    zeroed, ranked against zeroing each other sense group.
  - That ranking doubles as a table of which senses brains actually use.
- **Size ladder:** retrain nurseries at `memory_units` 0, 2 and 8 (16 hidden
  units) and score them paired. Relationship: score against units.
- **Prediction** (Claude, before results):
  - Ablation moves collapses and diet by less than seed noise in 2D, and a
    little in 4D.
  - 0, 2 and 8 units score the same within noise.
  - Reason: nothing in today's worlds rewards history, because the senses
    already point the right way at each tick.
- **Cost:** the probe takes minutes. The ladder (3 sizes x 2 dims x 6
  nurseries) is roughly 1.5-3 h on 16 cores, judging by M2's ~45 min per cell
  set. Time the first cell before launching the rest.

## MR1. The memory stack (plan-m2 slice 4a, extended)
Built as drafted in 4a, plus a second way to write memories:
- **`Config.memory_slots` K** (0 means off, and LEGACY is 0).
  - Stored per slot: position, tick, and a tag (the food richest there, as
    one-hots).
  - Sensed per slot: filled, direction (`wrapped_delta / half`), freshness
    `exp(-age / memory_tau)`, and the tag.
  - That is 7 inputs per slot in 2D and 9 in 4D.
  - No mass is involved. Slots are saved in snapshots.
- **`Config.memory_write`, two variants:**
  - `"action"`: a `remember` output; the brain chooses (the purest form of
    rule 6).
  - `"meal"`: the world writes a slot on each eat that takes a real bite (at
    least half of a full one). This is an instinct, like the eat action's
    food choice today.
  - Comparing them separates "can brains use memories" (meal) from "will
    they learn to write them" (action).
- **Eviction:** the oldest slot goes. A write at a cell already remembered
  refreshes that slot instead, so one patch can't fill every slot.
- **Brain size:** 16 vs 32 hidden units with memory on, since 4 slots grow the
  inputs by about half.
- **Measure:** a K ladder of 0, 1, 2, 4 and 8, for each write mode, in 2D and
  4D, paired. Usage measures:
  - how often `remember` fires;
  - the follow rate: the share of moves that close distance to the freshest
    slot holding the needed food, against random (1 in 2·dims);
  - returns to remembered cells;
  - the score with the stack's senses held at 0.
- **Prediction:**
  - `"meal"` raises 4D food types per life by 0.2 or more, with moves toward
    memories above random.
  - `"action"`: `remember` fires on under 1% of ticks, and its score matches
    no stack.
  - The score against K levels off by 2-4 slots (3 food types).
- **Tests:**
  - stack order, refresh and eviction;
  - the sense size and contents in 2D and 4D;
  - snapshot round trip;
  - old snapshots load with the stack off;
  - mass unaffected;
  - the two engines match exactly (`test_engines.py` case).

## MR2. Reaction time and think rate
Uses the existing decide/resolve seam. Three rules, all off by default:
- **`reaction_delay` k:**
  - An action decided now resolves k ticks later, through a ring buffer of k
    actions per NPC.
  - A newborn's queue starts as "stay".
  - The senses an action was chosen on are k ticks stale when it happens.
- **`think_interval` k:**
  - Each NPC decides every k ticks and repeats its last action in between.
  - The phase is staggered by a keyed draw per NPC, so not everyone thinks on
    the same tick.
  - This is the far level of detail from the performance notes. It also saves
    (1 − 1/k) of brain time, so measure the speed too: that number is for the
    game.
- **`think_jitter`:**
  - k is redrawn at each decision from keyed randomness in [1, k].
  - This is the "train with random think intervals" idea: if the game will
    use level of detail, brains should be trained to tolerate it.
- **Measure:**
  - Delay ladder k = 0, 1, 2, 4, 8; think-interval ladder 1, 2, 4, 8.
  - Two regimes: trained at k, and trained at 0 then scored at k
    (tolerance).
  - Relationship: score against k ÷ (ticks to walk through a food core).
  - Then a 2x2: delay {0, 4} × memory {2 units, stack}. Does memory make up
    for lag?
- **Prediction:**
  - Delays of 1-2 cost little, because a move is small next to a food core.
  - The score bends down once k nears the ticks to cross a core.
  - Brains trained at 0 tolerate a think interval of 2 but not 8.
  - Recurrent units help a little under delay (they can carry "I was moving
    +x"); the stack doesn't.
- **Tests:**
  - delay 0 and interval 1 equal today's rules exactly (fingerprints
    unchanged);
  - queue order;
  - the snapshot round trip keeps the queue;
  - newborns' queues;
  - results don't depend on NPC order (rule 7);
  - the two engines match exactly.

## MR3. Later (design only)
- **An action stack the brain fills ahead:** a plan of L actions per thought
  (L × the action outputs), or a controller (the AI-model pawn) filling the
  queue. Waits for MR2's results and the game-layer design.
- **Memories the world writes:** an occupation's post and shift time
  ("a smell with a timestamp"), gifts via `share` into an inbox slot, and
  entity ids. These come with M4, M5 and occupations.

## Order
MR0 → MR1 → MR2, run as a ladder, carrying on unless a result says stop:
- MR0 is cheap and says whether memory limits brains at all today.
- MR1 is the bigger build.
- MR2 is small code on an existing seam.
- If MR0 shows today's units already matter in 4D, MR1's K ladder includes
  "units only" as its baseline.

## Open decisions (5zorro)
1. **Write mode for MR1:** both variants (recommended), or `"action"` only to
   stay strictly with rule 6?
2. **Think jitter in MR2:** train level-of-detail tolerance now (cheap), or
   leave it for the game layer?
3. **Scoring worlds:** M2 top-up worlds first, births worlds second
   (recommended)?
4. **Dimensions:** 2D and 4D first, 3D later?
