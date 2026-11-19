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

## Slices
- **O0. Decisions (5zorro):** wages yes or no; direct direction or smell;
  day length, shift length and frazzled effects as proposed or changed;
  which NPCs work (every adult, or a share of them, leaving free foragers).
- **O1. Posts, shifts and the fallback, one brain.** Build the clock, posts,
  assignment, senses, fallback walk, frazzled, wages if chosen; both
  engines, snapshots, tests (mass with wages; 4D; old snapshots load with
  posts off; engines match). Train nurseries from the M2 pools (Q = 3, no
  memory) with posts on. Prediction to be written before the run.
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
