"""The reference engine: the tick rules written one NPC at a time.

This is G1 of docs/plan-gpu-backend.md, kept as the readable spec of the
rules (and of the C++ port) and as the test oracle for the array engine in
simulation.py: tests/test_engines.py runs both and expects identical worlds.
Any rule change goes into both. Nothing outside the tests runs it.

The tick loop: senses -> tiny brain -> action -> metabolism.

The tick rules (docs/plan-gpu-backend.md, G1): every NPC senses the world as it
was at the start of the tick and decides; then the chosen actions resolve in
fixed phases (moves; eats and pick-ups; give, mate, share; the rest), then
everyone's metabolism, then deaths and collapses. Within a phase NPCs go in priority order, a fresh keyed draw each
tick (lowest first). All randomness is keyed (sim/keyed.py).

Invariant: total mass (soil + food + poop + secret caches + everything NPCs
carry in body, bowel and inventory) never changes. tests/test_simulation.py
checks this. If you add a mechanic, keep it true.
"""
from __future__ import annotations

import numpy as np

from .brain import Brain
from .clock import SimClock
from .config import Config
from . import keyed
from .deity import Deity
from .npc import NPC, build_actions
from .stats import Stats
from .world import World, wrapped_delta


# Rule 2's phases, in the order they resolve. "stay" and anything unlisted go last.
N_PHASES = 4
SOCIAL_PHASE = 2
_PHASES = {"eat": 1, "eat_need": 1, "eat_most": 1, "pick_up": 1,
           "give": SOCIAL_PHASE, "mate": SOCIAL_PHASE, "share": SOCIAL_PHASE}


def action_phase(name: str) -> int:
    return 0 if name.startswith("move") else _PHASES.get(name, 3)


class ReferenceSimulation:
    def __init__(self, cfg: Config | None = None, populate: bool = True, log_every: int = 100):
        self.cfg = cfg or Config()
        # The world is built from one NumPy stream (so maps match those before
        # keyed randomness); every draw after that is keyed.
        self.world = World(self.cfg, np.random.default_rng(self.cfg.seed))
        self.keys = keyed.Keys(self.cfg.seed)
        self.deity = Deity(self.cfg)
        self.clock = SimClock()
        self.stats = Stats(log_every)
        self.actions = build_actions(self.cfg.dims, self.cfg.two_eat_actions)
        self.n_actions = len(self.actions)
        self._phase = [action_phase(a) for a in self.actions]
        self.n_inputs = self.sensor_size()
        self.n_outputs = self.n_actions + self.cfg.memory_units
        c = self.cfg
        if not (np.isfinite(c.mutations_per_birth) and c.mutations_per_birth >= 0):
            raise ValueError(f"mutations_per_birth must be a number >= 0, got {c.mutations_per_birth!r}")
        if not (np.isfinite(c.action_temperature) and c.action_temperature > 0):
            raise ValueError(f"action_temperature must be a number > 0, got {c.action_temperature!r}")
        if c.hall_of_fame_min_copies < 0:
            raise ValueError(f"hall_of_fame_min_copies must be >= 0, got {c.hall_of_fame_min_copies!r}")
        if c.mutation_lineage and not c.mutations_per_birth > 0:
            raise ValueError("mutation_lineage needs mutations_per_birth > 0 (its base count)")
        if not (np.isfinite(c.hall_of_fame_prior_lives) and c.hall_of_fame_prior_lives >= 0):
            raise ValueError(f"hall_of_fame_prior_lives must be a number >= 0, got {c.hall_of_fame_prior_lives!r}")
        if not (np.isfinite(c.mutation_lineage_max) and c.mutation_lineage_max >= 1):
            raise ValueError(f"mutation_lineage_max must be a number >= 1, got {c.mutation_lineage_max!r}")
        self._shrine_cache: dict = {}
        self._shrines_cached: list = []
        self.npcs: list[NPC] = []
        self.hall_of_fame: list[dict] = []   # see nursery.hall_of_fame_entry for the fields
        self.overrides: dict[int, object] = {}  # npc id -> controller (see controllers.py)
        self.tick = 0
        self.next_id = 0
        if populate:
            for _ in range(self.cfg.initial_npcs):
                draw = self.keys.stream(0, self.next_id, keyed.INIT)
                self._spawn(self._random_brain(draw), self.world.random_cell(draw),
                            self.cfg.npc_start_mass, generation=0)

    # ============================================================ public API
    def step(self) -> bool:
        """Advance one tick. Returns False if time is frozen (player AFK)."""
        cfg = self.cfg
        if cfg.freeze_all_when_afk and not self.clock.aging_active:
            return False
        aging = self.clock.aging_active
        self.tick += 1
        self.world.step()
        self.deity.step(self.tick, self.world, self.keys, self.stats)

        order = self._priority_order()
        chosen = self.decide_all(order, self._spatial_index())
        births: list[NPC] = []
        self.resolve(order, chosen, births)
        self.metabolize(order, aging)

        self.npcs = [n for n in self.npcs if n.alive] + births
        self._top_up()
        self.clock.consume_tick()
        self.stats.maybe_sample(self)
        return True

    def run(self, ticks: int) -> None:
        for _ in range(ticks):
            self.step()

    def fast_forward(self, ticks: int) -> None:
        """The player turns the clock: run with aging forced on."""
        self.clock.turn(ticks)
        self.run(ticks)

    def total_mass(self) -> float:
        carried = sum(n.body + n.bowel + float(n.inventory.sum()) for n in self.npcs)
        return self.world.mass() + self.deity.mass() + carried

    def is_stable(self) -> bool:
        return not self.stability_problems()

    def stability_problems(self) -> list[str]:
        """Why the population hasn't settled yet (an empty list means stable).

        Stable means low population variation over the last `stable_window`
        samples, sustained by real births. A population held on the
        `min_population` floor by hall-of-fame top-ups has zero variation, so
        it must not count (see gotchas.md).
        """
        c = self.cfg
        hist = self.stats.history[-c.stable_window:]
        if len(hist) < c.stable_window:
            return [f"only {len(hist)} of {c.stable_window} samples so far"]
        pops = np.array([h["population"] for h in hist], dtype=float)
        if pops.mean() == 0:
            return ["population is extinct"]
        problems = []
        cv = pops.std() / pops.mean()
        if cv >= c.stable_max_cv:
            problems.append(f"population varies too much (cv {cv:.2f} >= {c.stable_max_cv})")
        births = sum(h["births"] for h in hist)
        spawns = sum(h["spawns"] for h in hist)
        if births == 0:
            problems.append("no births")
        if spawns > c.stable_max_spawn_fraction * births:
            problems.append(f"too many top-ups ({spawns} spawns vs {births} births; "
                            f"allowed {c.stable_max_spawn_fraction} per birth)")
        if pops.mean() <= c.min_population:
            problems.append(f"population sits on the top-up floor "
                            f"(mean {pops.mean():.1f} <= min_population {c.min_population})")
        return problems

    # =============================================================== senses
    def sensor_size(self) -> int:
        c = self.cfg
        t, n, d, m = c.n_food_types, c.n_nutrients, c.dims, c.memory_units
        scent = t + d * t if c.food_scent else 0
        return (n + 4 + t + t + d * t + 1 + d + 1 + t + 2
                + 1 + d + d + 1 + 1 + m + 1 + scent)

    def sense(self, npc: NPC, index: dict) -> np.ndarray:
        cfg, w, p = self.cfg, self.world, npc.pos
        half = cfg.size / 2
        # Every neighbor at once: columns are +1, -1 along axis 0, then axis 1...
        # Gradients come out axis by axis, each holding every food type.
        nbr = w.flat_neighbors(p)
        types = w.food.shape[0]
        food_n = w.food.reshape(types, -1)[:, nbr]
        food_grad = ((food_n[:, 0::2] - food_n[:, 1::2]) / cfg.food_capacity).T.ravel()
        stink_n = w.stink.reshape(-1)[nbr]
        stink_grad = stink_n[0::2] - stink_n[1::2]

        secret = self.deity.secrets.get(npc.known_secret) if npc.known_secret is not None else None
        if secret is None:
            npc.known_secret = None
            secret_part = np.zeros(1 + cfg.dims)
        else:
            secret_part = np.concatenate([[1.0], wrapped_delta(p, secret.pos, cfg.size) / half])

        parts = [
            npc.nutrients,
            [npc.health, min(npc.age / cfg.old_age, 1.5),
             npc.body / cfg.npc_start_mass, npc.bowel / cfg.bowel_capacity],
            npc.satiation,
            w.food_at(p) / cfg.food_capacity,
            food_grad,
            [w.stink[p]],
            stink_grad,
            [min(len(self._neighbors(npc, index)) / 4.0, 1.0)],
            npc.inventory / cfg.carry_capacity,
            [npc.piety, npc.smite],
            secret_part,
            self._shrine_sense(p),
            [1.0 if npc.moved_last else 0.0],
            npc.memory,
            [1.0],
        ]
        if cfg.food_scent:
            here = w.scent_at(p)
            scent_n = w.scent.reshape(types, -1)[:, nbr]
            s_plus, s_minus = scent_n[:, 0::2], scent_n[:, 1::2]
            # Relative difference: points uphill at any distance, like a nose.
            parts += [here / (here + cfg.scent_half),
                      ((s_plus - s_minus) / (s_plus + s_minus + 1e-12)).T.ravel()]
        obs = np.concatenate(parts, dtype=float)
        assert obs.size == self.n_inputs, (obs.size, self.n_inputs)
        return obs

    def _shrine_sense(self, p) -> np.ndarray:
        """Direction to the nearest shrine and whether the NPC is on one. Shrines
        don't move, so it's cached per cell (rebuilt if the shrines change)."""
        w, cfg = self.world, self.cfg
        if self._shrines_cached != w.shrines:
            self._shrine_cache, self._shrines_cached = {}, list(w.shrines)
        part = self._shrine_cache.get(p)
        if part is None:
            part = np.zeros(cfg.dims + 1)
            if w.shrines:
                deltas = [wrapped_delta(p, s, cfg.size) for s in w.shrines]
                nearest = min(deltas, key=lambda d: np.abs(d).sum())
                part = np.concatenate([nearest / (cfg.size / 2), [1.0 if not nearest.any() else 0.0]])
            self._shrine_cache[p] = part
        return part

    # ============================================================== thinking
    def _priority_order(self) -> list[NPC]:
        """The living NPCs, lowest priority draw first (ties, practically never,
        by id). Every phase of the tick goes in this order."""
        npcs = [n for n in self.npcs if n.alive]
        if not npcs:
            return []
        ids = np.array([n.id for n in npcs])
        prio = self.keys.uniform(self.tick, ids, keyed.ORDER)
        return [npcs[i] for i in np.lexsort((ids, prio))]

    def decide_all(self, order: list[NPC], index: dict) -> list[int]:
        """Rule 1: everyone senses the start-of-tick world and picks an action.
        Deciding changes only the NPC's own memory, so the order doesn't matter.
        (5zorro's reaction-time queue would hand `resolve` actions decided
        earlier instead; docs/plan-gpu-backend.md.)"""
        if not order:
            return []
        draws = self.keys.uniform(self.tick, [n.id for n in order], keyed.ACTION)
        return [self._decide(npc, self.sense(npc, index), float(u)) for npc, u in zip(order, draws)]

    def resolve(self, order: list[NPC], chosen: list[int], births: list[NPC]) -> None:
        """Rules 2-3: actions take effect phase by phase, in priority order. Social
        actions see where everyone is after the moves."""
        index = None
        for phase in range(N_PHASES):
            if phase == SOCIAL_PHASE:
                index = self._spatial_index()
            for npc, action in zip(order, chosen):
                if self._phase[action] == phase:
                    self._act(npc, action, index, births)

    def _decide(self, npc: NPC, obs: np.ndarray, u: float) -> int:
        """`u` is this NPC's keyed uniform draw for the tick (keyed.ACTION)."""
        controller = self.overrides.get(npc.id)
        if controller is not None:
            return controller.decide(self, npc, obs)
        out = npc.brain.forward(obs)
        npc.memory = np.tanh(out[self.n_actions:])
        logits = out[: self.n_actions] / self.cfg.action_temperature
        logits -= logits.max()
        probs = np.exp(logits)
        probs /= probs.sum()
        # The way NumPy's rng.choice(p=probs) samples (one uniform draw against the
        # cumulative sum), with the NPC's keyed draw `u`.
        cdf = probs.cumsum()
        cdf /= cdf[-1]
        return int(cdf.searchsorted(u, side="right"))

    # =============================================================== actions
    def _act(self, npc: NPC, action: int, index: dict | None, births: list[NPC]) -> None:
        name = self.actions[action]
        moved = did = False          # did: the action changed something (not just tried)
        if name.startswith("move"):
            sign = 1 if name[4] == "+" else -1
            before = npc.pos
            npc.pos = self.world.neighbor(npc.pos, int(name[5:]), sign)
            moved = True
            self._record_approach(npc, before)
            claimed = self.deity.claim_at(npc.pos, self.world)
            if claimed:
                self.stats.count("secrets_claimed", claimed)
        elif name in ("eat", "eat_need"):
            did = self._eat(npc, "need")
        elif name == "eat_most":
            did = self._eat(npc, "most")
        elif name == "pick_up":
            did = self._pick_up(npc)
        elif name == "give":
            did = self._give(npc, index)
        elif name == "poop":
            if npc.bowel > 1e-9:
                self.world.poop[npc.pos] += npc.bowel
                npc.bowel = 0.0
                self.stats.count("poops")
                did = True
        elif name == "mate":
            did = self._mate(npc, index, births)
        elif name == "pray":
            result = self.deity.pray(npc, self.tick)
            self.stats.count({"answered": "prayers_answered", "silent": "prayers_silent",
                              "ignored": "prayers_ignored", "smitten": "smitings"}[result])
            did = result == "answered"
        elif name == "worship":
            if npc.pos in self.world.shrines:
                npc.piety = min(1.0, npc.piety + self.cfg.worship_piety_gain)
                self.stats.count("worships")
                did = True
        elif name == "share":
            did = self._share(npc, index)
        # "stay" does nothing on purpose.
        npc.moved_last = moved
        busy = moved or (did and self.cfg.busy_resets_idle)
        npc.idle_streak = 0 if busy else npc.idle_streak + 1

    def _record_approach(self, npc: NPC, before) -> None:
        """M2 slice 3c: did this move head for the food the NPC needs most, more
        than for the others? Moves only, so the eat instinct can't leak in."""
        w = self.world
        need = int(np.argmin(npc.nutrients))
        if w.serves(before)[need]:
            return                         # already where its food grows
        dist = w.need_distance
        here = dist[(slice(None),) + before]
        others = np.isfinite(here)
        others[need] = False
        if not np.isfinite(here[need]) or not others.any():
            return
        # Score the move taken, then every possible step from the same cell. Their
        # mean is what a random step scores. Not 0: a random walk drifts away from
        # near food faster than from far food (gotchas.md).
        cells = tuple(np.array([npc.pos] + w.adjacent(before)).T)
        delta = dist[(slice(None),) + cells] - here[:, None]          # (nutrients, steps)
        # sum / count is what np.mean computes, without its per-call overhead.
        score = delta[others].sum(axis=0) / others.sum() - delta[need]
        npc.approach_sum += float(score[0])
        npc.approach_null += float(score[1:].sum() / (score.size - 1))
        npc.approach_moves += 1

    def _eat(self, npc: NPC, rule: str = "need") -> bool:
        """Eat a bite from the ground, else from the inventory. `rule` picks the
        food: "need" = the one that best fixes deficits per unit (crumbs count),
        "most" = the biggest pile (eat_most)."""
        cfg, w = self.cfg, self.world
        deficit = 1.0 - npc.nutrients
        value = (w.profiles @ deficit) * (1.0 - npc.satiation)
        here = w.food_at(npc.pos)
        if (here > 1e-9).any():
            score = here if rule == "most" else value
            t = int(np.argmax(np.where(here > 1e-9, score, -np.inf)))
            amount = min(cfg.bite_size, float(here[t]))
            here[t] -= amount
            zone = w.zone_at(t, npc.pos)
            if zone >= 0:                  # carried food doesn't count: it isn't a place
                last = npc.last_zone
                still = last is not None and w.zone_at(last[0], npc.pos) == last[1]
                if npc.record_zone((t, zone), still):
                    self.stats.count("zone_switches")
                    # Deficit-directed travel (M2 slice 3b): judged by where it
                    # arrived, not by what `eat` picked, since eat already
                    # chooses by deficit.
                    serves = w.serves(npc.pos)
                    npc.directed_hits += float(serves[int(np.argmin(npc.nutrients))])
                    npc.directed_chance += float(serves.mean())
        elif (npc.inventory > 1e-9).any():
            score = npc.inventory if rule == "most" else value
            t = int(np.argmax(np.where(npc.inventory > 1e-9, score, -np.inf)))
            amount = min(cfg.bite_size, float(npc.inventory[t]))
            npc.inventory[t] -= amount
        else:
            return False
        frac = amount / cfg.bite_size
        npc.body += amount
        npc.nutrients = np.clip(
            npc.nutrients + frac * cfg.nutrition_per_bite * w.profiles[t] * (1.0 - npc.satiation[t]),
            0.0, 1.0)
        npc.satiation[t] = min(1.0, npc.satiation[t] + cfg.satiation_gain * frac)
        npc.eaten[t] += amount
        self.stats.count("eats")
        if cfg.two_eat_actions:
            self.stats.count(f"eats_{rule}")
        return True

    def _pick_up(self, npc: NPC) -> bool:
        room = self.cfg.carry_capacity - float(npc.inventory.sum())
        here = self.world.food_at(npc.pos)
        if room <= 1e-9 or not (here > 1e-9).any():
            return False
        t = int(np.argmax(here))
        amount = min(self.cfg.bite_size, float(here[t]), room)
        here[t] -= amount
        npc.inventory[t] += amount
        return True

    def _give(self, npc: NPC, index: dict) -> bool:
        if npc.inventory.sum() <= 1e-9:
            return False
        cap = self.cfg.carry_capacity
        takers = sorted((n for n in self._neighbors(npc, index) if cap - n.inventory.sum() > 1e-9),
                        key=lambda n: n.id)            # by id: the pick mustn't depend on list order
        if not takers:
            return False
        other = takers[self.keys.stream(self.tick, npc.id, keyed.GIVE).integers(len(takers))]
        t = int(np.argmax(npc.inventory))
        amount = min(self.cfg.bite_size, float(npc.inventory[t]), cap - float(other.inventory.sum()))
        npc.inventory[t] -= amount
        other.inventory[t] += amount
        npc.gifts_given += 1
        other.gifts_received += 1
        self.stats.count("gives")
        return True

    def _can_mate(self, npc: NPC) -> bool:
        c = self.cfg
        return (npc.alive and npc.age >= c.adult_age and npc.body >= c.reproduce_min_mass
                and npc.health > 0.5 and self.tick >= npc.mate_cooldown_until)

    def _mate(self, npc: NPC, index: dict, births: list[NPC]) -> bool:
        """True only when a child is born; signaling readiness alone isn't busy."""
        cfg = self.cfg
        if not self._can_mate(npc):
            return False
        npc.mate_ready_until = self.tick + cfg.mate_window
        if len(self.npcs) + len(births) >= cfg.max_population:
            return False
        partners = sorted((n for n in self._neighbors(npc, index)
                           if n.mate_ready_until >= self.tick and self._can_mate(n)),
                          key=lambda n: n.id)

        if not partners:
            return False
        mate = partners[self.keys.stream(self.tick, npc.id, keyed.MATE).integers(len(partners))]
        half = cfg.child_mass / 2
        npc.body -= half
        mate.body -= half
        child_id = self.next_id                      # the child's draws are keyed by its id
        brain = Brain.crossover(npc.brain, mate.brain,
                                self.keys.stream(self.tick, child_id, keyed.CROSSOVER))
        parent_rate = (npc.collapse_rate() + mate.collapse_rate()) / 2
        known = [p.lineage for p in (npc, mate) if p.lineage >= 0]
        brain, mutations, lineage = self.mutate_child(
            brain, parent_rate, sum(known) / len(known) if known else -1.0, key_id=child_id)
        child = self._make_npc(brain, npc.pos, cfg.child_mass,
                               max(npc.generation, mate.generation) + 1)
        child.origin, child.mutations, child.parent_rate = "birth", mutations, parent_rate
        child.lineage = lineage
        births.append(child)
        for parent in (npc, mate):
            parent.offspring += 1
            parent.mate_ready_until = -1
            parent.mate_cooldown_until = self.tick + cfg.mate_cooldown
        self.stats.count("births")
        return True

    def _share(self, npc: NPC, index: dict) -> bool:
        sid = npc.known_secret
        if sid is None or sid not in self.deity.secrets:
            return False
        shared = 0
        for other in self._neighbors(npc, index):
            if other.known_secret != sid:
                other.known_secret = sid
                shared += 1
        if shared:
            self.stats.count("secrets_shared", shared)
        return shared > 0

    # ============================================================ metabolism
    def metabolize(self, npcs: list[NPC], aging: bool) -> None:
        """Everyone's metabolism first, then the fallen (health gone) in this order."""
        for npc in npcs:
            if npc.alive:
                self._metabolize(npc, aging)
        for npc in npcs:
            if npc.alive and npc.health <= 0:
                self._fall(npc)

    def _metabolize(self, npc: NPC, aging: bool) -> None:
        cfg, w = self.cfg, self.world

        moved_mass = cfg.metabolism_rate * npc.body
        npc.body -= moved_mass
        npc.bowel += moved_mass
        if npc.bowel >= cfg.bowel_capacity:
            w.poop[npc.pos] += npc.bowel
            npc.bowel = 0.0
            self.stats.count("accidents")

        idle = npc.idle_streak > cfg.idle_grace_ticks
        decay = cfg.nutrient_decay * (cfg.idle_hunger_multiplier if idle else 1.0)
        # np.minimum/maximum: same values as np.clip, much less overhead on tiny arrays.
        npc.nutrients = np.minimum(np.maximum(npc.nutrients - decay, 0.0), 1.0)
        npc.satiation = np.minimum(np.maximum(npc.satiation - cfg.satiation_decay, 0.0), 1.0)
        npc.smite = max(0.0, npc.smite - cfg.smite_decay)

        npc.lifetime += 1
        self.stats.generation_lifetime[npc.generation] += 1
        if aging:
            npc.age += 1

        damage = {}
        if npc.nutrients.min() < cfg.starving_threshold:
            damage["nutrient_starve"] = cfg.starvation_damage
        if npc.body < cfg.min_body_mass:
            damage["body_starve"] = cfg.starvation_damage
        stink = float(w.stink[npc.pos])
        if stink > cfg.stink_threshold:
            damage["stink"] = cfg.stink_damage * (stink - cfg.stink_threshold)
        if npc.age > cfg.old_age:
            damage["elder"] = cfg.elder_decline * (npc.age - cfg.old_age) / cfg.old_age

        if damage:
            for cause, amount in damage.items():
                npc.take_damage(cause, amount)
        elif npc.nutrients.min() > 0.4:
            npc.health = min(1.0, npc.health + cfg.heal_rate)
            if npc.health >= 1.0:
                npc.damage.clear()


    def _fall(self, npc: NPC) -> None:
        """Health ran out: elders die, the young collapse."""
        if npc.age >= self.cfg.old_age:
            self._die(npc)
        else:
            self._collapse(npc)

    def _drop_inventory(self, npc: NPC) -> None:
        here = self.world.food_at(npc.pos)
        here += npc.inventory
        npc.inventory[:] = 0.0

    def _collapse(self, npc: NPC) -> None:
        """Young NPCs can't die permanently. They collapse, drop what they
        carry, wake up somewhere else, and age faster for the trouble."""
        cfg = self.cfg
        self._drop_inventory(npc)
        npc.pos = self.world.random_cell(self.keys.stream(self.tick, npc.id, keyed.COLLAPSE))
        npc.health = cfg.collapse_health
        npc.nutrients = np.maximum(npc.nutrients, cfg.collapse_nutrient_floor)
        npc.age += cfg.collapse_age_penalty
        npc.collapses += 1
        npc.known_secret = None
        npc.last_zone = None               # waking up elsewhere isn't travel
        self.stats.count("collapses")
        self.stats.count(f"collapse_{npc.main_damage_cause()}")
        self.stats.generation_collapses[npc.generation] += 1
        npc.damage.clear()

    def _die(self, npc: NPC) -> None:
        """Elders die for real. The body becomes poop (which stinks, then
        fertilizes), so the mass goes back into the loop."""
        self._drop_inventory(npc)
        self.world.poop[npc.pos] += npc.body + npc.bowel
        npc.body = npc.bowel = 0.0
        npc.alive = False
        self._record_hall_of_fame(npc)
        self.stats.count("deaths")
        self.stats.count(f"death_{npc.main_damage_cause()}")
        self.stats.record_life(npc, self.tick)

    # ========================================================= population
    def _random_brain(self, draw) -> Brain:
        """`draw`: a keyed stream (keyed.Stream) or anything with NumPy's normal()."""
        return Brain.random(self.n_inputs, self.cfg.hidden_units, self.n_outputs, draw)

    def _make_npc(self, brain: Brain, pos, body: float, generation: int) -> NPC:
        cfg = self.cfg
        npc = NPC(
            id=self.next_id, pos=pos, brain=brain, body=body, generation=generation,
            nutrients=np.full(cfg.n_nutrients, 0.7),
            satiation=np.zeros(cfg.n_food_types),
            inventory=np.zeros(cfg.n_food_types),
            memory=np.zeros(cfg.memory_units),
        )
        self.next_id += 1
        return npc

    def _spawn(self, brain: Brain, pos, body: float, generation: int) -> NPC:
        npc = self._make_npc(brain, pos, body, generation)
        self.npcs.append(npc)
        return npc

    def population_collapse_rate(self) -> float:
        """Collapses per 1,000 ticks lived, over everyone alive (weighted by
        time lived, so newborns' noisy rates barely count)."""
        lived = sum(n.lifetime for n in self.npcs)
        return 1000.0 * sum(n.collapses for n in self.npcs) / lived if lived else -1.0

    def mutation_rate(self, brain: Brain, lineage: float, key_id: int = -1) -> float:
        """Chance per weight for a child whose ancestors collapsed at this rate
        (per 1,000 ticks; -1 = unknown). Measurement scripts override it (`key_id`
        is the new brain's NPC id, for their own keyed draws)."""
        cfg = self.cfg
        rate = brain.mutation_rate(cfg.mutation_rate, cfg.mutations_per_birth)
        if not cfg.mutation_lineage or lineage < 0:
            return rate
        # 5zorro's rule: ancestors collapsing more than the population today -> more
        # mutations; less -> fewer. Relative, so the rate doesn't just follow how
        # harsh the world is.
        top = cfg.mutation_lineage_max
        average = self.population_collapse_rate()
        if average > 0:
            factor = min(max(lineage / average, 1.0 / top), top)
        else:
            factor = top if lineage > 0 else 1.0
        return min(1.0, rate * factor)

    def mutate_child(self, brain: Brain, parent_rate: float, parent_lineage: float = -1.0,
                     key_id: int | None = None) -> tuple[Brain, float, float]:
        """A mutated copy, its expected number of mutated weights, and its
        lineage (ancestors' collapse rate: parents 1/2, then their lineage 1/2).
        Every child, top-up and seeded copy goes through here. Draws are keyed
        by `key_id`, the NPC that gets the brain (default: the next new id)."""
        key_id = self.next_id if key_id is None else key_id
        if parent_rate < 0:
            lineage = -1.0
        else:
            lineage = 0.5 * parent_rate + 0.5 * (parent_lineage if parent_lineage >= 0 else parent_rate)
        rate = self.mutation_rate(brain, lineage, key_id)
        draw = self.keys.stream(self.tick, key_id, keyed.MUTATE)
        return brain.mutate(rate, self.cfg.mutation_scale, draw), rate * brain.n_params, lineage

    def _record_hall_of_fame(self, npc: NPC) -> None:
        """A finished life: add it to the entry its brain was copied from (track
        record), then offer it a place of its own."""
        cfg = self.cfg
        population = self.population_collapse_rate()
        excess = npc.collapse_rate() - population if population >= 0 else 0.0
        if cfg.hall_of_fame_track_record and npc.source >= 0:
            self._credit_source(npc.source, excess)
        self.hall_of_fame.append({"fitness": npc.fitness(), "generation": npc.generation,
                                  "brain": npc.brain, "rate": npc.collapse_rate(),
                                  "lineage": npc.lineage, "id": npc.id, "lives": 1.0,
                                  "excess_sum": excess, "copies": 0.0, "copy_excess_sum": 0.0})
        self._rank_hall_of_fame()

    def _rank_hall_of_fame(self) -> None:
        key = self._merit if self.cfg.hall_of_fame_track_record else (lambda e: e["fitness"])
        self.hall_of_fame.sort(key=key, reverse=True)
        del self.hall_of_fame[self.cfg.hall_of_fame_size:]

    def _merit(self, entry: dict) -> float:
        """Track-record score of a hall-of-fame entry, higher is better: minus
        its average collapses above the population's, over its own life and its
        copies' lives, with `hall_of_fame_prior_lives` average (0) lives added."""
        return -entry["excess_sum"] / (entry["lives"] + self.cfg.hall_of_fame_prior_lives)

    def _living_merit(self, npc: NPC, population: float) -> float:
        """The same score for a living NPC: its life so far counts as a fraction
        of a life (lifetime / old_age, at most 1)."""
        if population < 0:
            return 0.0
        weight = min(1.0, npc.lifetime / self.cfg.old_age)
        return -(npc.collapse_rate() - population) * weight / (weight + self.cfg.hall_of_fame_prior_lives)

    def _credit_source(self, source: int, excess: float) -> None:
        """A copy's finished life joins its source entry's track record. After
        hall_of_fame_min_copies copies, an entry whose copies do worse than the
        population on average is dropped (5zorro's floor)."""
        cfg = self.cfg
        for i, entry in enumerate(self.hall_of_fame):
            if entry.get("id", -1) != source:
                continue
            entry["lives"] += 1
            entry["excess_sum"] += excess
            entry["copies"] += 1
            entry["copy_excess_sum"] += excess
            if (cfg.hall_of_fame_min_copies > 0 and entry["copies"] >= cfg.hall_of_fame_min_copies
                    and entry["copy_excess_sum"] > 0):
                del self.hall_of_fame[i]
                self.stats.count("hall_of_fame_dropped")
            self._rank_hall_of_fame()
            return
        self.stats.count("hall_of_fame_credit_lost")   # its source was pushed out first

    def _top_up(self) -> None:
        """If the population drops too low, spawn mutated copies of the best
        brains seen so far. Mass comes out of the soil, so it's still conserved."""
        cfg = self.cfg
        while len(self.npcs) < cfg.min_population:
            if not self.world.take_from_soil(cfg.npc_start_mass):
                break
            track = cfg.hall_of_fame_track_record
            population = self.population_collapse_rate() if track else -1.0
            candidates = [(self._merit(e) if track else e["fitness"], e["generation"], e["brain"],
                           e.get("rate", -1.0), e.get("lineage", -1.0), e.get("id", -1))
                          for e in self.hall_of_fame]
            candidates += [(self._living_merit(n, population) if track else n.fitness(),
                            n.generation, n.brain, n.collapse_rate(), n.lineage, -1)
                           for n in sorted(self.npcs, key=lambda n: n.id)]   # by id, not list order
            origin, mutations, parent_rate, lineage, source = "", -1.0, -1.0, -1.0, -1
            draw = self.keys.stream(self.tick, self.next_id, keyed.SPAWN)
            if candidates:
                picks = [candidates[draw.integers(len(candidates))] for _ in range(3)]
                _, gen, brain, parent_rate, parent_lineage, source = max(picks, key=lambda c: c[0])
                brain, mutations, lineage = self.mutate_child(brain, parent_rate, parent_lineage)
                origin, gen = "copy", gen + 1
            else:
                brain, gen = self._random_brain(draw), 0
            npc = self._spawn(brain, self.world.random_cell(draw), cfg.npc_start_mass, gen)
            npc.origin, npc.mutations, npc.parent_rate = origin, mutations, parent_rate
            npc.lineage, npc.source = lineage, source
            self.stats.count("spawns")

    # ============================================================== helpers
    def _spatial_index(self) -> dict:
        index: dict = {}
        for n in self.npcs:
            index.setdefault(n.pos, []).append(n)
        return index

    def _neighbors(self, npc: NPC, index: dict) -> list[NPC]:
        """NPCs in the same cell or one step away, by the positions `index` was
        built from (start of tick for senses, after the moves for social actions)."""
        cells = [npc.pos] + self.world.adjacent(npc.pos)
        return [o for c in cells for o in index.get(c, ()) if o is not npc and o.alive]
