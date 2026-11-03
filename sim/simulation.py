"""The core tick loop: senses -> tiny brain -> action -> metabolism.

Invariant: total mass (soil + food + poop + secret caches + everything NPCs
carry in body, bowel and inventory) never changes. tests/test_simulation.py
checks this. If you add a mechanic, keep it true.
"""
from __future__ import annotations

import numpy as np

from .brain import Brain
from .clock import SimClock
from .config import Config
from .deity import Deity
from .npc import NPC, build_actions
from .stats import Stats
from .world import World, wrapped_delta


class Simulation:
    def __init__(self, cfg: Config | None = None, populate: bool = True, log_every: int = 100):
        self.cfg = cfg or Config()
        self.rng = np.random.default_rng(self.cfg.seed)
        self.world = World(self.cfg, self.rng)
        self.deity = Deity(self.cfg)
        self.clock = SimClock()
        self.stats = Stats(log_every)
        self.actions = build_actions(self.cfg.dims)
        self.n_actions = len(self.actions)
        self.n_inputs = self.sensor_size()
        self.n_outputs = self.n_actions + self.cfg.memory_units
        self.npcs: list[NPC] = []
        self.hall_of_fame: list[dict] = []   # {"fitness", "generation", "brain"}
        self.overrides: dict[int, object] = {}  # npc id -> controller (see controllers.py)
        self.tick = 0
        self.next_id = 0
        if populate:
            for _ in range(self.cfg.initial_npcs):
                self._spawn(self._random_brain(), self.world.random_cell(self.rng),
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
        self.deity.step(self.tick, self.world, self.rng, self.stats)

        index = self._spatial_index()
        births: list[NPC] = []
        for i in self.rng.permutation(len(self.npcs)):
            npc = self.npcs[i]
            if not npc.alive:
                continue
            action = self._decide(npc, self.sense(npc, index))
            self._act(npc, action, index, births)
            if npc.alive:
                self._metabolize(npc, aging)

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
        food_grad, stink_grad, scent_grad = [], [], []
        for axis in range(cfg.dims):
            plus, minus = w.neighbor(p, axis, 1), w.neighbor(p, axis, -1)
            food_grad.append((w.food_at(plus) - w.food_at(minus)) / cfg.food_capacity)
            stink_grad.append(w.stink[plus] - w.stink[minus])
            if cfg.food_scent:
                # Relative difference: points uphill at any distance, like a nose.
                s_plus, s_minus = w.scent_at(plus), w.scent_at(minus)
                scent_grad.append((s_plus - s_minus) / (s_plus + s_minus + 1e-12))

        secret = self.deity.secrets.get(npc.known_secret) if npc.known_secret is not None else None
        if secret is None:
            npc.known_secret = None
            secret_part = np.zeros(1 + cfg.dims)
        else:
            secret_part = np.concatenate([[1.0], wrapped_delta(p, secret.pos, cfg.size) / half])

        shrine_part = np.zeros(cfg.dims + 1)
        if w.shrines:
            deltas = [wrapped_delta(p, s, cfg.size) for s in w.shrines]
            nearest = min(deltas, key=lambda d: np.abs(d).sum())
            shrine_part = np.concatenate([nearest / half, [1.0 if not nearest.any() else 0.0]])

        parts = [
            npc.nutrients,
            [npc.health, min(npc.age / cfg.old_age, 1.5),
             npc.body / cfg.npc_start_mass, npc.bowel / cfg.bowel_capacity],
            npc.satiation,
            w.food_at(p) / cfg.food_capacity,
            np.concatenate(food_grad),
            [w.stink[p]],
            stink_grad,
            [min(len(self._neighbors(npc, index)) / 4.0, 1.0)],
            npc.inventory / cfg.carry_capacity,
            [npc.piety, npc.smite],
            secret_part,
            shrine_part,
            [1.0 if npc.moved_last else 0.0],
            npc.memory,
            [1.0],
        ]
        if cfg.food_scent:
            here = w.scent_at(p)
            parts += [here / (here + cfg.scent_half), np.concatenate(scent_grad)]
        obs = np.concatenate([np.asarray(x, dtype=float).ravel() for x in parts])
        assert obs.size == self.n_inputs, (obs.size, self.n_inputs)
        return obs

    # ============================================================== thinking
    def _decide(self, npc: NPC, obs: np.ndarray) -> int:
        controller = self.overrides.get(npc.id)
        if controller is not None:
            return controller.decide(self, npc, obs)
        out = npc.brain.forward(obs)
        npc.memory = np.tanh(out[self.n_actions:])
        logits = out[: self.n_actions] / self.cfg.action_temperature
        logits -= logits.max()
        probs = np.exp(logits)
        probs /= probs.sum()
        return int(self.rng.choice(self.n_actions, p=probs))

    # =============================================================== actions
    def _act(self, npc: NPC, action: int, index: dict, births: list[NPC]) -> None:
        name = self.actions[action]
        moved = did = False          # did: the action changed something (not just tried)
        if name.startswith("move"):
            sign = 1 if name[4] == "+" else -1
            npc.pos = self.world.neighbor(npc.pos, int(name[5:]), sign)
            moved = True
            claimed = self.deity.claim_at(npc.pos, self.world)
            if claimed:
                self.stats.count("secrets_claimed", claimed)
        elif name == "eat":
            did = self._eat(npc)
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

    def _eat(self, npc: NPC) -> bool:
        cfg, w = self.cfg, self.world
        deficit = 1.0 - npc.nutrients
        value = (w.profiles @ deficit) * (1.0 - npc.satiation)
        here = w.food_at(npc.pos)
        if (here > 1e-9).any():
            t = int(np.argmax(np.where(here > 1e-9, value, -np.inf)))
            amount = min(cfg.bite_size, float(here[t]))
            here[t] -= amount
            zone = w.zone_at(t, npc.pos)
            if zone >= 0 and npc.record_zone((t, zone)):   # carried food isn't a place
                self.stats.count("zone_switches")
        elif (npc.inventory > 1e-9).any():
            t = int(np.argmax(np.where(npc.inventory > 1e-9, value, -np.inf)))
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
        takers = [n for n in self._neighbors(npc, index) if cap - n.inventory.sum() > 1e-9]
        if not takers:
            return False
        other = takers[int(self.rng.integers(len(takers)))]
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
        partners = [n for n in self._neighbors(npc, index)
                    if n.mate_ready_until >= self.tick and self._can_mate(n)]
        if not partners:
            return False
        mate = partners[int(self.rng.integers(len(partners)))]
        half = cfg.child_mass / 2
        npc.body -= half
        mate.body -= half
        brain = Brain.crossover(npc.brain, mate.brain, self.rng).mutate(
            cfg.mutation_rate, cfg.mutation_scale, self.rng)
        child = self._make_npc(brain, npc.pos, cfg.child_mass,
                               max(npc.generation, mate.generation) + 1)
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
        npc.nutrients = np.clip(npc.nutrients - decay, 0.0, 1.0)
        npc.satiation = np.clip(npc.satiation - cfg.satiation_decay, 0.0, 1.0)
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

        if npc.health <= 0:
            if npc.age >= cfg.old_age:
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
        npc.pos = self.world.random_cell(self.rng)
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
    def _random_brain(self) -> Brain:
        return Brain.random(self.n_inputs, self.cfg.hidden_units, self.n_outputs, self.rng)

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

    def _record_hall_of_fame(self, npc: NPC) -> None:
        self.hall_of_fame.append({"fitness": npc.fitness(), "generation": npc.generation,
                                  "brain": npc.brain})
        self.hall_of_fame.sort(key=lambda e: e["fitness"], reverse=True)
        del self.hall_of_fame[self.cfg.hall_of_fame_size:]

    def _top_up(self) -> None:
        """If the population drops too low, spawn mutated copies of the best
        brains seen so far. Mass comes out of the soil, so it's still conserved."""
        cfg = self.cfg
        while len(self.npcs) < cfg.min_population:
            if not self.world.take_from_soil(cfg.npc_start_mass):
                break
            candidates = [(e["fitness"], e["generation"], e["brain"]) for e in self.hall_of_fame]
            candidates += [(n.fitness(), n.generation, n.brain) for n in self.npcs]
            if candidates:
                picks = [candidates[int(self.rng.integers(len(candidates)))] for _ in range(3)]
                _, gen, brain = max(picks, key=lambda c: c[0])
                brain = brain.mutate(cfg.mutation_rate, cfg.mutation_scale, self.rng)
                gen += 1
            else:
                brain, gen = self._random_brain(), 0
            self._spawn(brain, self.world.random_cell(self.rng), cfg.npc_start_mass, gen)
            self.stats.count("spawns")

    # ============================================================== helpers
    def _spatial_index(self) -> dict:
        index: dict = {}
        for n in self.npcs:
            index.setdefault(n.pos, []).append(n)
        return index

    def _neighbors(self, npc: NPC, index: dict) -> list[NPC]:
        """NPCs in the same cell or one step away. Uses positions from the
        start of the tick, which is fine for a prototype."""
        cells = [npc.pos] + self.world.adjacent(npc.pos)
        return [o for c in cells for o in index.get(c, ()) if o is not npc and o.alive]
