"""Every NPC's state as arrays (struct of arrays), one row ("slot") per NPC.

The array engine (simulation.py) works on whole columns at once. Scripts,
controllers and tests keep using NPC-shaped objects: `NPCView` reads and
writes one slot through the same attribute names as `npc.NPC`, the plain
record used for snapshots and for the reference engine (reference.py).

Slots are reused after deaths, so slot order means nothing; results never
depend on it (tests/test_tick_rules.py).
"""
from __future__ import annotations

import numpy as np

from .brain import Brain
from .npc import DAMAGE_CAUSES, NPC

# Scalar columns: name -> dtype. Every NPC field that's a plain number or bool.
SCALARS = {
    "id": np.int64, "body": np.float64, "generation": np.int64, "bowel": np.float64,
    "health": np.float64, "age": np.int64, "lifetime": np.int64, "piety": np.float64,
    "smite": np.float64, "idle_streak": np.int64, "moved_last": np.bool_,
    "mate_ready_until": np.int64, "mate_cooldown_until": np.int64, "last_prayer": np.int64,
    "offspring": np.int64, "collapses": np.int64, "gifts_given": np.int64,
    "gifts_received": np.int64, "alive": np.bool_, "zone_switches": np.int64,
    "directed_hits": np.float64, "directed_chance": np.float64, "approach_sum": np.float64,
    "approach_null": np.float64, "approach_moves": np.int64, "mutations": np.float64,
    "parent_rate": np.float64, "lineage": np.float64, "source": np.int64,
}
VECTORS = ("nutrients", "satiation", "inventory", "memory", "eaten")   # float rows
BRAIN = ("w1", "b1", "w2", "b2")
ORIGINS = ["", "birth", "copy"]
CAUSE = {c: i for i, c in enumerate(DAMAGE_CAUSES)}
# Within one tick, damage is taken in this order (smiting comes from praying,
# before metabolism; then metabolism's causes in its order). Used to rebuild a
# damage dict's insertion order, which picks the main cause when two tie.
_CAUSE_RANK = {"smite": 0, "nutrient_starve": 1, "body_starve": 2, "stink": 3, "elder": 4}


class Population:
    def __init__(self, capacity: int, dims: int, sizes: dict, brain_shape: tuple, patches: int,
                 dtype=np.float64):
        """sizes: row length of each VECTORS column; brain_shape: (n_in, hidden, n_out);
        dtype: the width of every float column."""
        self.dims, self.sizes, self.brain_shape, self.patches = dims, dict(sizes), brain_shape, patches
        self.float = np.dtype(dtype).type
        self.capacity = 0
        self._alloc(max(int(capacity), 1))

    # ------------------------------------------------------------ storage
    def _shapes(self) -> dict:
        n_in, hidden, n_out = self.brain_shape
        types = self.sizes["inventory"]
        f = self.float
        shapes = {name: ((), f if dtype is np.float64 else dtype) for name, dtype in SCALARS.items()}
        shapes.update({name: ((self.sizes[name],), f) for name in VECTORS})
        shapes.update(pos=((self.dims,), np.int64), known_secret=((), np.int64),
                      last_zone=((2,), np.int64), origin=((), np.int64),
                      damage=((len(DAMAGE_CAUSES),), f),
                      damage_seq=((len(DAMAGE_CAUSES),), np.int64),   # 0 = cause absent
                      zones_eaten=((types, self.patches), np.bool_),
                      world=((), np.int64),          # which world of a batch (not an NPC field)
                      w1=((hidden, n_in), f), b1=((hidden,), f),
                      w2=((n_out, hidden), f), b2=((n_out,), f))
        return shapes

    def _alloc(self, capacity: int) -> None:
        old, old_cap = {k: getattr(self, k) for k in self._shapes()} if self.capacity else {}, self.capacity
        for name, (shape, dtype) in self._shapes().items():
            arr = np.zeros((capacity,) + shape, dtype=dtype)
            if name in old:
                arr[:old_cap] = old[name]
            setattr(self, name, arr)
        self.capacity = capacity

    def live(self, world: int | None = None) -> np.ndarray:
        """Used slots (of one world, if given)."""
        return np.flatnonzero(self.alive if world is None else self.alive & (self.world == world))

    def count(self, world: int | None = None) -> int:
        return int(np.count_nonzero(self.alive if world is None else self.alive & (self.world == world)))

    def clear(self, world: int | None = None) -> None:
        if world is None:
            self.alive[:] = False
        else:
            self.alive[self.world == world] = False

    # ---------------------------------------------------- records in and out
    def add(self, npc: NPC, world: int = 0) -> int:
        """Store a record in the lowest free slot (growing if full); returns the slot."""
        free = np.flatnonzero(~self.alive)
        if free.size == 0:
            self._alloc(self.capacity * 2)
            free = np.flatnonzero(~self.alive)
        slot = int(free[0])
        for name in SCALARS:
            getattr(self, name)[slot] = getattr(npc, name)
        for name in VECTORS:
            getattr(self, name)[slot] = getattr(npc, name)
        self.pos[slot] = npc.pos
        self.known_secret[slot] = -1 if npc.known_secret is None else npc.known_secret
        self.last_zone[slot] = (-1, -1) if npc.last_zone is None else npc.last_zone
        self.origin[slot] = ORIGINS.index(npc.origin)
        self.set_damage(slot, npc.damage)
        self.zones_eaten[slot] = False
        for t, z in npc.zones_eaten:
            self.zones_eaten[slot, t, z] = True
        self.set_brain(slot, npc.brain)
        self.world[slot] = world
        self.alive[slot] = npc.alive
        return slot

    def record(self, slot: int) -> NPC:
        """A detached NPC record with this slot's state (copies, not views)."""
        v = NPCView(self, slot)
        data = {name: getattr(v, name) for name in SCALARS}
        data.update({name: getattr(self, name)[slot].copy() for name in VECTORS})
        data.update(pos=v.pos, brain=v.brain, known_secret=v.known_secret, last_zone=v.last_zone,
                    origin=v.origin, damage=v.damage, zones_eaten=v.zones_eaten)
        return NPC(**data)

    def brain(self, slot: int) -> Brain:
        return Brain(*(getattr(self, k)[slot].copy() for k in BRAIN))

    def set_brain(self, slot: int, brain: Brain) -> None:
        for k, a in zip(BRAIN, brain._arrays()):
            getattr(self, k)[slot] = a

    def damage_dict(self, slot: int) -> dict:
        seq = self.damage_seq[slot]
        present = [i for i in range(len(DAMAGE_CAUSES)) if seq[i] > 0]
        present.sort(key=lambda i: seq[i])
        return {DAMAGE_CAUSES[i]: float(self.damage[slot, i]) for i in present}

    def set_damage(self, slot: int, damage: dict) -> None:
        self.damage[slot] = 0.0
        self.damage_seq[slot] = 0
        for order, (cause, amount) in enumerate(damage.items(), start=1):
            self.damage[slot, CAUSE[cause]] = amount
            self.damage_seq[slot, CAUSE[cause]] = order      # loaded dicts keep their order

    def add_damage(self, slots: np.ndarray, cause: str, amounts, tick: int) -> None:
        """Damage several slots at once (each slot once): health falls, and a cause
        new since full health is stamped so it sorts after older causes."""
        i = CAUSE[cause]
        self.health[slots] -= amounts
        self.damage[slots, i] += amounts
        new = slots[self.damage_seq[slots, i] == 0]
        self.damage_seq[new, i] = 1_000 + 16 * tick + _CAUSE_RANK[cause]

    def main_damage_cause(self, slot: int) -> str:
        d = self.damage_dict(slot)
        return max(d, key=d.get) if d else "unknown"


class NPCView:
    """One slot of a Population, with NPC's attribute names. Number fields
    read back as Python scalars; nutrients, inventory and the other rows are
    views (writes go through); brain, damage and zones_eaten are copies (set
    them whole).

    A view belongs to one NPC: once that NPC's slot is reused (it died and a
    newcomer took the slot), using the view raises instead of quietly reading
    the newcomer. Keep ids, not views, across ticks."""

    __slots__ = ("_pop", "_slot", "_id")

    def __init__(self, pop: Population, slot: int):
        object.__setattr__(self, "_pop", pop)
        object.__setattr__(self, "_slot", int(slot))
        object.__setattr__(self, "_id", int(pop.id[slot]))

    def _check(self):
        if self._pop.id[self._slot] != self._id:
            raise LookupError(f"NPC {self._id} is gone (its slot now holds NPC {int(self._pop.id[self._slot])})")
        return self._pop, self._slot

    def __getattr__(self, name):
        pop, s = self._check()
        if name in SCALARS:
            return getattr(pop, name)[s].item()
        if name in VECTORS:
            return getattr(pop, name)[s]
        if name == "pos":
            return tuple(int(v) for v in pop.pos[s])
        if name == "known_secret":
            k = int(pop.known_secret[s])
            return None if k < 0 else k
        if name == "last_zone":
            t, z = (int(v) for v in pop.last_zone[s])
            return None if t < 0 else (t, z)
        if name == "origin":
            return ORIGINS[int(pop.origin[s])]
        if name == "damage":
            return pop.damage_dict(s)
        if name == "zones_eaten":
            return {(int(t), int(z)) for t, z in np.argwhere(pop.zones_eaten[s])}
        if name == "brain":
            return pop.brain(s)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        pop, s = self._check()
        if name in SCALARS or name in VECTORS or name == "pos":
            getattr(pop, name)[s] = value
        elif name == "known_secret":
            pop.known_secret[s] = -1 if value is None else value
        elif name == "last_zone":
            pop.last_zone[s] = (-1, -1) if value is None else value
        elif name == "origin":
            pop.origin[s] = ORIGINS.index(value)
        elif name == "damage":
            pop.set_damage(s, value)
        elif name == "zones_eaten":
            pop.zones_eaten[s] = False
            for t, z in value:
                pop.zones_eaten[s, t, z] = True
        elif name == "brain":
            pop.set_brain(s, value)
        else:
            raise AttributeError(f"NPC has no field {name!r}")

    def __eq__(self, other):
        return isinstance(other, NPCView) and other._pop is self._pop and other._id == self._id

    def __hash__(self):
        return hash((id(self._pop), self._id))

    def __repr__(self):
        return f"NPCView(id={self._id}, slot={self._slot})"

    # The record's methods, reading through the view.
    fitness = NPC.fitness
    collapse_rate = NPC.collapse_rate

    def take_damage(self, cause: str, amount: float) -> None:
        """Single-NPC damage outside the tick's batches (e.g. smiting from a
        prayer): stamped like add_damage would with the current tick unknown,
        so it's given rank order within this NPC's existing causes."""
        pop, s = self._check()
        pop.health[s] -= amount
        i = CAUSE[cause]
        pop.damage[s, i] += amount
        if pop.damage_seq[s, i] == 0:
            pop.damage_seq[s, i] = int(pop.damage_seq[s].max()) + 1

    def main_damage_cause(self) -> str:
        return self._pop.main_damage_cause(self._check()[1])

    def record_zone(self, zone: tuple, still_in_last: bool) -> bool:
        rec = self._pop.record(self._check()[1])
        switched = rec.record_zone(zone, still_in_last)
        self.zones_eaten, self.zone_switches, self.last_zone = (
            rec.zones_eaten, rec.zone_switches, rec.last_zone)
        return switched

    def to_dict(self) -> dict:
        return self._pop.record(self._check()[1]).to_dict()

    def check_finite(self) -> None:
        self._pop.record(self._check()[1]).check_finite()
