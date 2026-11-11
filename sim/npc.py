"""NPC state. Behavior lives in Simulation; this is just the data."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .brain import Brain

BASE_ACTIONS = ["stay", "eat", "pick_up", "give", "poop", "mate", "pray", "worship", "share"]

# Everything that can lower health. A collapse or death is blamed on whichever
# cause did the most damage since the NPC was last at full health.
DAMAGE_CAUSES = ["nutrient_starve", "body_starve", "stink", "smite", "elder"]


# Actions Config.actions_off may switch off (moves, eating and poop stay).
OPTIONAL_ACTIONS = ("stay", "pick_up", "give", "mate", "pray", "worship", "share")
MAX_EXTRA_STAY = 256


def build_actions(dims: int, two_eat_actions: bool = False, off: str = "", extra_stay: int = 0) -> list[str]:
    """Two moves per axis (so 4 in 2D, 8 in 4D), then everything else. With
    two_eat_actions, `eat` becomes `eat_most` and `eat_need`. `off` ("a+b")
    drops optional actions and `extra_stay` adds copies of `stay` named
    `stay1`, `stay2`... that do nothing (Config.actions_off, extra_stay_actions:
    research on outputs vs training time)."""
    moves = [f"move{sign}{axis}" for axis in range(dims) for sign in ("+", "-")]
    base = list(BASE_ACTIONS)
    if two_eat_actions:
        i = base.index("eat")
        base[i:i + 1] = ["eat_most", "eat_need"]
    drop = {name for name in off.split("+") if name}
    unknown = drop - set(OPTIONAL_ACTIONS)
    if unknown:
        raise ValueError(f"actions_off can only name {', '.join(OPTIONAL_ACTIONS)}; got {sorted(unknown)}")
    if not 0 <= extra_stay <= MAX_EXTRA_STAY:      # a shared snapshot's config sizes the arrays
        raise ValueError(f"extra_stay_actions must be within 0-{MAX_EXTRA_STAY}, got {extra_stay}")
    return moves + [a for a in base if a not in drop] + [f"stay{i}" for i in range(1, extra_stay + 1)]


def queue_fill(actions: list[str], queue_len: int) -> int:
    """The action a newborn's reaction queue starts with ("stay"); Config.reaction_queue
    needs it, so it can't be turned off with actions_off then."""
    if queue_len and "stay" not in actions:
        raise ValueError("reaction_queue needs the stay action (newborns start with it queued)")
    return actions.index("stay") if "stay" in actions else 0


def slot_inputs(cfg) -> int:
    """Senses per NPC for Config.memory_slots: per slot, filled, direction (dims),
    freshness and the remembered food per type."""
    return cfg.memory_slots * (2 + cfg.dims + cfg.n_food_types)


def memory_net_shape(cfg, n_inputs: int) -> tuple | None:
    """The memory net's (inputs, hidden, outputs): the forager's senses in, one
    output per choice (remember in slot k, forget slot k, nothing); None if off."""
    k = cfg.memory_slots
    return (n_inputs, cfg.memory_net_hidden, 2 * k + 1) if k else None


def check_memory_settings(cfg) -> None:
    if not (np.isfinite(cfg.memory_tau) and cfg.memory_tau > 0):
        raise ValueError(f"memory_tau must be a number > 0, got {cfg.memory_tau!r}")
    if not 0 < cfg.memory_write_start < 1:
        raise ValueError(f"memory_write_start must be within 0-1 (exclusive), got {cfg.memory_write_start!r}")


def random_memory_net(cfg, n_inputs: int, draw) -> Brain:
    """A new memory net whose "nothing" output starts biased so it writes or
    forgets on about memory_write_start of its ticks."""
    net = Brain.random(*memory_net_shape(cfg, n_inputs), draw)
    r, choices = cfg.memory_write_start, 2 * cfg.memory_slots
    # Choices are sampled from logits / action_temperature, so the bias is scaled by it.
    net.b2[-1] = cfg.action_temperature * np.log((1 - r) / r * choices)
    return net


def checked_action(choice, n_actions: int) -> int:
    """A controller's choice as an action index, or ValueError (a bad index would
    fail mid-tick or, if negative, silently wrap)."""
    if isinstance(choice, (bool, np.bool_)) or not isinstance(choice, (int, np.integer)):
        raise ValueError(f"a controller must return an action index or None, got {choice!r}")
    if not 0 <= int(choice) < n_actions:
        raise ValueError(f"a controller's action {int(choice)} is out of range (0-{n_actions - 1})")
    return int(choice)


def check_queue(queue: np.ndarray, n_actions: int, who) -> None:
    """A queue a controller may have rewritten: every entry a valid action index."""
    if queue.size and not ((queue >= 0) & (queue < n_actions)).all():
        raise ValueError(f"NPC {who}: a queued action is out of range (0-{n_actions - 1})")


def _whole(values, ndim: int, who, name: str) -> np.ndarray:
    a = np.asarray(values, dtype=float)
    if a.ndim != ndim and not (a.size == 0 and ndim == 2):
        raise ValueError(f"NPC {who}: {name} has the wrong shape")
    if not (np.isfinite(a).all() and (a == np.round(a)).all()):
        raise ValueError(f"NPC {who}: {name} must hold whole numbers")
    return a.astype(np.int64).reshape(a.shape if a.ndim == ndim else (0, 0))


def write_slot(npc, k: int, pos, tick: int, food) -> None:
    """Fill memory slot k of an NPC (a record or a view): a cell, the tick, and the
    food there per type (/ food_capacity). Used by the memory net and by
    controllers (the LLM pawn, later occupations) through write_memory."""
    npc.mem_pos[k] = pos
    npc.mem_tick[k] = tick
    npc.mem_food[k] = food
    npc.mem_filled[k] = True


def clear_slot(npc, k: int) -> None:
    npc.mem_pos[k] = 0
    npc.mem_tick[k] = 0
    npc.mem_food[k] = 0.0
    npc.mem_filled[k] = False


@dataclass
class NPC:
    id: int
    pos: tuple[int, ...]
    brain: Brain
    body: float
    nutrients: np.ndarray
    satiation: np.ndarray
    inventory: np.ndarray
    memory: np.ndarray
    generation: int = 0
    bowel: float = 0.0
    health: float = 1.0
    age: int = 0
    lifetime: int = 0
    piety: float = 0.0
    smite: float = 0.0
    idle_streak: int = 0
    moved_last: bool = False
    mate_ready_until: int = -1
    mate_cooldown_until: int = 0
    last_prayer: int = -10**9
    known_secret: int | None = None
    offspring: int = 0
    collapses: int = 0
    gifts_given: int = 0
    gifts_received: int = 0
    alive: bool = True
    eaten: np.ndarray = field(default=None)  # per food type, reset each stats window
    damage: dict = field(default_factory=dict)  # cause -> damage since last at full health
    # M2 travel: zones (food type, patch index) it has eaten in this lifetime,
    # the zone of its last in-zone bite, and how often that zone changed.
    zones_eaten: set = field(default_factory=set)
    last_zone: tuple | None = None
    zone_switches: int = 0
    # M2 slice 3b, summed over switches: did the new zone serve the nutrient it
    # was lowest on (hits), and how often would a random nutrient be served (chance)?
    directed_hits: float = 0.0
    directed_chance: float = 0.0
    # Move-based (slice 3c), over moves made outside its needed food's zones:
    # summed (cells closer to the needed food) - (mean cells closer to the others),
    # and the same for a random step from each of those cells (the null).
    approach_sum: float = 0.0
    approach_null: float = 0.0
    approach_moves: int = 0
    # Mutation bookkeeping (research slice R3): how this NPC's brain was made
    # ("birth", "copy" = a hall-of-fame top-up or seeded copy, "" = not recorded),
    # how many weights were mutated (expected count; -1 = none), and its parents'
    # collapse rate per 1,000 ticks when it was made (-1 = unknown).
    origin: str = ""
    mutations: float = -1.0
    parent_rate: float = -1.0
    # Ancestors' collapse rate when it was made: parents 1/2, grandparents 1/4...
    # (-1 = unknown). Drives lineage-adaptive mutation (Config.mutation_lineage).
    lineage: float = -1.0
    # The hall-of-fame entry this copy was made from (-1 = none), so its finished
    # life can be added to that entry's track record.
    source: int = -1
    source2: int = -1         # a crossover top-up's second parent entry (Config.topup_crossover)
    # Birth parents' ids (-1 = not born), and for Config.hall_of_fame_child_credit:
    # this NPC's children still alive, and its finished children's lives and
    # summed collapse excess (carried into its hall-of-fame entry).
    parent1: int = -1
    parent2: int = -1
    kids_alive: int = 0
    kid_lives: float = 0.0
    kid_excess_sum: float = 0.0
    trial_of: int = -1        # the hall-of-fame candidate this clone is a trial of (Config.hall_of_fame_trials)
    # Config.reaction_queue: actions decided but not yet resolved, oldest first
    # (indices into the world's actions). Empty when the queue is off.
    queue: np.ndarray = field(default=None)
    # Config.memory_slots (MR2): per slot, the remembered cell, the tick it was
    # written, the food there (per type, / food_capacity) and whether it's in use.
    mem_pos: np.ndarray = field(default=None)
    mem_tick: np.ndarray = field(default=None)
    mem_food: np.ndarray = field(default=None)
    mem_filled: np.ndarray = field(default=None)

    def __post_init__(self):
        if self.eaten is None:
            self.eaten = np.zeros_like(self.inventory)
        if self.queue is None:
            self.queue = np.zeros(0, dtype=np.int64)
        if self.mem_pos is None:
            self.mem_pos = np.zeros((0, len(self.pos)), dtype=np.int64)
            self.mem_tick = np.zeros(0, dtype=np.int64)
            self.mem_food = np.zeros((0, len(self.inventory)))
            self.mem_filled = np.zeros(0, dtype=bool)

    def take_damage(self, cause: str, amount: float) -> None:
        self.health -= amount
        self.damage[cause] = self.damage.get(cause, 0.0) + amount

    def main_damage_cause(self) -> str:
        return max(self.damage, key=self.damage.get) if self.damage else "unknown"

    def fitness(self) -> float:
        """Used only to pick parents when topping up the population.

        Keep this simple and avoid rewarding specific behaviors (like trading)
        directly; the point is to see whether those emerge on their own.
        """
        return self.offspring * 500.0 + self.lifetime - self.collapses * 100.0

    def collapse_rate(self) -> float:
        """Collapses per 1,000 ticks lived. Comparable between finished and
        ongoing lives, unlike lifetime or fitness."""
        return 1000.0 * self.collapses / max(self.lifetime, 1)

    def record_zone(self, zone: tuple, still_in_last: bool) -> bool:
        """A bite eaten inside `zone` (food type, patch index). True if it's a
        switch: a different zone from the last in-zone bite, after leaving that
        one. `still_in_last` says whether this cell is inside the last zone too,
        so eating another food where two zones overlap isn't counted as travel."""
        self.zones_eaten.add(zone)
        switched = self.last_zone is not None and zone != self.last_zone and not still_in_last
        self.zone_switches += switched
        self.last_zone = zone
        return switched

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "brain"}
        for k, v in d.items():
            if isinstance(v, np.ndarray):
                d[k] = v.tolist()
        d["pos"] = list(self.pos)
        d["zones_eaten"] = sorted(list(z) for z in self.zones_eaten)
        d["last_zone"] = list(self.last_zone) if self.last_zone is not None else None
        d["brain"] = self.brain.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "NPC":
        d = dict(data)
        d["brain"] = Brain.from_dict(d["brain"])
        d["pos"] = tuple(d["pos"])
        for k in ("nutrients", "satiation", "inventory", "memory", "eaten"):
            d[k] = np.asarray(d[k], dtype=float)
        queue = np.asarray(d.get("queue", []), dtype=float)   # absent before MR1 (2026-11-10)
        if queue.ndim != 1 or not (np.isfinite(queue).all() and (queue == np.round(queue)).all()):
            raise ValueError(f"NPC {d.get('id')}: queue must be a list of whole numbers")
        d["queue"] = queue.astype(np.int64)
        if "mem_pos" in d:                                     # absent before MR2 (2026-11-10)
            d["mem_pos"] = _whole(d["mem_pos"], 2, d.get("id"), "mem_pos")
            d["mem_tick"] = _whole(d["mem_tick"], 1, d.get("id"), "mem_tick")
            d["mem_food"] = np.asarray(d["mem_food"], dtype=float)
            d["mem_filled"] = np.asarray(d["mem_filled"], dtype=bool)
            if d["mem_pos"].size == 0:                         # JSON's [] loses the row width
                d["mem_pos"] = d["mem_pos"].reshape(0, len(d["pos"]))
            if d["mem_food"].size == 0:
                d["mem_food"] = d["mem_food"].reshape(0, len(d["inventory"]))
            if d["mem_food"].ndim != 2 or d["mem_filled"].ndim != 1:
                raise ValueError(f"NPC {d.get('id')}: memory slots have the wrong shape")
        d["zones_eaten"] = {tuple(z) for z in d.get("zones_eaten", [])}   # absent before M2
        if d.get("last_zone") is not None:
            d["last_zone"] = tuple(d["last_zone"])
        npc = cls(**d)
        npc.check_finite()
        return npc

    def check_finite(self) -> None:
        """Raise ValueError if any number is NaN or infinite. Snapshots may be
        shared (docs/SAFETY.md §4), and JSON loads NaN happily; a NaN lineage, for
        one, would fully mutate every child and spread to its descendants."""
        for name, value in self.__dict__.items():
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)):
                ok = np.isfinite(value)
            elif isinstance(value, np.ndarray):
                ok = np.isfinite(value).all()
            elif isinstance(value, dict):
                ok = all(np.isfinite(v) for v in value.values())
            else:
                continue
            if not ok:
                raise ValueError(f"NPC {self.id}: {name} holds a NaN or infinite number")
