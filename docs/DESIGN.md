# Tesseract Folk: Design Document

A living society for a 4D voxel game, where every NPC has a tiny neural net
(like the norns in *Creatures*), ages, eats, poops, prays, trades, and gossips,
and where an economy emerges from a conserved flow of matter instead of
hand-tuned prices.

Status markers: **[built]** exists in the Python prototype, **[partial]** has a
stub or simplified version, **[idea]** is design only.

---

## 1. Core pillars

1. **Every NPC has a tiny brain.** A small neural net (hundreds of weights, not
   millions) maps senses to actions. Behavior is learned and evolved, not scripted.
2. **Entropy drives everything.** Hunger, boredom, waste, and stink push NPCs to
   move, mix, and interact. Standing still is never a stable strategy.
3. **Mass is conserved.** Nothing is created or destroyed; it only changes form.
   Scarcity and trade come from that.
4. **Death is gradual.** Young NPCs can't die permanently; only elders can.
5. **The world runs without the player,** but time (aging) respects the player.

## 2. Prior art (for reference, not imitation)

- *Creatures* (norns): tiny neural brains, raising creatures.
- *The Bibites*: evolving neural-net creatures in a conserved energy/matter ecosystem.
- *Polyworld*, *Species: ALRE*: neural/genetic ecosystem sims.
- Steve Grand's *Grandroids / Frapton Gurney*: richer creature brains; a lesson in scope.
- *Dwarf Fortress*, *Kenshi*, *Shadows of Doubt*: persistent simulated NPCs (scripted).
- *X4: Foundations*: NPC-driven physical economy.
- *Shadow of Mordor* Nemesis system: enemies return after "death."
- *Black & White*, *Populous*: player as deity.
- *RimWorld*: pawns with needs, filth, moods, religion (Ideology DLC).

Closest current projects (checked 2026-11-02):
- **Skyrim AI-NPC mods: Mantella, CHIM (with MinAI), SkyrimNet.** Large AI models
  give NPCs conversation, memory and a few triggered actions (follow, attack).
  They're dialogue-first and nothing evolves. *Immersive Citizens* improves
  schedules with hand-made rules.
- **Project Sid** (Altera, 2024): up to 1,000 large-AI-model agents in Minecraft
  formed roles, an economy, taxes and a religion. That's research, with one
  costly model call per agent decision. Also Stanford's "Generative Agents" (2023).
- **4D Miner:** a modding framework exists (see §13), with block and item mods,
  but no NPC or society mods were found.

What's new here: learned brains across a whole society + aging-gated death +
an economy emerging from a thermodynamic resource loop.

## 3. NPC brains

- **[built]** Feedforward net, one hidden layer (default 16 units, tanh), plus 2
  recurrent memory units fed back as inputs. ~900 weights in 2D, ~1,100 in 4D.
- **[built]** Plain arrays, JSON-serializable, no ML framework, so a C++ port is trivial.
- **[built]** Neuroevolution: children get crossed-over, mutated parent weights.
- **[built]** Hall of fame: if population falls below a minimum, spawn mutated
  copies of the best brains seen. Fitness = offspring and lifetime, minus collapses.
  Deliberately does *not* reward trading directly; trade should emerge.
- **[idea]** Lifetime learning (Hebbian or reward-modulated) on top of inherited weights.
- **[partial] Instinct vs. learning.** Some behaviors can run on hard-coded
  decision trees (genetic or scripted). Instincts cost less compute and less
  hunger, but only learning can discover hidden secrets. `ScriptedController`
  in `sim/controllers.py` is the starting point. A gene could set how much an
  NPC relies on instinct, making it an evolvable tradeoff.

### Senses (inputs)
Nutrients, health, age, body mass, bowel fullness, per-food satiation, food here,
food gradient per axis, stink here and gradient, nearby NPC count, inventory,
piety, smite, known-secret direction, nearest-shrine direction, moved-last-tick,
memory, bias, and food scent per type (level here and which way it's stronger).
Input size scales with dimensions automatically.

- **[built] Food scent** (`Config.food_scent`): each food type has a smell that
  spreads farther than stink, so an NPC short on a nutrient can follow the smell
  of the food that has it. The brain gets raw scents; linking them to its own
  deficits is left to evolution.
- **[built, off by default] Meal scent** (`Config.scent_min_food`): only food
  beyond a set amount smells, so crumbs are silent. Tested alone in M2 slice 3f
  with no effect; meant to pair with brain-chosen eating.
- **[idea] Two eat actions** (5zorro, 2026-11-04): `eat_most` (biggest bite) and
  `eat_need` (best for deficits), so the brain, not an instinct, chooses.

### Actions (outputs)
Move ± along each axis (4 in 2D, 8 in 4D), stay, eat, pick up, give, poop,
mate, pray, worship, share (a secret).

## 4. Aging, time, and death

- **[built] Activity-gated aging.** Age only advances while the player is
  active (not AFK), or when the player deliberately **turns the clock**
  (fast-forward). Gives the player a godlike "skip a generation" power.
- **[built] Open question as a config flag:** `freeze_all_when_afk`. False means
  only aging pauses (NPCs keep living daily life); true freezes everything.
- **[built] Young NPCs collapse instead of dying.** They drop what they carry,
  wake up elsewhere, and suffer an age penalty. Bad brains age out fast; that is
  the selection pressure.
- **[built] Elders die permanently.** Health declines past `old_age`. The body
  becomes poop (stinks, then fertilizes), returning its mass to the loop.

## 5. Entropy and the economy

- **[built] Hunger with nutrients.** Each food type is rich in one nutrient.
  NPCs track deficits, so they need a balanced diet, which pulls goods across regions.
- **[built] Same-food penalty.** Satiation per food type reduces how much
  nutrition repeat meals give.
- **[built] Idle penalty.** Doing nothing beyond a grace period makes hunger rise
  faster. Moving, or an action that changes something (eating, giving, a birth…),
  counts as busy (`busy_resets_idle`, 5zorro 2026-11-02).
- **[built] Food zones.** Each food type grows only in its own patches (no thin
  layer everywhere since 2026-11-02), and food scent leads NPCs to them. The
  world keeps a zone map (patch cores) so travel between zones can be measured
  (M2). In 4D at size 10, use `food_patch_radius=2.0`, or patches cover everything.
  Patches are Gaussians, so their thin edges grow crumbs almost everywhere; in
  higher dimensions most of a patch is edge (M2 slice 3f). `food_layout=shared`
  (a measurement control) grows every food in the same patches.
- **[idea] Biomes:** named, separated zones (food 1 in "mountains", food 2 on
  "beaches"), readable to players and matching 4D Miner's own biomes.
- **[built] Poop and stink.** Digestion fills the bowel; pooping (or an
  "accident") drops waste that emits stink. Stink diffuses, fades, and hurts above
  a threshold, so NPCs learn to move away from it.
- **[built] Poop becomes fertilizer.** Poop decomposes into soil, and food grows
  from soil. Farming near the smell is a real tradeoff.
- **[built] Give action** as the seed of trade. **[idea]** Explicit exchange,
  reciprocity memory, and prices emerging from scarcity.

## 6. Conservation of mass

- **[built]** Total mass across soil, food, poop, secret caches, and NPC
  bodies, bowels, and inventories is constant. Tests enforce this.
- **[idea] Renewable vs. finite items.** Items are either renewable (generated)
  or finite.
- **[idea] Real estate remembers.** When a finite resource is consumed, its block
  of land remembers what was there and converts nearby renewable block(s) into the
  resources needed to eventually produce that finite resource again. Finite things
  become slow, location-bound cycles instead of permanent losses.

## 7. The deity, prayer, and secrets

- **[built] Secrets** are hidden food caches pulled from the soil. They **go
  stale**: unclaimed secrets dissolve back into soil after a while.
- **[built] Prayer** reveals the nearest secret's direction to the NPC. It
  requires both **piety** (above a threshold) and a low **"not smited" score**
  (smite below a threshold), plus a cooldown.
- **[built] Smiting.** Praying while unqualified (including spamming) raises the
  smite score; crossing the threshold damages health. Smite decays over time.
  **Off by default for now** (`Config.smiting = False`, since 2026-11-02): with
  random brains it caused ~70% of collapses and hid the hunger problem. It comes
  back once a snapshot survives on hunger alone.
- **[built] Worship** at shrines raises piety (costs time and travel).
- **[built] Share** passes a known secret to nearby NPCs, so information spreads
  and can become an economic good.
- **[idea]** Sacrifices (offering food for piety), lying about secrets,
  information brokers emerging, deity "moods."
- **[idea]** The smite trigger is effectively the society's moral code. Choose it
  deliberately.

## 8. Claude-powered NPCs and deity (bring your own API key)

Safety rules for everything in this section (no tools beyond in-game actions,
validated replies, key handling, spending caps): `docs/SAFETY.md` §5.

- **[partial]** `ClaudeController` stub and `describe_observation()` in
  `sim/controllers.py`; `sim.overrides[npc_id]` lets any controller drive one NPC.
- The Claude pawn gets the same senses and actions as everyone else (fair
  comparison with tiny brains), replies with one action as JSON.
- Call the API at decision points and cache a plan; don't call every tick.
- Key lives in an environment variable or local config; never in snapshots.
- In C++, make HTTP calls on a background thread.
- **[idea]** A Claude-powered deity that answers prayers in character, hints at
  secrets, and decides smitings. Speaks rarely, so cost stays low.

## 9. Emergent communication and the universal translator

- **[idea]** NPCs develop their own signaling ("AI speak"), e.g. a small set of
  output channels others can sense, shaped by evolution.
- **[idea]** A **universal translator** maps learned signals to English (or any
  language) for the player, e.g. by correlating signals with the sender's state
  and subsequent actions, optionally phrased by an LLM.
- **[idea]** Translator patches for comedy: **"sales floor jargon"** and
  **"passive aggressive."**

## 10. The 4D body

- **[idea]** Six eyes and six arms: 2 facing the front dimension, 2 facing the
  back dimension, and 2 half-and-half so only the hands are visible from the front.
- **[idea]** The two front-facing hands are always doing sign language (a natural
  visual output for emergent communication).
- **[idea]** Rhino-shaped head with horns in the back dimension.

## 11. Sound

- **[idea]** Voice timbre varies with the dimensional direction it comes from.
- **[idea]** Generated with xVASynth, or by layering default sound assets.
  Caution: xVASynth imitates real voice actors, who have objected to AI copies
  of their voices. Don't clone a real voice without consent (`docs/SAFETY.md` §7).

## 12. Baseline snapshot

Infinitely configurable worlds tend to end up samey and are expensive to
re-derive. So:

- **[built]** Run the world without players until the population stabilizes
  (`run_headless.py --until-stable --save snapshots/baseline`).
- **[built]** Save it as a snapshot; new players boot from that snapshot.
  Snapshots resume deterministically.
- **[built] Nursery** (`sim/nursery.py`): brains evolve offline under harsh rules
  (deaths drive selection), then fresh worlds under the gentle play rules start
  from the best of them (`run_headless.py --brains-from`). Pretrained brains
  generalize to new maps, collapse ~28% less, and raise births ~7× (M1 plan,
  slice 4b). The shipped baseline should come from the nursery.
- **[idea]** Keep play worlds from drifting: in gentle worlds, generations
  slowly lose the nursery's advantage. Re-seed periodically, mutate less in
  play, or keep mild selection.

## 13. Porting to 4D Miner

- 4D Miner has an unofficial community modding framework: **4DModLoader** with
  C++ headers (`4dm.h`), from the 4D-Modding GitHub organization.
- The prototype is N-dimensional, so 4D rules can be tested in Python first
  (`--dims 4`).
- **Two kinds of movers** (5zorro, 2026-11-04): land walkers can't fly, so they
  live on 3D surfaces (`--dims 3`); 4D fish and birds move freely in 4D. Both
  have to work, so M2 is judged in 3D and in 4D.
- Port order: brain forward pass and JSON loading, then world fields, then NPC
  loop, then rendering and the 4D body.
- Risks: the framework is reverse-engineered (game updates can break mods),
  4D pathfinding and rendering are hard, and almost all NPC systems are new.

## 14. Open questions

- Should hunger and poop also pause while the player is AFK?
- What exactly triggers smiting (the society's moral code)?
- How should trade be represented beyond gifts: barter, reciprocity, currency?
- How much should NPCs rely on instinct vs. learning by default?
- What signals make up "AI speak," and how does the translator learn them?
