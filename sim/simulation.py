"""The core tick loop, as array operations over every NPC at once.

The tick rules (docs/plan-gpu-backend.md, G1): every NPC senses the world as it
was at the start of the tick and decides; then the chosen actions resolve in
fixed phases (moves; eats and pick-ups; give, mate, share; the rest), then
everyone's metabolism, then deaths and collapses. Within a phase NPCs go in
priority order, a fresh keyed draw each tick (lowest first). All randomness is
keyed (sim/keyed.py).

NPC state lives in a Population (struct of arrays, sim/population.py); `npcs`
gives NPC-shaped views for scripts and tests. reference.py states the same
rules one NPC at a time, and tests/test_engines.py checks that both engines
produce identical worlds (G2). A rule change goes into both.

Exactness: where several NPCs add to one cell in a phase, the additions run in
priority order (np.add.at keeps index order), as the reference does them one
by one. Eaters sharing a cell take turns in rounds: the first of every cell,
then the second, and so on.

Invariant: total mass (soil + food + poop + secret caches + everything NPCs
carry in body, bowel and inventory) never changes. tests/test_simulation.py
checks this. If you add a mechanic, keep it true.
"""
from __future__ import annotations

import numpy as np

from . import keyed
from .brain import Brain
from .clock import SimClock
from .config import Config
from .deity import Deity
from .npc import NPC, build_actions
from .population import NPCView, Population
from .stats import Stats
from .world import World, wrapped_delta

# Rule 2's phases, in the order they resolve. "stay" and anything unlisted go last.
N_PHASES = 4
SOCIAL_PHASE = 2
_PHASES = {"eat": 1, "eat_need": 1, "eat_most": 1, "pick_up": 1,
           "give": SOCIAL_PHASE, "mate": SOCIAL_PHASE, "share": SOCIAL_PHASE}


def action_phase(name: str) -> int:
    return 0 if name.startswith("move") else _PHASES.get(name, 3)


class Simulation:
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
        self._phase = np.array([action_phase(a) for a in self.actions])
        self._act_index = {name: i for i, name in enumerate(self.actions)}
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
        types = c.n_food_types
        self.pop = Population(
            max(c.max_population, c.initial_npcs, c.min_population) + 1, c.dims,
            {"nutrients": c.n_nutrients, "satiation": types, "inventory": types,
             "memory": c.memory_units, "eaten": types},
            (self.n_inputs, c.hidden_units, self.n_outputs), c.food_patches_per_type)
        self._nbr = self.world.neighbor_table()            # (cells, 2 * dims)
        self._shrine_table: np.ndarray | None = None
        self._shrines_cached: list = []
        self._present: np.ndarray | None = None            # slots alive at the tick's start
        self.hall_of_fame: list[dict] = []   # see nursery.hall_of_fame_entry for the fields
        self.overrides: dict[int, object] = {}  # npc id -> controller (see controllers.py)
        self.tick = 0
        self.next_id = 0
        if populate:
            for _ in range(self.cfg.initial_npcs):
                draw = self.keys.stream(0, self.next_id, keyed.INIT)
                self._spawn(self._random_brain(draw), self.world.random_cell(draw),
                            self.cfg.npc_start_mass, generation=0)

    # ============================================================ the NPCs
    @property
    def npcs(self) -> list[NPCView]:
        """The living NPCs as views, by id (writes go into the arrays)."""
        live = self.pop.live()
        return [NPCView(self.pop, s) for s in self._by_id(live)]

    @npcs.setter
    def npcs(self, npcs: list) -> None:
        """Replace everyone with these NPC records (or views); dead ones are dropped."""
        records = [n if isinstance(n, NPC) else self.pop.record(n._check()[1]) for n in npcs]
        self.pop.clear()
        for r in records:
            if r.alive:
                self.pop.add(r)

    def _slot(self, npc) -> int:
        if not isinstance(npc, NPCView) or npc._pop is not self.pop:
            raise TypeError("expected one of this simulation's NPCs (from sim.npcs)")
        return npc._check()[1]

    def _slots(self, npcs) -> np.ndarray:
        return np.array([self._slot(n) for n in npcs], dtype=np.int64)

    def _by_id(self, slots: np.ndarray) -> np.ndarray:
        return slots[np.argsort(self.pop.id[slots], kind="stable")]

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
        self._present = order
        actions = self.decide_all(order)
        births: list[NPC] = []
        self.resolve(order, actions, births)
        self._metabolize(order, aging)
        self._fall(order)
        self._present = None
        for child in births:
            self.pop.add(child)
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
        P, live = self.pop, self._by_id(self.pop.live())
        each = P.body[live] + P.bowel[live] + P.inventory[live].sum(axis=1)
        carried = sum(each.tolist())        # one by one, in id order, like the reference
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

    def sense(self, npc, index=None) -> np.ndarray:
        """One NPC's senses (`index` is ignored; kept for the reference's signature)."""
        return self.sense_slots(np.array([self._slot(npc)]))[0]

    def sense_slots(self, slots: np.ndarray) -> np.ndarray:
        """Senses of these slots, one row each, from the world as it is now."""
        cfg, w, P = self.cfg, self.world, self.pop
        n, d = slots.size, cfg.dims
        types = w.food.shape[0]
        half = cfg.size / 2
        flat = w.flat(P.pos[slots])
        nbr = self._nbr[flat]                                   # (n, 2d): +1, -1 per axis
        food = w.food.reshape(types, -1)
        food_n = food[:, nbr]                                   # (types, n, 2d)
        food_grad = ((food_n[:, :, 0::2] - food_n[:, :, 1::2]) / cfg.food_capacity
                     ).transpose(1, 2, 0).reshape(n, d * types)    # axis by axis, every type
        stink = w.stink.reshape(-1)
        stink_n = stink[nbr]
        # Others in the same cell or one step away.
        occupied = np.bincount(w.flat(P.pos[P.live()]), minlength=stink.size)
        crowd = occupied[flat] + occupied[nbr].sum(axis=1) - 1

        secret = np.zeros((n, 1 + d))
        for i in np.flatnonzero(P.known_secret[slots] >= 0):
            s = self.deity.secrets.get(int(P.known_secret[slots[i]]))
            if s is None:                                       # gone stale or claimed
                P.known_secret[slots[i]] = -1
            else:
                secret[i, 0] = 1.0
                secret[i, 1:] = wrapped_delta(P.pos[slots[i]], s.pos, cfg.size) / half

        parts = [
            P.nutrients[slots],
            np.stack([P.health[slots], np.minimum(P.age[slots] / cfg.old_age, 1.5),
                      P.body[slots] / cfg.npc_start_mass, P.bowel[slots] / cfg.bowel_capacity], axis=1),
            P.satiation[slots],
            food[:, flat].T / cfg.food_capacity,
            food_grad,
            stink[flat][:, None],
            stink_n[:, 0::2] - stink_n[:, 1::2],
            np.minimum(crowd / 4.0, 1.0)[:, None],
            P.inventory[slots] / cfg.carry_capacity,
            np.stack([P.piety[slots], P.smite[slots]], axis=1),
            secret,
            self._shrines()[flat],
            P.moved_last[slots].astype(float)[:, None],
            P.memory[slots],
            np.ones((n, 1)),
        ]
        if cfg.food_scent:
            scent = w.scent.reshape(types, -1)
            here = scent[:, flat].T
            scent_n = scent[:, nbr]
            s_plus, s_minus = scent_n[:, :, 0::2], scent_n[:, :, 1::2]
            # Relative difference: points uphill at any distance, like a nose.
            parts += [here / (here + cfg.scent_half),
                      ((s_plus - s_minus) / (s_plus + s_minus + 1e-12)).transpose(1, 2, 0).reshape(n, d * types)]
        obs = np.concatenate(parts, axis=1, dtype=float)
        assert obs.shape == (n, self.n_inputs), (obs.shape, self.n_inputs)
        return obs

    def _shrines(self) -> np.ndarray:
        """Per cell: direction to the nearest shrine and whether it's on one
        ((cells, dims + 1); rebuilt if the shrines change). Ties go to the
        first shrine in the list, as in the reference."""
        w, cfg = self.world, self.cfg
        if self._shrine_table is None or self._shrines_cached != w.shrines:
            cells = np.indices(w.shape).reshape(cfg.dims, -1).T          # (cells, dims)
            table = np.zeros((cells.shape[0], cfg.dims + 1))
            if w.shrines:
                shrines = np.array(w.shrines)
                deltas = (shrines[:, None, :] - cells[None] + cfg.size // 2) % cfg.size - cfg.size // 2
                nearest = deltas[np.abs(deltas).sum(axis=2).argmin(axis=0), np.arange(cells.shape[0])]
                table[:, :cfg.dims] = nearest / (cfg.size / 2)
                table[:, cfg.dims] = (~nearest.any(axis=1)).astype(float)
            self._shrine_table, self._shrines_cached = table, list(w.shrines)
        return self._shrine_table

    # ============================================================== thinking
    def _priority_order(self) -> np.ndarray:
        """The living slots, lowest priority draw first (ties, practically never,
        by id). Every phase of the tick goes in this order."""
        live = self.pop.live()
        if not live.size:
            return live
        ids = self.pop.id[live]
        return live[np.lexsort((ids, self.keys.uniform(self.tick, ids, keyed.ORDER)))]

    def decide_all(self, order: np.ndarray) -> np.ndarray:
        """Rule 1: everyone senses the start-of-tick world and picks an action
        (an index into self.actions). Deciding changes only each NPC's own memory.
        (5zorro's reaction-time queue would hand `resolve` actions decided
        earlier instead; docs/plan-gpu-backend.md.)"""
        if not order.size:
            return np.zeros(0, dtype=np.int64)
        P, A = self.pop, self.n_actions
        obs = self.sense_slots(order)
        u = self.keys.uniform(self.tick, P.id[order], keyed.ACTION)
        hidden = np.tanh(np.matmul(P.w1[order], obs[:, :, None])[:, :, 0] + P.b1[order])
        out = np.matmul(P.w2[order], hidden[:, :, None])[:, :, 0] + P.b2[order]
        logits = out[:, :A] / self.cfg.action_temperature
        logits -= logits.max(axis=1, keepdims=True)
        probs = np.exp(logits)
        probs /= probs.sum(axis=1, keepdims=True)
        # The way NumPy's rng.choice(p=probs) samples (one uniform draw against the
        # cumulative sum), with each NPC's keyed draw `u`.
        cdf = probs.cumsum(axis=1)
        cdf /= cdf[:, -1:]
        actions = (cdf <= u[:, None]).sum(axis=1)
        brained = np.ones(order.size, dtype=bool)
        if self.overrides:
            for i, slot in enumerate(order.tolist()):
                controller = self.overrides.get(int(P.id[slot]))
                if controller is not None:
                    actions[i] = controller.decide(self, NPCView(P, slot), obs[i])
                    brained[i] = False
        P.memory[order[brained]] = np.tanh(out[brained, A:])
        return actions

    # =============================================================== actions
    def resolve(self, order: np.ndarray, actions: np.ndarray, births: list[NPC]) -> None:
        """Rules 2-3: actions take effect phase by phase, in priority order."""
        cfg, P = self.cfg, self.pop
        phase = self._phase[actions]
        moved = phase == 0
        did = np.zeros(order.size, dtype=bool)
        if moved.any():
            self._moves(order[moved], actions[moved])
        eats = phase == 1
        if eats.any():
            did[eats] = self._eats(order[eats], actions[eats])
        social = phase == SOCIAL_PHASE
        if social.any():
            did[social] = self._social(order[social], actions[social], births)
        rest = phase == 3
        if rest.any():
            did[rest] = self._rest(order[rest], actions[rest])
        P.moved_last[order] = moved
        busy = moved | (did & cfg.busy_resets_idle)
        P.idle_streak[order] = np.where(busy, 0, P.idle_streak[order] + 1)

    def _moves(self, slots: np.ndarray, actions: np.ndarray) -> None:
        cfg, w, P = self.cfg, self.world, self.pop
        before = P.pos[slots].copy()
        rows = np.arange(slots.size)
        axis = actions // 2                         # moves are move+0, move-0, move+1, ...
        after = before.copy()
        after[rows, axis] = (after[rows, axis] + np.where(actions % 2 == 0, 1, -1)) % cfg.size
        P.pos[slots] = after
        self._record_approach(slots, w.flat(before), w.flat(after))
        if self.deity.secrets:
            claimed = self.deity.claim_cells({tuple(int(v) for v in p) for p in after}, w)
            if claimed:
                self.stats.count("secrets_claimed", claimed)

    def _record_approach(self, slots: np.ndarray, before: np.ndarray, after: np.ndarray) -> None:
        """M2 slice 3c: did this move head for the food the NPC needs most, more
        than for the others? Moves only, so the eat instinct can't leak in."""
        w, P = self.world, self.pop
        k = w.need_distance.shape[0]
        need = np.argmin(P.nutrients[slots], axis=1)
        rows = np.arange(slots.size)
        dist = w.need_distance.reshape(k, -1)
        here = dist[:, before].T                                       # (n, nutrients)
        others = np.isfinite(here)
        others[rows, need] = False
        ok = (~w.serves_table().reshape(k, -1)[need, before]          # not already at its food
              & np.isfinite(here[rows, need]) & others.any(axis=1))
        if not ok.any():
            return
        slots, need, here, others = slots[ok], need[ok], here[ok], others[ok]
        rows = np.arange(slots.size)
        # Score the move taken, then every possible step from the same cell. Their
        # mean is what a random step scores. Not 0: a random walk drifts away from
        # near food faster than from far food (gotchas.md).
        cells = np.concatenate([after[ok][:, None], self._nbr[before[ok]]], axis=1)   # (n, steps)
        delta = dist[:, cells].transpose(1, 0, 2) - here[:, :, None]                  # (n, nutrients, steps)
        score = (np.where(others[:, :, None], delta, 0.0).sum(axis=1) / others.sum(axis=1)[:, None]
                 - delta[rows, need])
        P.approach_sum[slots] += score[:, 0]
        P.approach_null[slots] += score[:, 1:].sum(axis=1) / (score.shape[1] - 1)
        P.approach_moves[slots] += 1

    def _eats(self, slots: np.ndarray, actions: np.ndarray) -> np.ndarray:
        """Eaters and pick-uppers sharing a cell take turns in priority order: in
        round r, the r-th of every cell acts (different cells don't interact)."""
        flat = self.world.flat(self.pop.pos[slots])
        by_cell = np.argsort(flat, kind="stable")       # stable: priority order within a cell
        sorted_flat = flat[by_cell]
        first = np.r_[True, sorted_flat[1:] != sorted_flat[:-1]]
        starts = np.maximum.accumulate(np.where(first, np.arange(flat.size), 0))
        turn = np.empty(flat.size, dtype=np.int64)
        turn[by_cell] = np.arange(flat.size) - starts
        did = np.zeros(slots.size, dtype=bool)
        for r in range(int(turn.max()) + 1):
            now = np.flatnonzero(turn == r)
            did[now] = self._eat_round(slots[now], actions[now], flat[now])
        return did

    def _eat_round(self, slots: np.ndarray, actions: np.ndarray, flat: np.ndarray) -> np.ndarray:
        """One round of eats and pick-ups, at most one NPC per cell."""
        did = np.zeros(slots.size, dtype=bool)
        pick = actions == self._act_index["pick_up"]
        if pick.any():
            did[pick] = self._pick_up(slots[pick], flat[pick])
        if (~pick).any():
            most = actions[~pick] == self._act_index.get("eat_most", -1)
            did[~pick] = self._eat_slots(slots[~pick], flat[~pick], most)
        return did

    def _eat(self, npc, rule: str = "need") -> bool:
        """The reference's single-NPC eat (tests use it)."""
        slot = np.array([self._slot(npc)])
        return bool(self._eat_slots(slot, self.world.flat(self.pop.pos[slot]), np.array([rule == "most"]))[0])

    def _eat_slots(self, slots: np.ndarray, flat: np.ndarray, most: np.ndarray) -> np.ndarray:
        """Eat a bite from the ground, else from the inventory. Per NPC, the food
        is the one that best fixes deficits per unit (crumbs count), or with
        `most` (eat_most) the biggest pile. One NPC per cell."""
        cfg, w, P = self.cfg, self.world, self.pop
        types = w.food.shape[0]
        food = w.food.reshape(types, -1)
        rows = np.arange(slots.size)
        deficit = 1.0 - P.nutrients[slots]
        value = np.matmul(w.profiles, deficit[:, :, None])[:, :, 0] * (1.0 - P.satiation[slots])
        here = food[:, flat].T                                  # (n, types), a copy
        inventory = P.inventory[slots]
        ground = (here > 1e-9).any(axis=1)
        ate = ground | (inventory > 1e-9).any(axis=1)
        source = np.where(ground[:, None], here, inventory)
        score = np.where(most[:, None], source, value)
        t = np.argmax(np.where(source > 1e-9, score, -np.inf), axis=1)
        amount = np.minimum(cfg.bite_size, source[rows, t])
        g = np.flatnonzero(ground)
        food[t[g], flat[g]] -= amount[g]
        inv = np.flatnonzero(ate & ~ground)
        P.inventory[slots[inv], t[inv]] -= amount[inv]
        if g.size:
            self._record_zones(slots[g], flat[g], t[g])
        e = np.flatnonzero(ate)
        if not e.size:
            return ate
        s, t, amount = slots[e], t[e], amount[e]
        frac = amount / cfg.bite_size
        P.body[s] += amount
        P.nutrients[s] = np.clip(
            P.nutrients[s] + (frac * cfg.nutrition_per_bite)[:, None] * w.profiles[t]
            * (1.0 - P.satiation[s, t])[:, None], 0.0, 1.0)
        P.satiation[s, t] = np.minimum(1.0, P.satiation[s, t] + cfg.satiation_gain * frac)
        P.eaten[s, t] += amount
        self.stats.count("eats", e.size)
        if cfg.two_eat_actions:
            n_most = int(most[e].sum())
            if e.size - n_most:
                self.stats.count("eats_need", e.size - n_most)
            if n_most:
                self.stats.count("eats_most", n_most)
        return ate

    def _record_zones(self, slots: np.ndarray, flat: np.ndarray, t: np.ndarray) -> None:
        """M2 travel: a bite from the ground inside a zone (food type, patch);
        a switch is a different zone from the last in-zone bite, after leaving
        it (eating another food where two zones overlap isn't travel)."""
        w, P = self.world, self.pop
        zones = w.zones.reshape(w.zones.shape[0], -1)
        zone = zones[t, flat]
        inside = zone >= 0                              # carried food doesn't count: it isn't a place
        if not inside.any():
            return
        slots, flat, t, zone = slots[inside], flat[inside], t[inside], zone[inside]
        last_t, last_z = P.last_zone[slots, 0], P.last_zone[slots, 1]
        has_last = last_t >= 0
        still = has_last & (zones[np.maximum(last_t, 0), flat] == last_z)
        switched = has_last & ((t != last_t) | (zone != last_z)) & ~still
        P.zones_eaten[slots, t, zone] = True
        P.zone_switches[slots] += switched
        P.last_zone[slots, 0], P.last_zone[slots, 1] = t, zone
        if switched.any():
            self.stats.count("zone_switches", int(switched.sum()))
            # Deficit-directed travel (M2 slice 3b): judged by where it arrived,
            # not by what `eat` picked, since eat already chooses by deficit.
            s, f = slots[switched], flat[switched]
            serves = w.serves_table().reshape(w.need_distance.shape[0], -1)[:, f].T
            need = np.argmin(P.nutrients[s], axis=1)
            P.directed_hits[s] += serves[np.arange(s.size), need]
            P.directed_chance[s] += serves.mean(axis=1)

    def _pick_up(self, slots: np.ndarray, flat: np.ndarray) -> np.ndarray:
        cfg, P = self.cfg, self.pop
        types = self.world.food.shape[0]
        food = self.world.food.reshape(types, -1)
        room = cfg.carry_capacity - P.inventory[slots].sum(axis=1)
        here = food[:, flat].T
        ok = ~(room <= 1e-9) & (here > 1e-9).any(axis=1)
        k = np.flatnonzero(ok)
        if k.size:
            t = np.argmax(here[k], axis=1)
            amount = np.minimum(np.minimum(cfg.bite_size, here[k, t]), room[k])
            food[t, flat[k]] -= amount
            P.inventory[slots[k], t] += amount
        return ok

    # -------------------------------------------- social actions (few, in turn)
    def _social(self, slots: np.ndarray, actions: np.ndarray, births: list[NPC]) -> np.ndarray:
        """give, mate and share, one NPC at a time in priority order. They see
        where everyone is after the moves."""
        P, w = self.pop, self.world
        live = P.live()
        index: dict[int, list[int]] = {}
        for slot, cell in zip(live.tolist(), w.flat(P.pos[live]).tolist()):
            index.setdefault(cell, []).append(slot)
        did = np.zeros(slots.size, dtype=bool)
        handlers = {self._act_index.get("give"): self._give, self._act_index.get("mate"): self._mate,
                    self._act_index.get("share"): self._share}
        for i, (slot, action) in enumerate(zip(slots.tolist(), actions.tolist())):
            did[i] = handlers[action](slot, index, births)
        return did

    def _neighbors(self, slot: int, index: dict) -> list[int]:
        """Slots in the same cell or one step away (by the positions `index`
        was built from), other than `slot`."""
        cell = int(self.world.flat(self.pop.pos[slot][None])[0])
        return [o for c in [cell, *self._nbr[cell].tolist()] for o in index.get(c, ()) if o != slot]

    def _give(self, slot: int, index: dict, births: list) -> bool:
        P, cfg = self.pop, self.cfg
        if P.inventory[slot].sum() <= 1e-9:
            return False
        cap = cfg.carry_capacity
        takers = sorted((o for o in self._neighbors(slot, index) if cap - P.inventory[o].sum() > 1e-9),
                        key=lambda o: P.id[o])            # by id: the pick mustn't depend on list order
        if not takers:
            return False
        other = takers[self.keys.stream(self.tick, int(P.id[slot]), keyed.GIVE).integers(len(takers))]
        t = int(np.argmax(P.inventory[slot]))
        amount = min(cfg.bite_size, float(P.inventory[slot, t]), cap - float(P.inventory[other].sum()))
        P.inventory[slot, t] -= amount
        P.inventory[other, t] += amount
        P.gifts_given[slot] += 1
        P.gifts_received[other] += 1
        self.stats.count("gives")
        return True

    def _can_mate(self, slot: int) -> bool:
        c, P = self.cfg, self.pop
        return bool(P.alive[slot] and P.age[slot] >= c.adult_age and P.body[slot] >= c.reproduce_min_mass
                    and P.health[slot] > 0.5 and self.tick >= P.mate_cooldown_until[slot])

    def _rate(self, slot: int) -> float:
        """NPC.collapse_rate for a slot."""
        return 1000.0 * int(self.pop.collapses[slot]) / max(int(self.pop.lifetime[slot]), 1)

    def _mate(self, slot: int, index: dict, births: list[NPC]) -> bool:
        """True only when a child is born; signaling readiness alone isn't busy."""
        cfg, P = self.cfg, self.pop
        if not self._can_mate(slot):
            return False
        P.mate_ready_until[slot] = self.tick + cfg.mate_window
        if self.pop.count() + len(births) >= cfg.max_population:
            return False
        partners = sorted((o for o in self._neighbors(slot, index)
                           if P.mate_ready_until[o] >= self.tick and self._can_mate(o)),
                          key=lambda o: P.id[o])
        if not partners:
            return False
        mate = partners[self.keys.stream(self.tick, int(P.id[slot]), keyed.MATE).integers(len(partners))]
        half = cfg.child_mass / 2
        P.body[slot] -= half
        P.body[mate] -= half
        child_id = self.next_id                      # the child's draws are keyed by its id
        brain = Brain.crossover(P.brain(slot), P.brain(mate),
                                self.keys.stream(self.tick, child_id, keyed.CROSSOVER))
        parent_rate = (self._rate(slot) + self._rate(mate)) / 2
        known = [float(P.lineage[p]) for p in (slot, mate) if P.lineage[p] >= 0]
        brain, mutations, lineage = self.mutate_child(
            brain, parent_rate, sum(known) / len(known) if known else -1.0, key_id=child_id)
        child = self._make_npc(brain, tuple(int(v) for v in P.pos[slot]), cfg.child_mass,
                               max(int(P.generation[slot]), int(P.generation[mate])) + 1)
        child.origin, child.mutations, child.parent_rate = "birth", mutations, parent_rate
        child.lineage = lineage
        births.append(child)
        for parent in (slot, mate):
            P.offspring[parent] += 1
            P.mate_ready_until[parent] = -1
            P.mate_cooldown_until[parent] = self.tick + cfg.mate_cooldown
        self.stats.count("births")
        return True

    def _share(self, slot: int, index: dict, births: list) -> bool:
        P = self.pop
        sid = int(P.known_secret[slot])
        if sid < 0 or sid not in self.deity.secrets:
            return False
        shared = 0
        for other in self._neighbors(slot, index):
            if P.known_secret[other] != sid:
                P.known_secret[other] = sid
                shared += 1
        if shared:
            self.stats.count("secrets_shared", shared)
        return shared > 0

    def _rest(self, slots: np.ndarray, actions: np.ndarray) -> np.ndarray:
        """poop, pray, worship (and stay, which does nothing on purpose)."""
        cfg, w, P = self.cfg, self.world, self.pop
        did = np.zeros(slots.size, dtype=bool)
        poop = (actions == self._act_index["poop"]) & (P.bowel[slots] > 1e-9)
        if poop.any():
            s = slots[poop]
            np.add.at(w.poop.reshape(-1), w.flat(P.pos[s]), P.bowel[s])   # in priority order
            P.bowel[s] = 0.0
            self.stats.count("poops", s.size)
            did[poop] = True
        names = {"answered": "prayers_answered", "silent": "prayers_silent",
                 "ignored": "prayers_ignored", "smitten": "smitings"}
        for i in np.flatnonzero(actions == self._act_index["pray"]).tolist():
            result = self.deity.pray(NPCView(P, slots[i]), self.tick)
            self.stats.count(names[result])
            did[i] = result == "answered"
        worship = actions == self._act_index["worship"]
        if worship.any() and w.shrines:
            on = np.isin(w.flat(P.pos[slots]), w.flat(np.array(w.shrines)))
            k = np.flatnonzero(worship & on)
            if k.size:
                P.piety[slots[k]] = np.minimum(1.0, P.piety[slots[k]] + cfg.worship_piety_gain)
                self.stats.count("worships", k.size)
                did[k] = True
        return did

    # ============================================================ metabolism
    def metabolize(self, npcs: list, aging: bool) -> None:
        """Everyone's metabolism first, then the fallen (health gone) in this order."""
        slots = self._slots([n for n in npcs if n.alive])
        outside_tick = self._present is None
        if outside_tick:
            self._present = self.pop.live()
        try:
            self._metabolize(slots, aging)
            self._fall(slots)
        finally:
            if outside_tick:
                self._present = None

    def _metabolize(self, s: np.ndarray, aging: bool) -> None:
        cfg, w, P = self.cfg, self.world, self.pop
        if not s.size:
            return
        moved_mass = cfg.metabolism_rate * P.body[s]
        P.body[s] -= moved_mass
        P.bowel[s] += moved_mass
        accident = P.bowel[s] >= cfg.bowel_capacity
        if accident.any():
            a = s[accident]
            np.add.at(w.poop.reshape(-1), w.flat(P.pos[a]), P.bowel[a])     # in priority order
            P.bowel[a] = 0.0
            self.stats.count("accidents", a.size)

        idle = P.idle_streak[s] > cfg.idle_grace_ticks
        decay = np.where(idle, cfg.nutrient_decay * cfg.idle_hunger_multiplier, cfg.nutrient_decay * 1.0)
        # np.minimum/maximum: the same values as np.clip.
        P.nutrients[s] = np.minimum(np.maximum(P.nutrients[s] - decay[:, None], 0.0), 1.0)
        P.satiation[s] = np.minimum(np.maximum(P.satiation[s] - cfg.satiation_decay, 0.0), 1.0)
        P.smite[s] = np.maximum(0.0, P.smite[s] - cfg.smite_decay)

        P.lifetime[s] += 1
        generations, counts = np.unique(P.generation[s], return_counts=True)
        for g, k in zip(generations.tolist(), counts.tolist()):
            self.stats.generation_lifetime[g] += k
        if aging:
            P.age[s] += 1

        lowest = P.nutrients[s].min(axis=1)
        starving = lowest < cfg.starving_threshold
        thin = P.body[s] < cfg.min_body_mass
        stink = w.stink.reshape(-1)[w.flat(P.pos[s])]
        stinky = stink > cfg.stink_threshold
        elder = P.age[s] > cfg.old_age
        # One cause at a time, in the reference's order, so health falls the same way.
        P.add_damage(s[starving], "nutrient_starve", cfg.starvation_damage, self.tick)
        P.add_damage(s[thin], "body_starve", cfg.starvation_damage, self.tick)
        P.add_damage(s[stinky], "stink", cfg.stink_damage * (stink[stinky] - cfg.stink_threshold), self.tick)
        P.add_damage(s[elder], "elder", cfg.elder_decline * (P.age[s[elder]] - cfg.old_age) / cfg.old_age,
                     self.tick)
        heal = s[~(starving | thin | stinky | elder) & (lowest > 0.4)]
        P.health[heal] = np.minimum(1.0, P.health[heal] + cfg.heal_rate)
        whole = heal[P.health[heal] >= 1.0]
        P.damage[whole] = 0.0
        P.damage_seq[whole] = 0

    def _fall(self, slots: np.ndarray) -> None:
        """Health ran out: elders die, the young collapse (in priority order)."""
        P = self.pop
        for slot in slots[P.alive[slots] & (P.health[slots] <= 0)].tolist():
            if P.age[slot] >= self.cfg.old_age:
                self._die_slot(slot)
            else:
                self._collapse_slot(slot)

    def _drop_inventory(self, slot: int) -> None:
        here = self.world.food_at(tuple(int(v) for v in self.pop.pos[slot]))
        here += self.pop.inventory[slot]
        self.pop.inventory[slot] = 0.0

    def _collapse_slot(self, slot: int) -> None:
        """Young NPCs can't die permanently. They collapse, drop what they
        carry, wake up somewhere else, and age faster for the trouble."""
        cfg, P = self.cfg, self.pop
        self._drop_inventory(slot)
        P.pos[slot] = self.world.random_cell(self.keys.stream(self.tick, int(P.id[slot]), keyed.COLLAPSE))
        P.health[slot] = cfg.collapse_health
        P.nutrients[slot] = np.maximum(P.nutrients[slot], cfg.collapse_nutrient_floor)
        P.age[slot] += cfg.collapse_age_penalty
        P.collapses[slot] += 1
        P.known_secret[slot] = -1
        P.last_zone[slot] = -1                 # waking up elsewhere isn't travel
        self.stats.count("collapses")
        self.stats.count(f"collapse_{P.main_damage_cause(slot)}")
        self.stats.generation_collapses[int(P.generation[slot])] += 1
        P.damage[slot] = 0.0
        P.damage_seq[slot] = 0

    def _die_slot(self, slot: int) -> None:
        """Elders die for real. The body becomes poop (which stinks, then
        fertilizes), so the mass goes back into the loop."""
        P = self.pop
        self._drop_inventory(slot)
        self.world.poop[tuple(int(v) for v in P.pos[slot])] += P.body[slot] + P.bowel[slot]
        P.body[slot] = P.bowel[slot] = 0.0
        P.alive[slot] = False
        npc = NPCView(P, slot)
        self._record_hall_of_fame(npc)
        self.stats.count("deaths")
        self.stats.count(f"death_{P.main_damage_cause(slot)}")
        self.stats.record_life(npc, self.tick)

    # The reference's single-NPC helpers, for tests and scripts.
    def _spatial_index(self) -> None:
        return None

    def _act(self, npc, action: int, index=None, births: list | None = None) -> None:
        outside_tick = self._present is None
        if outside_tick:
            self._present = self.pop.live()
        try:
            self.resolve(np.array([self._slot(npc)]), np.array([action]), [] if births is None else births)
        finally:
            if outside_tick:
                self._present = None

    def _die(self, npc) -> None:
        self._die_slot(self._slot(npc))

    def _collapse(self, npc) -> None:
        self._collapse_slot(self._slot(npc))

    # ========================================================= population
    def _random_brain(self, draw) -> Brain:
        """`draw`: a keyed stream (keyed.Stream) or anything with NumPy's normal()."""
        return Brain.random(self.n_inputs, self.cfg.hidden_units, self.n_outputs, draw)

    def _make_npc(self, brain: Brain, pos, body: float, generation: int) -> NPC:
        """A new NPC record with the next id (not added to the world yet)."""
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

    def _spawn(self, brain: Brain, pos, body: float, generation: int) -> NPCView:
        return NPCView(self.pop, self.pop.add(self._make_npc(brain, pos, body, generation)))

    def population_collapse_rate(self) -> float:
        """Collapses per 1,000 ticks lived, over everyone alive (weighted by
        time lived, so newborns' noisy rates barely count). During a tick,
        "alive" means alive when the tick began, as in the reference."""
        P = self.pop
        slots = self._present if self._present is not None else P.live()
        lived = int(P.lifetime[slots].sum())
        return 1000.0 * int(P.collapses[slots].sum()) / lived if lived else -1.0

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

    def _record_hall_of_fame(self, npc) -> None:
        """A finished life (a record or a view): add it to the entry its brain was
        copied from (track record), then offer it a place of its own."""
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

    def _living_merit(self, npc, population: float) -> float:
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
        cfg, P = self.cfg, self.pop
        while P.count() < cfg.min_population:
            if not self.world.take_from_soil(cfg.npc_start_mass):
                break
            track = cfg.hall_of_fame_track_record
            population = self.population_collapse_rate() if track else -1.0
            living = self._by_id(P.live())
            lifetime, collapses = P.lifetime[living], P.collapses[living]
            rate = 1000.0 * collapses / np.maximum(lifetime, 1)
            if not track:
                living_score = P.offspring[living] * 500.0 + lifetime - collapses * 100.0
            elif population < 0:
                living_score = np.zeros(living.size)
            else:
                weight = np.minimum(1.0, lifetime / cfg.old_age)
                living_score = -(rate - population) * weight / (weight + cfg.hall_of_fame_prior_lives)
            n_hall = len(self.hall_of_fame)
            scores = [self._merit(e) if track else e["fitness"] for e in self.hall_of_fame]
            scores += living_score.tolist()
            origin, mutations, parent_rate, lineage, source = "", -1.0, -1.0, -1.0, -1
            draw = self.keys.stream(self.tick, self.next_id, keyed.SPAWN)
            if scores:
                picks = [draw.integers(len(scores)) for _ in range(3)]
                best = max(picks, key=lambda i: scores[i])         # the first best, like max()
                if best < n_hall:
                    e = self.hall_of_fame[best]
                    gen, brain, parent_rate = e["generation"], e["brain"], e.get("rate", -1.0)
                    parent_lineage, source = e.get("lineage", -1.0), e.get("id", -1)
                else:
                    slot = living[best - n_hall]
                    gen, brain, parent_rate = int(P.generation[slot]), P.brain(slot), float(rate[best - n_hall])
                    parent_lineage, source = float(P.lineage[slot]), -1
                brain, mutations, lineage = self.mutate_child(brain, parent_rate, parent_lineage)
                origin, gen = "copy", gen + 1
            else:
                brain, gen = self._random_brain(draw), 0
            npc = self._spawn(brain, self.world.random_cell(draw), cfg.npc_start_mass, gen)
            npc.origin, npc.mutations, npc.parent_rate = origin, mutations, parent_rate
            npc.lineage, npc.source = lineage, source
            self.stats.count("spawns")
