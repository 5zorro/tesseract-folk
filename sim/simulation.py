"""The core tick loop, as array operations over every NPC of many worlds at once.

The tick rules (docs/plan-gpu-backend.md, G1): every NPC senses the world as it
was at the start of the tick and decides; then the chosen actions resolve in
fixed phases (moves; eats and pick-ups; give, mate, share; the rest), then
everyone's metabolism, then deaths and collapses. Within a phase NPCs go in
priority order, a fresh keyed draw each tick (lowest first). All randomness is
keyed (sim/keyed.py).

Two classes (G3):
- `Simulation` is one world: its config, map, deity, stats, hall of fame and
  NPCs (as views). Everything outside this file talks to it.
- `Batch` steps many worlds in one set of arrays: their maps are stacked on a
  leading world axis, their NPCs share one Population (sim/population.py) with
  a world column, and numeric settings become per-world arrays, so a sweep's
  variants x seeds run as one. A lone `Simulation(cfg)` is a batch of one.
  Worlds in a batch must share the settings that shape arrays (STRUCTURAL).
  Stepping any of them steps them all.

reference.py states the same rules one NPC at a time. tests/test_engines.py
checks that a batch of one matches it exactly (G2), and that a mixed batch
matches its worlds run alone (G3). A rule change goes into both engines.

Exactness: where several NPCs add to one cell in a phase, the additions run in
priority order (np.add.at keeps index order), as the reference does them one
by one. Eaters sharing a cell take turns in rounds: the first of every cell,
then the second, and so on. Worlds never share a cell.

Invariant: total mass (soil + food + poop + secret caches + everything NPCs
carry in body, bowel and inventory) never changes. tests/test_simulation.py
checks this. If you add a mechanic, keep it true.
"""
from __future__ import annotations

from dataclasses import fields

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

# Settings that shape arrays, actions or senses: equal within a batch.
STRUCTURAL = ("dims", "size", "n_food_types", "n_nutrients", "hidden_units", "memory_units",
              "food_scent", "two_eat_actions", "food_patches_per_type", "precision")
PRECISIONS = {"float64": np.float64, "float32": np.float32}
# World arrays stacked by a batch (each World keeps a view of its row).
WORLD_ARRAYS = ("soil", "food", "poop", "stink", "scent", "capacity", "zones", "need_distance", "profiles")


def action_phase(name: str) -> int:
    return 0 if name.startswith("move") else _PHASES.get(name, 3)


class Simulation:
    """One world. Its NPC arrays and map live in `self.batch`."""

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
        if c.precision not in PRECISIONS:
            raise ValueError(f"precision must be one of {sorted(PRECISIONS)}, got {c.precision!r}")
        self.hall_of_fame: list[dict] = []   # see nursery.hall_of_fame_entry for the fields
        self.overrides: dict[int, object] = {}  # npc id -> controller (see controllers.py)
        self.next_id = 0
        self.batch: Batch | None = None
        self.index = 0                       # this world's row in its batch
        Batch([self])
        if populate:
            for _ in range(self.cfg.initial_npcs):
                draw = self.keys.stream(0, self.next_id, keyed.INIT)
                self._spawn(self._random_brain(draw), self.world.random_cell(draw),
                            self.cfg.npc_start_mass, generation=0)

    # ============================================================ the NPCs
    @property
    def pop(self) -> Population:
        return self.batch.pop

    @property
    def tick(self) -> int:
        return self.batch.tick

    @tick.setter
    def tick(self, value: int) -> None:
        if len(self.batch.sims) > 1:
            raise ValueError("worlds in a batch share one clock; set the tick before batching")
        self.batch.tick = value

    @property
    def npcs(self) -> list[NPCView]:
        """This world's living NPCs as views, by id (writes go into the arrays)."""
        return [NPCView(self.pop, s) for s in self._by_id(self.pop.live(self.index))]

    @npcs.setter
    def npcs(self, npcs: list) -> None:
        """Replace this world's NPCs with these records (or views); dead ones are dropped."""
        records = [n if isinstance(n, NPC) else self.pop.record(n._check()[1]) for n in npcs]
        self.pop.clear(self.index)
        for r in records:
            if r.alive:
                self.pop.add(r, self.index)
        self.batch.mass_target[self.index] = np.nan     # mass may have changed: re-read it

    def _slot(self, npc) -> int:
        if (not isinstance(npc, NPCView) or npc._pop is not self.pop
                or self.pop.world[npc._slot] != self.index):
            raise TypeError("expected one of this simulation's NPCs (from sim.npcs)")
        return npc._check()[1]

    def _slots(self, npcs) -> np.ndarray:
        return np.array([self._slot(n) for n in npcs], dtype=np.int64)

    def _by_id(self, slots: np.ndarray) -> np.ndarray:
        return slots[np.argsort(self.pop.id[slots], kind="stable")]

    def set_rule(self, name: str, value) -> None:
        """Change a numeric rule of this world mid-run (e.g. a nursery that raises
        hunger as it goes). Rules that shape the arrays (STRUCTURAL) or aren't
        numbers can't change once a world exists."""
        current = getattr(self.cfg, name)            # AttributeError for unknown names
        if name in STRUCTURAL or isinstance(current, str) or name not in self.batch.par:
            raise ValueError(f"{name} can't change mid-run")
        value = type(current)(value)
        setattr(self.cfg, name, value)
        self.batch.par[name][self.index] = value

    def world_changed(self) -> None:
        """Call after writing this world's arrays in place (snapshots do): derived
        tables (which cells serve which nutrient, shrine senses) are rebuilt."""
        self.world._serves_zones = None
        self.batch.refresh(self.index)
        self.batch.mass_target[self.index] = np.nan

    # ============================================================ public API
    def step(self) -> bool:
        """Advance one tick (of every world in this batch). Returns False if time
        is frozen (player AFK)."""
        return self.batch.step()

    def run(self, ticks: int) -> None:
        self.batch.run(ticks)

    def fast_forward(self, ticks: int) -> None:
        """The player turns the clock: run with aging forced on."""
        self.clock.turn(ticks)
        self.run(ticks)

    def total_mass(self) -> float:
        P, live = self.pop, self._by_id(self.pop.live(self.index))
        f = np.float64                      # float32 arrays are summed in float64 too
        each = P.body[live].astype(f) + P.bowel[live].astype(f) + P.inventory[live].astype(f).sum(axis=1)
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

    def sensor_size(self) -> int:
        c = self.cfg
        t, n, d, m = c.n_food_types, c.n_nutrients, c.dims, c.memory_units
        scent = t + d * t if c.food_scent else 0
        return (n + 4 + t + t + d * t + 1 + d + 1 + t + 2
                + 1 + d + d + 1 + 1 + m + 1 + scent)

    def sense_layout(self) -> dict[str, slice]:
        """Where each part of the sense vector sits (the order of reference.sense).
        Gradients are axis-major: axis 0's food types, then axis 1's..."""
        c = self.cfg
        t, n, d, m = c.n_food_types, c.n_nutrients, c.dims, c.memory_units
        parts = [("nutrients", n), ("health", 1), ("age", 1), ("body", 1), ("bowel", 1),
                 ("satiation", t), ("food_here", t), ("food_grad", d * t), ("stink_here", 1),
                 ("stink_grad", d), ("neighbors", 1), ("inventory", t), ("piety", 1), ("smite", 1),
                 ("secret", 1 + d), ("shrine", d + 1), ("moved", 1), ("memory", m), ("bias", 1)]
        if c.food_scent:
            parts += [("scent_here", t), ("scent_grad", d * t)]
        out, at = {}, 0
        for name, size in parts:
            out[name] = slice(at, at + size)
            at += size
        assert at == self.n_inputs, (at, self.n_inputs)
        return out

    # ================================ the reference's single-NPC helpers (tests)
    def sense(self, npc, index=None) -> np.ndarray:
        """One NPC's senses (`index` is ignored; kept for the reference's signature)."""
        return self.batch.sense_slots(np.array([self._slot(npc)]))[0]

    def _spatial_index(self) -> None:
        return None

    def _act(self, npc, action: int, index=None, births: list | None = None) -> None:
        lists = [[] for _ in self.batch.sims]
        if births is not None:
            lists[self.index] = births
        with self.batch.outside_tick():
            self.batch.resolve(np.array([self._slot(npc)]), np.array([action]), lists)

    def _eat(self, npc, rule: str = "need") -> bool:
        slot = np.array([self._slot(npc)])
        flat = self.world.flat(self.pop.pos[slot])
        return bool(self.batch._eat_slots(slot, flat, np.array([rule == "most"]))[0])

    def metabolize(self, npcs: list, aging: bool) -> None:
        """Everyone's metabolism first, then the fallen (health gone) in this order."""
        slots = self._slots([n for n in npcs if n.alive])
        with self.batch.outside_tick():
            self.batch._metabolize(slots, np.full(len(self.batch.sims), aging))
            self.batch._fall(slots)

    def _die(self, npc) -> None:
        self.batch._die_slot(self._slot(npc))

    def _collapse(self, npc) -> None:
        self.batch._collapse_slot(self._slot(npc))

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
        if not self.batch.stepping:                       # added from outside a tick (not a top-up)
            self.batch.mass_target[self.index] = np.nan
        return NPCView(self.pop, self.pop.add(self._make_npc(brain, pos, body, generation), self.index))

    def plug_mass(self) -> None:
        """The rounding plug (Config.mass_plug_every): post the difference between
        the true total and today's to the median soil cell, or raise if it's too
        big to be rounding."""
        target = self.batch.mass_target[self.index]
        now = self.total_mass()
        if np.isnan(target):
            self.batch.mass_target[self.index] = now
            return
        diff = target - now
        if abs(diff) > self.cfg.mass_plug_max * abs(target):
            raise RuntimeError(
                f"world {self.index} (seed {self.cfg.seed}), tick {self.tick}: mass is off by "
                f"{diff:+.3g} ({diff / target:+.2e} of {target:.6g}); that's not rounding but a "
                f"conservation bug (mass_plug_max {self.cfg.mass_plug_max:g})")
        if diff:
            # The median of the cells that can absorb the entry. Not the median of
            # all cells: once a boom has emptied most of the soil, that one holds
            # ~0, a negative entry made it negative, and growth's soil / (soil +
            # half_saturation) blew up and leaked 2.5e-5 of all mass in one tick
            # (anneal nursery, 3D, tick 27,402; 2026-11-06).
            soil = self.world.soil.reshape(-1)
            able = np.flatnonzero(soil > 10 * abs(diff))
            if not able.size:
                raise RuntimeError(f"world {self.index}, tick {self.tick}: no soil cell can absorb "
                                   f"the rounding entry {diff:+.3g}")
            cell = int(able[np.argsort(soil[able], kind="stable")[able.size // 2]])
            soil[cell] += diff
            self.stats.mass_plugged += diff
            self.stats.mass_plugs += 1

    def population_collapse_rate(self) -> float:
        """Collapses per 1,000 ticks lived, over everyone alive (weighted by
        time lived, so newborns' noisy rates barely count). During a tick,
        "alive" means alive when the tick began, as in the reference."""
        P, present = self.pop, self.batch.present
        slots = (present[P.world[present] == self.index] if present is not None
                 else P.live(self.index))
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
        if cfg.hall_of_fame_track_record:
            for source in (npc.source, npc.source2):
                if source >= 0:
                    self._credit_source(source, excess)
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
        while P.count(self.index) < cfg.min_population:
            body = self.world.take_from_soil(cfg.npc_start_mass)
            if not body:
                break
            track = cfg.hall_of_fame_track_record
            population = self.population_collapse_rate() if track else -1.0
            living = self._by_id(P.live(self.index))
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
            origin, mutations, parent_rate, lineage, source, source2 = "", -1.0, -1.0, -1.0, -1, -1
            draw = self.keys.stream(self.tick, self.next_id, keyed.SPAWN)

            def parent(i: int) -> tuple:
                """(generation, brain, collapse rate, lineage, entry id) of candidate i."""
                if i < n_hall:
                    e = self.hall_of_fame[i]
                    return (e["generation"], e["brain"], e.get("rate", -1.0),
                            e.get("lineage", -1.0), e.get("id", -1))
                slot = living[i - n_hall]
                return (int(P.generation[slot]), P.brain(slot), float(rate[i - n_hall]),
                        float(P.lineage[slot]), -1)

            if scores:
                picks = [draw.integers(len(scores)) for _ in range(3)]
                best = max(picks, key=lambda i: scores[i])         # the first best, like max()
                gen, brain, parent_rate, parent_lineage, source = parent(best)
                if cfg.topup_crossover and len(scores) > 1:
                    # A second tournament among the others, then a birth's recipe.
                    picks = [int(draw.integers(len(scores) - 1)) for _ in range(3)]
                    picks = [i + (i >= best) for i in picks]
                    gen2, brain2, rate2, lineage2, source2 = parent(max(picks, key=lambda i: scores[i]))
                    brain = Brain.crossover(brain, brain2, self.keys.stream(self.tick, self.next_id,
                                                                            keyed.CROSSOVER))
                    rates = [r for r in (parent_rate, rate2) if r >= 0]
                    known = [x for x in (parent_lineage, lineage2) if x >= 0]
                    parent_rate = sum(rates) / len(rates) if rates else -1.0
                    parent_lineage = sum(known) / len(known) if known else -1.0
                    gen, origin = max(gen, gen2), "cross"
                brain, mutations, lineage = self.mutate_child(brain, parent_rate, parent_lineage)
                origin, gen = origin or "copy", gen + 1
            else:
                brain, gen = self._random_brain(draw), 0
            npc = self._spawn(brain, self.world.random_cell(draw), body, gen)
            npc.origin, npc.mutations, npc.parent_rate = origin, mutations, parent_rate
            npc.lineage, npc.source, npc.source2 = lineage, source, source2
            self.stats.count("spawns")


class _OutsideTick:
    """Lets a single-NPC helper run between ticks as if inside one."""

    def __init__(self, batch: "Batch"):
        self.batch, self.set = batch, False

    def __enter__(self):
        if self.batch.present is None:
            self.batch.present, self.set = self.batch.pop.live(), True

    def __exit__(self, *exc):
        if self.set:
            self.batch.present = None


class Batch:
    """Many worlds stepped together (G3). Build the Simulations first (seed their
    brains, load snapshots...), then `Batch([sim, ...])`; afterwards each
    Simulation reads and writes the batch's arrays."""

    def __init__(self, sims: list[Simulation]):
        if not sims:
            raise ValueError("a batch needs at least one world")
        first = sims[0]
        for s in sims[1:]:
            differ = [k for k in STRUCTURAL if getattr(s.cfg, k) != getattr(first.cfg, k)]
            if differ:
                raise ValueError(f"worlds in a batch must share {', '.join(differ)}")
        ticks = {s.batch.tick if s.batch else 0 for s in sims}
        if len(ticks) > 1:
            raise ValueError(f"worlds in a batch must be at the same tick, got {sorted(ticks)}")
        self.sims = list(sims)
        self.tick = ticks.pop()
        W = self.W = len(sims)
        cfg = first.cfg
        self.dims, self.size, self.types = cfg.dims, cfg.size, cfg.n_food_types
        self.food_scent = cfg.food_scent
        self.cells = cfg.size ** cfg.dims
        self.float = PRECISIONS[cfg.precision]
        records = [[s.pop.record(slot) for slot in s._by_id(s.pop.live(s.index))] if s.batch else []
                   for s in sims]
        # Stack the maps; each World keeps a view of its row, so its own methods
        # (food_at, mass, take_from_soil...) write into the batch.
        for name in WORLD_ARRAYS:
            stacked = np.stack([getattr(s.world, name) for s in sims])
            if stacked.dtype.kind == "f":
                stacked = stacked.astype(self.float)
            setattr(self, name, stacked)
            for i, s in enumerate(sims):
                setattr(s.world, name, stacked[i])
        self.seeds = np.array([s.cfg.seed for s in sims], dtype=np.int64)
        self.par = {f.name: np.array([getattr(s.cfg, f.name) for s in sims])
                    for f in fields(Config) if not isinstance(getattr(cfg, f.name), str)}
        for name, values in self.par.items():       # float settings at the arrays' width,
            if values.dtype.kind == "f":             # so they don't widen float32 math
                self.par[name] = values.astype(self.float)
        capacity = sum(max(s.cfg.max_population, s.cfg.initial_npcs, s.cfg.min_population) + 1 for s in sims)
        self.pop = Population(
            capacity, cfg.dims,
            {"nutrients": cfg.n_nutrients, "satiation": self.types, "inventory": self.types,
             "memory": cfg.memory_units, "eaten": self.types},
            (first.n_inputs, cfg.hidden_units, first.n_outputs), cfg.food_patches_per_type, self.float,
            world_size=cfg.size)
        for i, (s, recs) in enumerate(zip(sims, records)):
            for r in recs:
                self.pop.add(r, i)
            s.batch, s.index = self, i
        self.actions = first.actions
        self.n_actions = first.n_actions
        self._phase = np.array([action_phase(a) for a in self.actions])
        self._act_index = {name: i for i, name in enumerate(self.actions)}
        self._nbr = first.world.neighbor_table()                   # (cells, 2 * dims), same for all
        self._serves = np.stack([s.world.serves_table().reshape(cfg.n_nutrients, -1) for s in sims])
        self._shrine = np.zeros((W, self.cells, cfg.dims + 1), dtype=self.float)
        self._shrines_cached: list = [None] * W
        self._aging = np.ones(W, dtype=bool)
        self.mass_target = np.full(W, np.nan)     # true total mass per world (the plug's ledger)
        self.stepping = False                     # inside step(): mass moves are the rules' own
        self.present: np.ndarray | None = None    # slots alive at the tick's start

    def refresh(self, i: int) -> None:
        """Rebuild world i's derived tables (its arrays were written in place)."""
        w = self.sims[i].world
        self._serves[i] = w.serves_table().reshape(self._serves.shape[1], -1)
        self._shrines_cached[i] = None

    def outside_tick(self) -> _OutsideTick:
        return _OutsideTick(self)

    def _p(self, name: str, wn: np.ndarray) -> np.ndarray:
        """A setting per NPC (wn: each NPC's world)."""
        return self.par[name][wn]

    def _pw(self, name: str, extra: int) -> np.ndarray:
        """A setting per world, shaped to broadcast over (worlds, ...extra axes)."""
        return self.par[name].reshape((self.W,) + (1,) * extra)

    def _flat(self, positions: np.ndarray) -> np.ndarray:
        return np.ravel_multi_index(tuple(positions.T), (self.size,) * self.dims)

    def _count(self, name: str, wn: np.ndarray) -> None:
        """Count one event per entry of wn into each world's stats."""
        if wn.size:
            for w, k in enumerate(np.bincount(wn, minlength=self.W).tolist()):
                if k:
                    self.sims[w].stats.count(name, k)

    # ================================================================ tick
    def run(self, ticks: int) -> None:
        for _ in range(ticks):
            self.step()

    def step(self) -> bool:
        """Advance every world one tick. Returns False if time is frozen (player AFK)."""
        frozen = [s.cfg.freeze_all_when_afk and not s.clock.aging_active for s in self.sims]
        if any(frozen):
            if not all(frozen):
                raise ValueError("worlds in a batch must freeze together (freeze_all_when_afk)")
            return False
        self._aging = np.array([s.clock.aging_active for s in self.sims])
        self.stepping = True
        try:
            self._step()
        finally:
            self.stepping = False
        return True

    def _step(self) -> None:
        for s in self.sims:                       # the plug's starting totals
            if s.cfg.mass_plug_every > 0 and np.isnan(self.mass_target[s.index]):
                s.plug_mass()
        self.tick += 1
        self._world_step()
        for s in self.sims:
            s.deity.step(self.tick, s.world, s.keys, s.stats)

        order = self._priority_order()
        self.present = order
        actions = self.decide_all(order)
        births: list[list[NPC]] = [[] for _ in self.sims]
        self.resolve(order, actions, births)
        self._metabolize(order, self._aging)
        self._fall(order)
        self.present = None
        for i, children in enumerate(births):
            for child in children:
                self.pop.add(child, i)
        for s in self.sims:
            s._top_up()
            if s.cfg.mass_plug_every > 0 and self.tick % s.cfg.mass_plug_every == 0:
                s.plug_mass()
            s.clock.consume_tick()
            s.stats.maybe_sample(s)

    # Cells per pass of the world step: about one 4D map (10,000 cells) at a time
    # stays in the CPU's cache even with 16 processes sharing it. Measured
    # 2026-11-05, 4D world step per world with 16 processes: 3.05 ms at 40,000
    # cells per pass, 1.39 ms at 10,000 (1.08-1.22 ms alone either way).
    WORLD_STEP_CELLS = 10_000

    def _world_step(self) -> None:
        """World.step for every world (same operations, per-world settings), a
        cache-sized group of worlds at a time; worlds don't interact here."""
        chunk = max(1, self.WORLD_STEP_CELLS // self.cells)
        for lo in range(0, self.W, chunk):
            self._world_step_part(slice(lo, min(lo + chunk, self.W)))

    def _world_step_part(self, part: slice) -> None:
        d = self.dims
        n = part.stop - part.start
        sp = lambda name: self.par[name][part].reshape((n,) + (1,) * d)          # noqa: E731
        tp = lambda name: self.par[name][part].reshape((n,) + (1,) * (d + 1))    # noqa: E731
        food, soil, poop, stink = self.food[part], self.soil[part], self.poop[part], self.stink[part]

        # Food grows toward its capacity, pulling mass out of the soil.
        room = np.clip(self.capacity[part] - food, 0.0, None)
        soil_factor = soil / (soil + sp("soil_half_saturation"))
        growth = tp("food_growth_rate") * room * soil_factor[:, None]
        total = growth.sum(axis=1)
        scale = np.minimum(1.0, soil / np.maximum(total, 1e-12))
        growth *= scale[:, None]
        # Exact transfers, as in World.step: the giver loses what the receiver gained.
        before = food.copy()
        food += growth
        soil -= (food - before).sum(axis=1)

        # Poop slowly becomes soil again (fertilizer) and emits stink.
        decomposed = poop * sp("poop_decompose_rate")
        before = soil.copy()
        soil += decomposed
        poop -= soil - before
        stink += poop * sp("stink_emission")

        # Stink spreads to neighbors and fades.
        stink += sp("stink_diffusion") * (self._neighbor_mean(stink, 1) - stink)
        stink *= 1.0 - sp("stink_decay")

        # Food smells beyond `scent_min_food`; the smell spreads the same way but
        # fades slower, so it reaches farther.
        if self.food_scent:
            scent = self.scent[part]
            scent += np.maximum(food - tp("scent_min_food"), 0.0) * tp("scent_emission")
            scent += tp("scent_diffusion") * (self._neighbor_mean(scent, 2) - scent)
            scent *= 1.0 - tp("scent_decay")

    def _neighbor_mean(self, field: np.ndarray, first_axis: int) -> np.ndarray:
        """World._neighbor_mean on stacked fields (spatial axes from first_axis on):
        the same sum of the same rolls in the same order, added in place slice by
        slice instead of building each rolled copy."""
        total = np.zeros_like(field)
        for axis in range(first_axis, first_axis + self.dims):
            for shift in (1, -1):              # np.roll(field, shift, axis), added to total
                head, tail = [slice(None)] * field.ndim, [slice(None)] * field.ndim
                if shift == 1:                 # out[1:] = in[:-1]; out[0] = in[-1]
                    head[axis], tail[axis] = slice(1, None), slice(None, -1)
                    total[tuple(head)] += field[tuple(tail)]
                    head[axis], tail[axis] = slice(0, 1), slice(-1, None)
                    total[tuple(head)] += field[tuple(tail)]
                else:                          # out[:-1] = in[1:]; out[-1] = in[0]
                    head[axis], tail[axis] = slice(None, -1), slice(1, None)
                    total[tuple(head)] += field[tuple(tail)]
                    head[axis], tail[axis] = slice(-1, None), slice(0, 1)
                    total[tuple(head)] += field[tuple(tail)]
        return total / (2 * self.dims)

    # =============================================================== senses
    def sense_slots(self, slots: np.ndarray) -> np.ndarray:
        """Senses of these slots, one row each, from the worlds as they are now."""
        P, d, T, W, C = self.pop, self.dims, self.types, self.W, self.cells
        n = slots.size
        wn = P.world[slots]
        flat = self._flat(P.pos[slots])
        nbr = self._nbr[flat]                                   # (n, 2d): +1, -1 per axis
        g, gn = wn * C + flat, wn[:, None] * C + nbr            # cells across all worlds
        food = self.food.reshape(W, T, C)
        food_cap = self._p("food_capacity", wn)
        food_n = food[wn[:, None], :, nbr]                      # (n, 2d, types)
        food_grad = ((food_n[:, 0::2] - food_n[:, 1::2]) / food_cap[:, None, None]
                     ).reshape(n, d * T)                        # axis by axis, every type
        stink = self.stink.reshape(-1)
        stink_n = stink[gn]
        # Others in the same cell or one step away.
        live = P.live()
        occupied = np.bincount(P.world[live] * C + self._flat(P.pos[live]), minlength=W * C)
        crowd = occupied[g] + occupied[gn].sum(axis=1) - 1

        half = self.size / 2
        secret = np.zeros((n, 1 + d))
        for i in np.flatnonzero(P.known_secret[slots] >= 0).tolist():
            s = self.sims[wn[i]].deity.secrets.get(int(P.known_secret[slots[i]]))
            if s is None:                                       # gone stale or claimed
                P.known_secret[slots[i]] = -1
            else:
                secret[i, 0] = 1.0
                secret[i, 1:] = wrapped_delta(P.pos[slots[i]], s.pos, self.size) / half

        parts = [
            P.nutrients[slots],
            np.stack([P.health[slots], np.minimum(P.age[slots] / self._p("old_age", wn), 1.5),
                      P.body[slots] / self._p("npc_start_mass", wn),
                      P.bowel[slots] / self._p("bowel_capacity", wn)], axis=1),
            P.satiation[slots],
            food[wn, :, flat] / food_cap[:, None],
            food_grad,
            stink[g][:, None],
            stink_n[:, 0::2] - stink_n[:, 1::2],
            np.minimum(crowd / 4.0, 1.0)[:, None],
            P.inventory[slots] / self._p("carry_capacity", wn)[:, None],
            np.stack([P.piety[slots], P.smite[slots]], axis=1),
            secret,
            self._shrines()[wn, flat],
            P.moved_last[slots].astype(float)[:, None],
            P.memory[slots],
            np.ones((n, 1)),
        ]
        if self.food_scent:
            scent = self.scent.reshape(W, T, C)
            here = scent[wn, :, flat]
            scent_n = scent[wn[:, None], :, nbr]
            s_plus, s_minus = scent_n[:, 0::2], scent_n[:, 1::2]
            # Relative difference: points uphill at any distance, like a nose.
            parts += [here / (here + self._p("scent_half", wn)[:, None]),
                      ((s_plus - s_minus) / (s_plus + s_minus + 1e-12)).reshape(n, d * T)]
        obs = np.concatenate(parts, axis=1, dtype=self.float)
        assert obs.shape == (n, self.sims[0].n_inputs), obs.shape
        return obs

    def _shrines(self) -> np.ndarray:
        """Per world and cell: direction to the nearest shrine and whether it's on
        one ((worlds, cells, dims + 1); a world's rows are rebuilt when its shrines
        change). Ties go to the first shrine in the list, as in the reference."""
        d, size = self.dims, self.size
        for i, s in enumerate(self.sims):
            shrines = s.world.shrines
            if self._shrines_cached[i] == shrines:
                continue
            cells = np.indices((size,) * d).reshape(d, -1).T          # (cells, dims)
            table = np.zeros((cells.shape[0], d + 1))
            if shrines:
                deltas = (np.array(shrines)[:, None, :] - cells[None] + size // 2) % size - size // 2
                nearest = deltas[np.abs(deltas).sum(axis=2).argmin(axis=0), np.arange(cells.shape[0])]
                table[:, :d] = nearest / (size / 2)
                table[:, d] = (~nearest.any(axis=1)).astype(float)
            self._shrine[i] = table
            self._shrines_cached[i] = list(shrines)
        return self._shrine

    # ============================================================== thinking
    def _priority_order(self) -> np.ndarray:
        """The living slots by world, then lowest priority draw first (ties,
        practically never, by id). Every phase of the tick goes in this order."""
        P = self.pop
        live = P.live()
        if not live.size:
            return live
        ids, wn = P.id[live], P.world[live]
        prio = keyed.uniform(self.seeds[wn], self.tick, ids, keyed.ORDER)
        return live[np.lexsort((ids, prio, wn))]

    def decide_all(self, order: np.ndarray) -> np.ndarray:
        """Rule 1: everyone senses the start-of-tick world and picks an action
        (an index into actions). Deciding changes only each NPC's own memory.
        (5zorro's reaction-time queue would hand `resolve` actions decided
        earlier instead; docs/plan-gpu-backend.md.)"""
        if not order.size:
            return np.zeros(0, dtype=np.int64)
        P, A = self.pop, self.n_actions
        wn = P.world[order]
        obs = self.sense_slots(order)
        u = keyed.uniform(self.seeds[wn], self.tick, P.id[order], keyed.ACTION)
        hidden = (np.tanh(np.matmul(P.w1[order], obs[:, :, None])[:, :, 0] + P.b1[order])
                  if P.w1.shape[1] else obs)                 # 0 hidden units: linear brain
        out = np.matmul(P.w2[order], hidden[:, :, None])[:, :, 0] + P.b2[order]
        logits = out[:, :A] / self._p("action_temperature", wn)[:, None]
        logits -= logits.max(axis=1, keepdims=True)
        probs = np.exp(logits)
        probs /= probs.sum(axis=1, keepdims=True)
        # The way NumPy's rng.choice(p=probs) samples (one uniform draw against the
        # cumulative sum), with each NPC's keyed draw `u`.
        cdf = probs.cumsum(axis=1)
        cdf /= cdf[:, -1:]
        actions = (cdf <= u[:, None]).sum(axis=1)
        brained = np.ones(order.size, dtype=bool)
        if any(s.overrides for s in self.sims):
            for i, slot in enumerate(order.tolist()):
                sim = self.sims[wn[i]]
                controller = sim.overrides.get(int(P.id[slot])) if sim.overrides else None
                if controller is not None:
                    actions[i] = controller.decide(sim, NPCView(P, slot), obs[i])
                    brained[i] = False
        P.memory[order[brained]] = np.tanh(out[brained, A:])
        return actions

    # =============================================================== actions
    def resolve(self, order: np.ndarray, actions: np.ndarray, births: list[list[NPC]]) -> None:
        """Rules 2-3: actions take effect phase by phase, in priority order."""
        P = self.pop
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
        busy = moved | (did & self._p("busy_resets_idle", P.world[order]))
        P.idle_streak[order] = np.where(busy, 0, P.idle_streak[order] + 1)

    def _moves(self, slots: np.ndarray, actions: np.ndarray) -> None:
        P = self.pop
        before = P.pos[slots].copy()
        rows = np.arange(slots.size)
        axis = actions // 2                         # moves are move+0, move-0, move+1, ...
        after = before.copy()
        after[rows, axis] = (after[rows, axis] + np.where(actions % 2 == 0, 1, -1)) % self.size
        P.pos[slots] = after
        self._record_approach(slots, self._flat(before), self._flat(after))
        wn = P.world[slots]
        for w in np.unique(wn).tolist():
            sim = self.sims[w]
            if sim.deity.secrets:
                cells = {tuple(int(v) for v in p) for p in after[wn == w]}
                claimed = sim.deity.claim_cells(cells, sim.world)
                if claimed:
                    sim.stats.count("secrets_claimed", claimed)

    def _record_approach(self, slots: np.ndarray, before: np.ndarray, after: np.ndarray) -> None:
        """M2 slice 3c: did this move head for the food the NPC needs most, more
        than for the others? Moves only, so the eat instinct can't leak in."""
        P = self.pop
        k = self.need_distance.shape[1]
        wn = P.world[slots]
        need = np.argmin(P.nutrients[slots], axis=1)
        rows = np.arange(slots.size)
        dist = self.need_distance.reshape(self.W, k, -1)
        here = dist[wn, :, before]                                     # (n, nutrients)
        others = np.isfinite(here)
        others[rows, need] = False
        ok = (~self._serves[wn, need, before]                         # not already at its food
              & np.isfinite(here[rows, need]) & others.any(axis=1))
        if not ok.any():
            return
        slots, wn, need, here, others = slots[ok], wn[ok], need[ok], here[ok], others[ok]
        rows = np.arange(slots.size)
        # Score the move taken, then every possible step from the same cell. Their
        # mean is what a random step scores. Not 0: a random walk drifts away from
        # near food faster than from far food (gotchas.md).
        cells = np.concatenate([after[ok][:, None], self._nbr[before[ok]]], axis=1)   # (n, steps)
        delta = (np.ascontiguousarray(dist[wn[:, None], :, cells].transpose(0, 2, 1))
                 - here[:, :, None])                                                   # (n, nutrients, steps)
        score = (np.where(others[:, :, None], delta, 0.0).sum(axis=1) / others.sum(axis=1)[:, None]
                 - delta[rows, need])
        P.approach_sum[slots] += score[:, 0]
        P.approach_null[slots] += score[:, 1:].sum(axis=1) / (score.shape[1] - 1)
        P.approach_moves[slots] += 1

    def _eats(self, slots: np.ndarray, actions: np.ndarray) -> np.ndarray:
        """Eaters and pick-uppers sharing a cell take turns in priority order: in
        round r, the r-th of every cell acts (different cells don't interact)."""
        P = self.pop
        flat = self._flat(P.pos[slots])
        cell = P.world[slots] * self.cells + flat
        by_cell = np.argsort(cell, kind="stable")       # stable: priority order within a cell
        sorted_cell = cell[by_cell]
        first = np.r_[True, sorted_cell[1:] != sorted_cell[:-1]]
        starts = np.maximum.accumulate(np.where(first, np.arange(cell.size), 0))
        turn = np.empty(cell.size, dtype=np.int64)
        turn[by_cell] = np.arange(cell.size) - starts
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

    def _eat_slots(self, slots: np.ndarray, flat: np.ndarray, most: np.ndarray) -> np.ndarray:
        """Eat a bite from the ground, else from the inventory. Per NPC, the food
        is the one that best fixes deficits per unit (crumbs count), or with
        `most` (eat_most) the biggest pile. One NPC per cell."""
        P = self.pop
        wn = P.world[slots]
        food = self.food.reshape(self.W, self.types, self.cells)
        rows = np.arange(slots.size)
        deficit = 1.0 - P.nutrients[slots]
        value = np.matmul(self.profiles[wn], deficit[:, :, None])[:, :, 0] * (1.0 - P.satiation[slots])
        here = food[wn, :, flat]                                # (n, types), a copy
        inventory = P.inventory[slots]
        ground = (here > 1e-9).any(axis=1)
        ate = ground | (inventory > 1e-9).any(axis=1)
        source = np.where(ground[:, None], here, inventory)
        score = np.where(most[:, None], source, value)
        t = np.argmax(np.where(source > 1e-9, score, -np.inf), axis=1)
        bite = self._p("bite_size", wn)
        amount = np.minimum(bite, source[rows, t])
        g = np.flatnonzero(ground)
        food[wn[g], t[g], flat[g]] -= amount[g]
        inv = np.flatnonzero(ate & ~ground)
        P.inventory[slots[inv], t[inv]] -= amount[inv]
        if g.size:
            self._record_zones(slots[g], flat[g], t[g])
        e = np.flatnonzero(ate)
        if not e.size:
            return ate
        s, t, amount, we = slots[e], t[e], amount[e], wn[e]
        frac = amount / bite[e]
        P.body[s] += amount
        P.nutrients[s] = np.clip(
            P.nutrients[s] + (frac * self._p("nutrition_per_bite", we))[:, None] * self.profiles[we, t]
            * (1.0 - P.satiation[s, t])[:, None], 0.0, 1.0)
        P.satiation[s, t] = np.minimum(1.0, P.satiation[s, t] + self._p("satiation_gain", we) * frac)
        P.eaten[s, t] += amount
        self._count("eats", we)
        if self.sims[0].cfg.two_eat_actions:
            self._count("eats_need", we[~most[e]])
            self._count("eats_most", we[most[e]])
        return ate

    def _record_zones(self, slots: np.ndarray, flat: np.ndarray, t: np.ndarray) -> None:
        """M2 travel: a bite from the ground inside a zone (food type, patch);
        a switch is a different zone from the last in-zone bite, after leaving
        it (eating another food where two zones overlap isn't travel)."""
        P = self.pop
        wn = P.world[slots]
        zones = self.zones.reshape(self.W, self.types, self.cells)
        zone = zones[wn, t, flat]
        inside = zone >= 0                              # carried food doesn't count: it isn't a place
        if not inside.any():
            return
        slots, wn, flat, t, zone = slots[inside], wn[inside], flat[inside], t[inside], zone[inside]
        last_t, last_z = P.last_zone[slots, 0], P.last_zone[slots, 1]
        has_last = last_t >= 0
        still = has_last & (zones[wn, np.maximum(last_t, 0), flat] == last_z)
        switched = has_last & ((t != last_t) | (zone != last_z)) & ~still
        P.zones_eaten[slots, t, zone] = True
        P.zone_switches[slots] += switched
        P.last_zone[slots, 0], P.last_zone[slots, 1] = t, zone
        if switched.any():
            self._count("zone_switches", wn[switched])
            # Deficit-directed travel (M2 slice 3b): judged by where it arrived,
            # not by what `eat` picked, since eat already chooses by deficit.
            s, f, ws = slots[switched], flat[switched], wn[switched]
            serves = self._serves[ws, :, f]                    # (n, nutrients)
            need = np.argmin(P.nutrients[s], axis=1)
            P.directed_hits[s] += serves[np.arange(s.size), need]
            P.directed_chance[s] += serves.mean(axis=1)

    def _pick_up(self, slots: np.ndarray, flat: np.ndarray) -> np.ndarray:
        P = self.pop
        wn = P.world[slots]
        food = self.food.reshape(self.W, self.types, self.cells)
        room = self._p("carry_capacity", wn) - P.inventory[slots].sum(axis=1)
        here = food[wn, :, flat]
        ok = ~(room <= 1e-9) & (here > 1e-9).any(axis=1)
        k = np.flatnonzero(ok)
        if k.size:
            t = np.argmax(here[k], axis=1)
            amount = np.minimum(np.minimum(self._p("bite_size", wn[k]), here[k, t]), room[k])
            food[wn[k], t, flat[k]] -= amount
            P.inventory[slots[k], t] += amount
        return ok

    # -------------------------------------------- social actions (few, in turn)
    def _social(self, slots: np.ndarray, actions: np.ndarray, births: list[list[NPC]]) -> np.ndarray:
        """give, mate and share, one NPC at a time in priority order. They see
        where everyone is after the moves."""
        P = self.pop
        live = P.live()
        index: dict[int, list[int]] = {}
        for slot, cell in zip(live.tolist(), (P.world[live] * self.cells + self._flat(P.pos[live])).tolist()):
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
        P = self.pop
        cell = int(self._flat(P.pos[slot][None])[0])
        base = int(P.world[slot]) * self.cells
        return [o for c in [cell, *self._nbr[cell].tolist()] for o in index.get(base + c, ()) if o != slot]

    def _give(self, slot: int, index: dict, births: list) -> bool:
        P = self.pop
        sim = self.sims[P.world[slot]]
        cfg = sim.cfg
        if P.inventory[slot].sum() <= 1e-9:
            return False
        cap = cfg.carry_capacity
        takers = sorted((o for o in self._neighbors(slot, index) if cap - P.inventory[o].sum() > 1e-9),
                        key=lambda o: P.id[o])            # by id: the pick mustn't depend on list order
        if not takers:
            return False
        other = takers[sim.keys.stream(self.tick, int(P.id[slot]), keyed.GIVE).integers(len(takers))]
        t = int(np.argmax(P.inventory[slot]))
        amount = min(cfg.bite_size, float(P.inventory[slot, t]), cap - float(P.inventory[other].sum()))
        P.inventory[slot, t] -= amount
        P.inventory[other, t] += amount
        P.gifts_given[slot] += 1
        P.gifts_received[other] += 1
        sim.stats.count("gives")
        return True

    def _can_mate(self, slot: int, cfg: Config) -> bool:
        P = self.pop
        return bool(P.alive[slot] and P.age[slot] >= cfg.adult_age and P.body[slot] >= cfg.reproduce_min_mass
                    and P.health[slot] > 0.5 and self.tick >= P.mate_cooldown_until[slot])

    def _rate(self, slot: int) -> float:
        """NPC.collapse_rate for a slot."""
        return 1000.0 * int(self.pop.collapses[slot]) / max(int(self.pop.lifetime[slot]), 1)

    def _mate(self, slot: int, index: dict, births: list[list[NPC]]) -> bool:
        """True only when a child is born; signaling readiness alone isn't busy."""
        P = self.pop
        w = int(P.world[slot])
        sim = self.sims[w]
        cfg = sim.cfg
        if not self._can_mate(slot, cfg):
            return False
        P.mate_ready_until[slot] = self.tick + cfg.mate_window
        if P.count(w) + len(births[w]) >= cfg.max_population:
            return False
        partners = sorted((o for o in self._neighbors(slot, index)
                           if P.mate_ready_until[o] >= self.tick and self._can_mate(o, cfg)),
                          key=lambda o: P.id[o])
        if not partners:
            return False
        mate = partners[sim.keys.stream(self.tick, int(P.id[slot]), keyed.MATE).integers(len(partners))]
        half = cfg.child_mass / 2
        P.body[slot] -= half
        P.body[mate] -= half
        child_id = sim.next_id                       # the child's draws are keyed by its id
        brain = Brain.crossover(P.brain(slot), P.brain(mate),
                                sim.keys.stream(self.tick, child_id, keyed.CROSSOVER))
        parent_rate = (self._rate(slot) + self._rate(mate)) / 2
        known = [float(P.lineage[p]) for p in (slot, mate) if P.lineage[p] >= 0]
        brain, mutations, lineage = sim.mutate_child(
            brain, parent_rate, sum(known) / len(known) if known else -1.0, key_id=child_id)
        child = sim._make_npc(brain, tuple(int(v) for v in P.pos[slot]), cfg.child_mass,
                              max(int(P.generation[slot]), int(P.generation[mate])) + 1)
        child.origin, child.mutations, child.parent_rate = "birth", mutations, parent_rate
        child.lineage = lineage
        births[w].append(child)
        for parent in (slot, mate):
            P.offspring[parent] += 1
            P.mate_ready_until[parent] = -1
            P.mate_cooldown_until[parent] = self.tick + cfg.mate_cooldown
        sim.stats.count("births")
        return True

    def _share(self, slot: int, index: dict, births: list) -> bool:
        P = self.pop
        sim = self.sims[P.world[slot]]
        sid = int(P.known_secret[slot])
        if sid < 0 or sid not in sim.deity.secrets:
            return False
        shared = 0
        for other in self._neighbors(slot, index):
            if P.known_secret[other] != sid:
                P.known_secret[other] = sid
                shared += 1
        if shared:
            sim.stats.count("secrets_shared", shared)
        return shared > 0

    def _rest(self, slots: np.ndarray, actions: np.ndarray) -> np.ndarray:
        """poop, pray, worship (and stay, which does nothing on purpose)."""
        P = self.pop
        wn = P.world[slots]
        flat = self._flat(P.pos[slots])
        did = np.zeros(slots.size, dtype=bool)
        poop = (actions == self._act_index["poop"]) & (P.bowel[slots] > 1e-9)
        if poop.any():
            s = slots[poop]
            np.add.at(self.poop.reshape(-1), wn[poop] * self.cells + flat[poop], P.bowel[s])  # priority order
            P.bowel[s] = 0.0
            self._count("poops", wn[poop])
            did[poop] = True
        names = {"answered": "prayers_answered", "silent": "prayers_silent",
                 "ignored": "prayers_ignored", "smitten": "smitings"}
        for i in np.flatnonzero(actions == self._act_index["pray"]).tolist():
            sim = self.sims[wn[i]]
            result = sim.deity.pray(NPCView(P, slots[i]), self.tick)
            sim.stats.count(names[result])
            did[i] = result == "answered"
        worship = actions == self._act_index["worship"]
        if worship.any():
            on = self._shrines()[wn, flat, self.dims] == 1.0      # standing on a shrine
            k = np.flatnonzero(worship & on)
            if k.size:
                P.piety[slots[k]] = np.minimum(1.0, P.piety[slots[k]] + self._p("worship_piety_gain", wn[k]))
                self._count("worships", wn[k])
                did[k] = True
        return did

    # ============================================================ metabolism
    def _metabolize(self, s: np.ndarray, aging: np.ndarray) -> None:
        """aging: per world, whether NPCs age this tick."""
        P, C = self.pop, self.cells
        if not s.size:
            return
        wn = P.world[s]
        p = lambda name: self._p(name, wn)          # noqa: E731
        g = wn * C + self._flat(P.pos[s])
        moved_mass = p("metabolism_rate") * P.body[s]
        before = P.bowel[s]
        P.bowel[s] = before + moved_mass
        P.body[s] -= P.bowel[s] - before       # exact transfer: what the bowel gained
        accident = P.bowel[s] >= p("bowel_capacity")
        if accident.any():
            a = s[accident]
            np.add.at(self.poop.reshape(-1), g[accident], P.bowel[a])     # in priority order
            P.bowel[a] = 0.0
            self._count("accidents", wn[accident])

        idle = P.idle_streak[s] > p("idle_grace_ticks")
        decay = p("nutrient_decay")
        decay = np.where(idle, decay * p("idle_hunger_multiplier"), decay * 1.0)
        # np.minimum/maximum: the same values as np.clip.
        P.nutrients[s] = np.minimum(np.maximum(P.nutrients[s] - decay[:, None], 0.0), 1.0)
        P.satiation[s] = np.minimum(np.maximum(P.satiation[s] - p("satiation_decay")[:, None], 0.0), 1.0)
        P.smite[s] = np.maximum(0.0, P.smite[s] - p("smite_decay"))

        P.lifetime[s] += 1
        pairs, counts = np.unique(np.stack([wn, P.generation[s]], axis=1), axis=0, return_counts=True)
        for (w, gen), k in zip(pairs.tolist(), counts.tolist()):
            self.sims[w].stats.generation_lifetime[gen] += k
        ages = aging[wn]
        P.age[s[ages]] += 1

        lowest = P.nutrients[s].min(axis=1)
        starving = lowest < p("starving_threshold")
        thin = P.body[s] < p("min_body_mass")
        stink = self.stink.reshape(-1)[g]
        stink_threshold = p("stink_threshold")
        stinky = stink > stink_threshold
        old = p("old_age")
        elder = P.age[s] > old
        starve = p("starvation_damage")
        # One cause at a time, in the reference's order, so health falls the same way.
        P.add_damage(s[starving], "nutrient_starve", starve[starving], self.tick)
        P.add_damage(s[thin], "body_starve", starve[thin], self.tick)
        P.add_damage(s[stinky], "stink", p("stink_damage")[stinky] * (stink[stinky] - stink_threshold[stinky]),
                     self.tick)
        P.add_damage(s[elder], "elder",
                     p("elder_decline")[elder] * (P.age[s[elder]] - old[elder]) / old[elder], self.tick)
        heal = ~(starving | thin | stinky | elder) & (lowest > 0.4)
        h = s[heal]
        P.health[h] = np.minimum(1.0, P.health[h] + p("heal_rate")[heal])
        whole = h[P.health[h] >= 1.0]
        P.damage[whole] = 0.0
        P.damage_seq[whole] = 0

    def _fall(self, slots: np.ndarray) -> None:
        """Health ran out: elders die, the young collapse (in priority order)."""
        P = self.pop
        for slot in slots[P.alive[slots] & (P.health[slots] <= 0)].tolist():
            if P.age[slot] >= self.sims[P.world[slot]].cfg.old_age:
                self._die_slot(slot)
            else:
                self._collapse_slot(slot)

    def _drop_inventory(self, slot: int) -> None:
        P = self.pop
        here = self.sims[P.world[slot]].world.food_at(tuple(int(v) for v in P.pos[slot]))
        here += P.inventory[slot]
        P.inventory[slot] = 0.0

    def _collapse_slot(self, slot: int) -> None:
        """Young NPCs can't die permanently. They collapse, drop what they
        carry, wake up somewhere else, and age faster for the trouble."""
        P = self.pop
        sim = self.sims[P.world[slot]]
        cfg = sim.cfg
        self._drop_inventory(slot)
        P.pos[slot] = sim.world.random_cell(sim.keys.stream(self.tick, int(P.id[slot]), keyed.COLLAPSE))
        P.health[slot] = cfg.collapse_health
        P.nutrients[slot] = np.maximum(P.nutrients[slot], cfg.collapse_nutrient_floor)
        P.age[slot] += cfg.collapse_age_penalty
        P.collapses[slot] += 1
        P.known_secret[slot] = -1
        P.last_zone[slot] = -1                 # waking up elsewhere isn't travel
        sim.stats.count("collapses")
        sim.stats.count(f"collapse_{P.main_damage_cause(slot)}")
        sim.stats.generation_collapses[int(P.generation[slot])] += 1
        P.damage[slot] = 0.0
        P.damage_seq[slot] = 0

    def _die_slot(self, slot: int) -> None:
        """Elders die for real. The body becomes poop (which stinks, then
        fertilizes), so the mass goes back into the loop."""
        P = self.pop
        sim = self.sims[P.world[slot]]
        self._drop_inventory(slot)
        sim.world.poop[tuple(int(v) for v in P.pos[slot])] += P.body[slot] + P.bowel[slot]
        P.body[slot] = P.bowel[slot] = 0.0
        P.alive[slot] = False
        npc = NPCView(P, slot)
        sim._record_hall_of_fame(npc)
        sim.stats.count("deaths")
        sim.stats.count(f"death_{P.main_damage_cause(slot)}")
        sim.stats.record_life(npc, self.tick)
