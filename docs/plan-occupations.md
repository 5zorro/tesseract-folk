# Plan: occupations and a second net switched by the shift (O)

Status: **draft, 2026-11-18.** Nothing built. 5zorro asked for this plan
("yes, write the plan") after the memory work (`plan-memory-reaction.md`)
showed that foraging in today's worlds needs neither memory nor even food
scent.

## Why
5zorro (2026-11-18): "humans have several different nets that are either on
or off depending on the time of day. the foraging brain is not the same as
the 'social complexities' brain. Different ultradian rhythms would
prioritize different nets. not all nets need memory."

The game layer 5zorro has described since 2026-11-03 needs exactly this:
- **Posts must be filled** (a shopkeeper at the shop, a priest at the
  shrine), like Skyrim's choreographed roles.
- **Volunteer first, script as the fallback** (5zorro, 2026-11-03): a forager
  who gets to work on time has a normal shift; one who would be late is
  walked there by the script and arrives **frazzled**.
- **The LLM pawn's main lever is assigning occupations**, with no frazzled
  debuff (2026-11-10), and a manager decides which net is in charge.
  Switches of the net in charge are where barks and reaction animations go.
- **Senses, not memory** (2026-11-11): a smell toward the post and a "ticks
  until late" sense, not a remembered location and time.

Precedent for one net per job, switched by a gate (all from memory): mixtures
of experts (Jacobs, Jordan, Nowlan & Hinton 1991); separate modules stop one
skill overwriting another (Ellefsen, Mouret & Clune 2015); duplicated modules
specialize (Calabretta et al. 2000); the brain's sleep/wake "flip-flop"
switch (Saper et al. 2001); fixed-priority behavior layers (Brooks's
subsumption architecture, 1986).

## Questions this plan answers
1. Can evolution make NPCs punctual when lateness has a real cost, using
   only senses (direction to the post, ticks until the shift)?
2. **One brain or two** (5zorro's MR4 question, now on a real second job):
   the forager with shift inputs added, against a forager plus a worker net
   that the shift switches on. Compare punctuality, foraging (diet,
   collapses), how much the old skill drops while the new one is learned,
   and compute.
3. Does switching nets cost anything (a bad first few ticks after a switch)?
   That window is also where barks and animations play.

## Design (proposed; open points marked)
**The clock.** A day of `day_length` ticks (proposed 300: an NPC lives ~1,500
ticks, so ~5 days a life). The world tick modulo the day is shared time,
5zorro's circadian clock. Later, each NPC can carry its own phase or
ultradian cycles (rest, social); not in the first slices.

**Posts.** A post is a cell with a shift (start tick within the day, length,
proposed a third of a day) and one assigned NPC. Posts are world features
like shrines: placed at world build, saved in snapshots, N-dimensional.
`n_posts` per world (0 = off, the default; fingerprints unchanged).

**Assignment.** At adulthood, an NPC without a post takes a free one
(keyed draw, rule 7). When the holder dies, the post frees up and the next
adult takes it (5zorro's reassignment case). A controller (the LLM pawn) can
assign or move a post at any time; those assignments carry no frazzled
debuff.

**Senses** (one group, after the slots, last; warm starts widen brains):
- on shift now (0/1);
- ticks until the next shift starts, scaled to 0-1 over a day;
- direction to the post (`wrapped_delta / half` per axis) and whether it's
  within reach, like the memory slots' direction;
- frazzled level (0-1).
Open: a real smell field per post (spreads and fades like the pheromone, so
range is limited) or the direct direction above (exact, cheap, any
distance). Proposed: direct first; a smell field only if 5zorro wants posts
that must be found.

**Being on time.** At the shift start, an NPC within reach of its post (its
cell or one step away, the same reach as `share` and mating) is on time. Otherwise the **fallback** takes over:
the code walks it to the post (one step per tick along the shortest wrapped
path; "nets choose, code walks"), its brain's choices are ignored meanwhile,
and it arrives **frazzled**. Rule 6 holds: the script only guarantees the
post is filled; getting there is the brain's choice, and lateness costs.

**Frazzled** (`frazzled_ticks`, `frazzled_*` effects). Proposed effects, all
world rules, none a reward: hunger drains faster (metabolism x 1.5) and the
action draw is noisier (temperature x 2) for `frazzled_ticks` (proposed 100).
Shown to the game as a state for barks and animations.

**On shift.** The NPC must stay within reach of the post until the shift
ends; leaving counts like lateness (the fallback walks it back, frazzled).
What it does there in the first slices: nothing but stay (eat from its hands,
poop if needed). Sandbox duties come later (O4).

**Wages (open, 5zorro decides).** Without a wage, the only cost of lateness
is the frazzled debuff and the lost control. A wage makes work worth
choosing: food paid into the hands at the shift's end for every shift
completed, from a post store filled from soil the way secret caches are
(exact transfers, mass conserved). Proposed: a small wage, so a punctual
worker is a little better fed than a late one. It's a game mechanic for
the job itself, not a reward for an emergent behavior.

**Two nets** (slice O2). The genome gains a worker net (the same shape as the
forager by default) in `Brain`, beside the memory net, with its own mutation
budget. The **switch**: off shift the forager acts; from `lead_ticks`
before the shift until its end the worker net acts (the lead time is when
it should be walking to work). Both nets see the same senses; only the
acting one's output is queued. The forager keeps its recurrent memory
running (like a brain under a controller). Each switch emits an event
(who was in charge, who is now, chosen or forced) for barks.

**Controllers stay above everything:** a controller (LLM pawn, player
script) overrides both nets, as today.

## Next: 5zorro's direction after O1 (2026-11-18, not built)
1. **Don't train foraging while training occupations:** train the worker
   net in its own nursery with the forager frozen (O2's second net, trained
   apart).
2. **A graded goal, not an all-or-nothing wage:** credit for each tick in
   the occupation area, extra for sandbox tasks done (forge, then
   grindstone, then quencher), so training has a ramp.
3. **Mask moves that leave the area during a shift** (invalid-action
   masking): only moves back toward work or along the area's edge are
   available, so being at work is guaranteed and the net learns the
   sandbox queue.
Needs an occupation area of several cells with timed sandbox tiles (O4
moves up), a worker-nursery score (area ticks + tasks), and 5zorro's call
on rule 6 (a designed job's task score vs a reward for emergent behavior).
Details and the AI-LLM's notes in openitems (2026-11-18).

## Known gaps (pre-compaction review, 2026-11-18)
- **`set_rule` skips the work checks:** changing `day_length` or
  `shift_length` mid-run isn't re-validated (shift >= day would mean no
  pay tick), and post shift starts stay where `day_length` put them at
  build. Refuse these in `set_rule` or re-check.
- **No checked way to assign a post from outside:** a controller (the LLM
  pawn, O3) setting `npc.post` out of range would crash at the next work
  phase (IndexError), and nothing re-checks it mid-run (only snapshots
  are checked). Add `assign_post(npc, k)` with checks in O3.
- **Senses written twice:** `work.sense` (reference) and
  `Batch._work_senses` (array) must match; only the engine tests guard it.
- **Per-worker Python loop:** the work phase and the walk build an NPCView
  per worker per tick (`work.tend`). Fine at 10 posts per world (O1 ran 21
  min vs MR2's 25); not measured per tick, and it won't scale to hundreds
  of workers without a vectorized version.
- **`o1_occupations.py` saves its metadata as `mr1.json`** (copied from
  MR2, the same naming gap as there); rename to `meta.json` in all three.
- **Counters are events:** `work_late` includes adults assigned
  mid-shift; `work_left` repeats every wander (gotchas.md).
- **Snapshots on disk:** snapshots/mr1 51 MB, mr2 101 MB, mr2b 104 MB, o1
  67 MB; none pass M2 as saved and all rebuild from their scripts.
  Deleting them is 5zorro's call (standing rule: keep only M2-passing).

## Measures
- Punctuality: share of shifts started on time; fallback walks per shift;
  ticks frazzled per life; leaving the post mid-shift.
- Foraging as in M2 (diet, food types per life, lowest nutrient,
  collapses by cause, births), to see what work costs the forager.
- Switch cost: the action mix in the first Q + 10 ticks after each switch
  against later.
- Compute per tick, one net vs two.
- Compared by nursery, not by scoring seed (MR2's lesson), against a
  no-occupation control trained the same way.

## O0 decisions (5zorro, 2026-11-18: "Use the defaults")
- **Wages: yes, small.** `wage` 0.4 (two bites) of the food rich in the
  worker's lowest nutrient, paid into its hands (up to carry room) at the
  first tick after a clean shift (on time, never walked back), taken from
  the soil like a top-up's body (mass conserved).
- **Direction, not smell:** the post's direction is sensed exactly, at any
  distance.
- **Day 300, shift 100, frazzled 100 ticks;** frazzled = nutrient decay x 1.5
  and action temperature x 2.
- **Who works:** posts are the limit. `n_posts` per world (10 in the O1
  experiment); adults take free posts lowest id first; everyone else is a
  free forager.
- **Built details (O1):** shift starts are spread evenly over the day (post
  i starts at i x day / n_posts); posts are placed by keyed draws (keyed.POST),
  so a world's posts follow from its seed and needn't be saved. The fallback
  walk overrides everything, controllers included (the script takes over), and
  holds the reaction queue at "stay", so nothing stale fires on arrival. A
  worker that collapses mid-shift wakes elsewhere and is walked back.

## Slices
- **O0. Decisions (5zorro):** wages yes or no; direct direction or smell;
  day length, shift length and frazzled effects as proposed or changed;
  which NPCs work (every adult, or a share of them, leaving free foragers).
- **O1. Posts, shifts and the fallback, one brain.** Build the clock, posts,
  assignment, senses, fallback walk, frazzled, wages if chosen; both
  engines, snapshots, tests (mass with wages; 4D; old snapshots load with
  posts off; engines match). Train nurseries from the M2 pools (Q = 3, no
  memory) with posts on. Prediction to be written before the run.
  - **Built (2026-11-18):** `sim/work.py` (shared rules), both engines,
    `Config.n_posts` and friends, work senses last (after queue and slots),
    warm starts widen old brains, 30 tests plus engine cases (2D, 4D with
    queue, mixed batches); fingerprints unchanged. Untrained brains in a
    smoke run leave their post 5-9 times per shift (they wander off as soon
    as they're walked in).
  - **Experiment** (`scripts/o1_occupations.py`): control (no posts) vs posts
    (10 per world), Q = 3, no memory, 3 nursery seeds per M2 pool, 60k
    ticks; scored 5 x 10k: control, **naive** (control brains with posts on,
    work senses at zero weight) and posts. By nursery.
  - **Prediction (AI-LLM, before results):**
    - Naive: on time ~0-5%, leaves several times per shift, paid ~0.
    - Leaving falls most: "stay while on shift and within reach" is one
      conditional, and every leave costs 100 frazzled ticks. Posts arm
      left per shift at most half of naive's in most nurseries.
    - On time rises less (it needs heading out *before* the shift, from the
      time-to-shift sense): 2D 10-30%, 4D 5-15%; paid follows on time.
    - Selection is weak (frazzled costs ~50 ticks of hunger; a wage is two
      bites; 10 of ~40-60 NPCs work), so foraging barely moves: posts vs
      control diet and food types within noise, collapses a little higher
      in most nurseries; births follow bistability as usual.
  - **Results (2026-11-18, 21 min;** `--report-only`**).** Mean over
    nurseries (2D 6, 4D 12); change vs control with nurseries down/up:

    | | 2D naive | 2D posts | 4D naive | 4D posts |
    |---|---|---|---|---|
    | on time (per shift start) | 0.4% | 0.5% | 0.1% | 0.06% |
    | left per shift | 7.1 | 8.0 | 12.7 | 12.5 |
    | walk ticks per shift | 22.7 | 23.8 | 21.6 | 21.4 |
    | paid | 0 | 0 | 0 | 0 |
    | collapses | +0.23 (0/6) | +0.18 (2/4) | +0.002 (1/11) | +0.001 (1/11) |
    | food types per life | -0.001 | -0.009 | -0.11 (12/0) | -0.09 (11/1) |
    | births | -35 (6/0) | -186 (5/1) | -2.5 | -6.7 |

    - **Nothing was learned.** After 60k ticks with posts, workers are as
      unpunctual as brains that never had a job: almost never on time,
      walked in, then off again within a few ticks (the queue holds "stay"
      for Q = 3 ticks after arrival, then the brain wanders), 7-13 times a
      shift; no wage was ever earned. Posts minus naive on time: 0.00 in
      every nursery.
    - **The job costs foraging** (both arms, so from working, not
      training): 4D food types per life -0.1 in 11-12 of 12 nurseries;
      2D collapses up in most nurseries.
    - **2D posts-arm births fell to the top-up floor** (203 -> 17, 5 of 6
      nurseries; population 30); naive only -35. Training with posts left
      most 2D nurseries not breeding. Cause open (workers walked and
      frazzled all shift may rarely mate, so lineages that breed lose out?).
    - **Prediction check:** naive right (on time ~0, leaves several times a
      shift, unpaid). "Leaving falls by half" and "on time 5-30%" **missed**:
      no change at all. "Foraging barely moves" missed in 4D (-0.1 food
      types) and in 2D births.
    - **Reading (not yet tested):** lateness is nearly free to selection.
      The hall of fame ranks lives by collapses (relative to the
      population) and births; frazzled hunger x 1.5 barely moves
      collapses in these lenient worlds (4D +0.001), and a wage of two
      bites never comes. So nothing rewards a punctual brain over a
      wandering one, while working costs foraging for everyone. Next
      probe: measure what a shift costs a worker (collapses, births, lowest
      nutrient, workers vs free foragers in the same worlds), and check a
      hand-built "stay while on shift" controller earns wages and stays
      unfrazzled, before changing any rule (5zorro decides).
- **O2. Two nets.** Add the worker net and the shift switch; same training
  and scoring as O1, paired by nursery. Prediction first.
- **O3. Switch events and controller assignment.** The event stream for
  barks, the LLM pawn's "assign occupation" seam (no frazzled), the
  player-delays-a-worker case from 5zorro's examples.
- **O4. Sandbox duties.** Task tiles at a post that open on timers, first
  come, first served (5zorro, 2026-11-03).
- **Later:** a rest net and fatigue (an ultradian need that builds and
  resets), a social net (kin sense; openitems 2026-11-18), per-NPC phases,
  the manager net choosing among nets instead of a fixed schedule.

## Rules this touches
Both engines (rule 7), fingerprints unchanged with `n_posts = 0`, mass
conservation for wages (rule 1), N-dimensional posts and walks (rule 2), no
outside I/O (rule 8: the LLM pawn stays a controller outside `sim/`), and no
fitness rewards for emergent behavior (rule 6: wages and frazzled are world
rules for the job).
