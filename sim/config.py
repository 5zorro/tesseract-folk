"""Every tunable number lives here so experiments are reproducible.

Rule of thumb: if you find yourself typing a magic number in the sim code,
add it to Config instead.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields


@dataclass
class Config:
    # --- world shape -------------------------------------------------------
    dims: int = 2                 # 2 for the prototype, 4 for 4D Miner
    size: int = 32                # cells per axis; the world wraps around
    seed: int = 0

    # --- food & nutrients --------------------------------------------------
    n_food_types: int = 3
    n_nutrients: int = 3
    food_capacity: float = 2.0            # max food of one type in one cell
    # How much grows outside patches. 0 since 2026-11-02 (5zorro): with food scent,
    # NPCs should seek out patches, not graze a thin layer everywhere (was 0.05).
    food_baseline_fraction: float = 0.0
    food_patches_per_type: int = 3        # each food type has its own regions
    food_patch_radius: float = 4.0
    food_growth_rate: float = 0.02
    soil_half_saturation: float = 0.5     # growth slows as soil runs out
    nutrition_per_bite: float = 0.15
    # A patch's "zone" (M2 travel metrics) is its core: cells whose capacity for
    # that food is at least this fraction of food_capacity. Measurement only.
    zone_core: float = 0.5
    # "separate": each food type has its own patches. "shared": M2's control,
    # where every type grows in the same patches, so diet needs no travel.
    food_layout: str = "separate"

    # --- conserved mass loop: soil -> food -> body -> bowel -> poop -> soil -
    initial_soil_per_cell: float = 1.0
    initial_food_fraction: float = 0.5
    poop_decompose_rate: float = 0.01
    # Poop and soil spread to neighbor cells (plan-m3 slice S3b, 5zorro
    # 2026-11-08): NPCs eat in the rich patch cores and poop everywhere, so the
    # cores lose their soil and food stops regrowing there (the boom-and-crash
    # in plan-m3 S3). 0-1, the same mix with the neighbor mean as stink's, but
    # moved as pairwise exact transfers so mass is conserved. 0 = off.
    poop_diffusion: float = 0.0
    soil_diffusion: float = 0.1          # default since 2026-11-08 (5zorro; plan-m3 S3b)

    # --- stink (a signal, not mass) ----------------------------------------
    stink_emission: float = 0.2           # per unit of poop per tick
    stink_diffusion: float = 0.3
    stink_decay: float = 0.05
    stink_threshold: float = 0.5          # above this, standing here hurts
    stink_damage: float = 0.02

    # --- food scent (a signal, not mass; M1 slice 6) -------------------------
    # Each food type has a smell that spreads farther than stink, so NPCs can
    # find patches they can't see. Fixed for a world's life: it changes the
    # brain's input size. Snapshots saved before it existed load with it off.
    food_scent: bool = True
    # Craving sense (M2 slice R8, 2026-11-06, 5zorro: "probably good"): one input
    # per axis, the scent gradient (the food gradient without food_scent) of the
    # food types rich in the NPC's lowest nutrient. A sense-only forager meets the
    # diet goals in 4D from today's senses, but brains don't learn the need x
    # gradient product; this hands them the product. Perception, not behavior:
    # the brain still decides whether to follow it. Changes the input size.
    craving_sense: bool = False
    # Mating sense (5zorro, 2026-11-06: "ideally they figure out how to mate in 4D
    # where it is harder to find population"; slice R9). 3 + dims inputs: I can
    # mate now (adult, body, health, off cooldown: cooldown isn't sensed
    # otherwise); a partner within reach is ready (signaled `mate`) and can mate;
    # and a pheromone (5zorro's idea): an NPC that signaled `mate` and can mate
    # calls, adding `pheromone_emission` to its cell each tick; the call spreads
    # and fades like stink, and NPCs sense its level here (s / (s + half)) and
    # its relative gradient per axis, like food scent. Only callers emit, so a
    # seeker on the move doesn't follow its own trail. Changes the input size.
    mate_sense: bool = False
    pheromone_emission: float = 0.1
    pheromone_diffusion: float = 0.3
    pheromone_decay: float = 0.02
    pheromone_half: float = 0.1
    scent_emission: float = 0.05          # per unit of food per tick
    scent_diffusion: float = 0.3          # 0-1; reach shrinks with dims, harmlessly (research §4)
    scent_decay: float = 0.01             # slower than stink, so it reaches farther
    scent_half: float = 1.0               # sensed level is s / (s + scent_half)
    # Meal scent (M2 slice 3f, 5zorro): only food beyond this amount per cell smells,
    # so crumbs at patch edges are silent and the smell leads to meals. 0 = all
    # food smells (before 2026-11-04); bite_size (0.2) = only more than a bite.
    scent_min_food: float = 0.0
    # Scent floor (MR2b, 2026-11-11): the nose's noise floor. The sensed gradient
    # is (s+ - s-) / (s+ + s- + floor), so it points uphill at any distance when
    # the floor is ~0 (the default: 1e-12 is always added) and fades out where the
    # scent is weaker than the floor, so far patches can't be smelled and memory
    # has a job. Perception only; the scent field itself is unchanged.
    scent_floor: float = 0.0

    # Two eat actions (5zorro, M2 slice 3f; built 2026-11-05): `eat_most` takes the
    # biggest pile here (most mass), `eat_need` the food that best fixes deficits
    # (the old `eat` rule, crumbs included). The brain chooses, instead of an
    # instinct that takes a crumb of the needed food beside a full meal. Adds one
    # brain output, so it's fixed for a world's life and pools must match.
    two_eat_actions: bool = True          # default since 2026-11-06 (5zorro)
    # Outputs vs training time (5zorro, 2026-11-06: "the quantity of training time
    # vs the number of outputs"): switch off optional actions ("pray+worship";
    # moves, eating and poop can't be) or add do-nothing copies of `stay`, so the
    # number of brain outputs changes while the task doesn't. Fixed for a
    # world's life (they change the output size).
    actions_off: str = ""
    extra_stay_actions: int = 0

    # --- npc body ----------------------------------------------------------
    initial_npcs: int = 60
    min_population: int = 30              # below this, top up from hall of fame
    max_population: int = 250
    npc_start_mass: float = 1.0
    bite_size: float = 0.2
    carry_capacity: float = 1.0
    metabolism_rate: float = 0.01         # fraction of body mass -> bowel per tick
    bowel_capacity: float = 0.4           # over this, an "accident" happens
    nutrient_decay: float = 0.003         # was 0.004 until 2026-11-02 (5zorro: hunger slower, collapses harsher)
    idle_grace_ticks: int = 5             # standing still longer than this...
    idle_hunger_multiplier: float = 2.5   # ...makes hunger rise faster
    # Actions that change something (eating, picking up, giving, pooping, a birth,
    # worship at a shrine, an answered prayer, sharing) count as busy, like moving.
    # False = only moving resets the idle streak (before 2026-11-02).
    busy_resets_idle: bool = True
    satiation_gain: float = 0.35          # eating the same food gets less useful
    satiation_decay: float = 0.01
    starving_threshold: float = 0.1
    starvation_damage: float = 0.02
    heal_rate: float = 0.01
    min_body_mass: float = 0.3

    # --- aging & death -----------------------------------------------------
    adult_age: int = 300
    old_age: int = 1500                   # only elders can die permanently
    elder_decline: float = 0.01
    collapse_age_penalty: int = 300       # young NPCs collapse, respawn, age faster (was 150)
    collapse_health: float = 0.5          # health on waking up after a collapse
    collapse_nutrient_floor: float = 0.4  # nutrients are topped up to at least this

    # --- reproduction ------------------------------------------------------
    reproduce_min_mass: float = 1.2
    child_mass: float = 0.6               # paid half by each parent
    mate_window: int = 5
    mate_cooldown: int = 100

    # --- brains ------------------------------------------------------------
    hidden_units: int = 16
    memory_units: int = 2                 # tiny recurrent memory
    # Reaction queue (5zorro, plan-memory-reaction MR1, 2026-11-10): each NPC keeps
    # its last Q decided actions. Each tick it decides one and appends it, and
    # the oldest resolves, so an action takes effect Q ticks after it was chosen.
    # The pending queue is sensed (one-hots, oldest first) at the end of the
    # sense vector. Newborns start with "stay" queued. 0 = off (today's rule).
    reaction_queue: int = 0
    # Memory slots and the memory net (5zorro, plan-memory-reaction MR2, 2026-11-10):
    # each NPC has K slots (position, tick, the food there) that its forager senses,
    # and a second net on the same senses that each tick picks one of 2K + 1:
    # remember here in slot k (overwriting it), forget slot k, or nothing.
    # 0 = off. The memory net is inherited with the forager (sim/brain.py).
    memory_slots: int = 0
    memory_net_hidden: int = 8
    memory_tau: float = 500.0             # ticks: a memory's freshness is exp(-age / memory_tau)
    # A new memory net's chance to write or forget anything on a tick, set by its
    # "nothing" bias (a random net would otherwise write on ~16 of 17 ticks and
    # every slot would hold "here, just now"). Mutation can move it. Roughly: the
    # random weights' spread about doubles it (0.05 -> ~0.10 of ticks, 0.2 -> ~0.34;
    # measured 2026-11-10, 8 slots).
    memory_write_start: float = 0.05
    mutation_rate: float = 0.1            # chance per weight (ignored if mutations_per_birth > 0)
    # Mutations per birth (research slices R1-R4, 2026-11-04): > 0 sets the chance
    # per weight to this / the brain's weight count, so every brain size gets the
    # same number of mutated weights per child (the textbook "1/L rule" uses 1,
    # which lost here). 0 = use mutation_rate per weight (~100 per child in 2D at
    # 16 hidden units; the default before 2026-11-04, kept for old snapshots).
    # Per net: a memory net (memory_slots) gets its own budget (2026-11-11).
    mutations_per_birth: float = 30.0
    # Lineage-adaptive mutation (5zorro, slice R4; default since 2026-11-04): scale
    # mutations_per_birth by the ancestors' collapse rate relative to the
    # population's, so struggling lineages explore more and thriving ones less.
    # The ancestors' rate weighs parents 1/2, grandparents 1/4, and so on. The
    # factor stays within 1/mutation_lineage_max .. mutation_lineage_max (7.5-120
    # per child at the defaults). Needs mutations_per_birth > 0.
    mutation_lineage: bool = True
    mutation_lineage_max: float = 4.0
    mutation_scale: float = 0.3
    action_temperature: float = 0.5
    hall_of_fame_size: int = 20
    # Hall-of-fame track record (5zorro, research slice R5, 2026-11-04). One life is
    # a noisy score (slice R3), so with this on, each entry is scored by its own
    # life *and* every finished life of its copies: collapses per 1,000 ticks
    # above (+) or below (-) the population's at the time, averaged with
    # `hall_of_fame_prior_lives` average lives added, so a newcomer's one lucky life
    # can't outrank an entry proven over many. Copies are picked by that score too.
    # Floor: after `hall_of_fame_min_copies` copies (0 = never), an entry whose
    # copies average worse than the population is dropped. Off = rank by fitness.
    hall_of_fame_track_record: bool = True   # default since 2026-11-06 (5zorro)
    hall_of_fame_prior_lives: float = 3.0
    hall_of_fame_min_copies: int = 5
    # Birth bonus (5zorro, 2026-11-06; 0 = off): with the track record, a life's
    # score also counts its children: each birth per 1,000 ticks lived counts as
    # this many fewer collapses per 1,000 ticks. The old fitness weighed a child
    # as 5 collapses (500 vs 100). Without it, merit ignores children entirely.
    hall_of_fame_birth_weight: float = 0.0
    # Child credit (5zorro, 2026-11-06: "parents should not be out of the hall of
    # fame before the children's proof is in"; off = children don't count). A
    # child's finished life joins each parent's track record (the living parent's
    # tally, carried into its entry, or its entry if it died), and an entry with
    # children still alive can't be pushed out of the hall of fame or dropped.
    hall_of_fame_child_credit: bool = False
    # Trials (5zorro, 2026-11-06; sim/trials.py): a finished life is re-run as
    # this many exact clones (top-ups) before it may enter the hall of fame, and
    # enters only if `hall_of_fame_trial_passes` of its lives passed (at most
    # `hall_of_fame_trial_max_collapses` collapses; -1 = a collapse rate below the
    # population's) and `hall_of_fame_trial_parents` had children. 0 = off.
    hall_of_fame_trials: int = 0
    hall_of_fame_trial_passes: int = 2
    hall_of_fame_trial_max_collapses: int = -1
    hall_of_fame_trial_parents: int = 0
    # Crossover top-ups (5zorro, 2026-11-06): a top-up is the child of two
    # tournament winners (crossover, then mutation, as a birth), not a mutated
    # copy of one, so top-ups can combine good brains instead of only exploring
    # near one. Both parents' track records get its life. Off = copies.
    topup_crossover: bool = False
    # Research switch (M2 slice R10, 2026-11-06): a frozen hall of fame takes no
    # new entries, credits no copies and drops none, so a resumed nursery keeps
    # selecting from the entries it had (does hall-of-fame drift cause 4D's decay?).
    hall_of_fame_frozen: bool = False

    # --- deity, prayer, secrets --------------------------------------------
    n_shrines: int = 2
    secret_interval: int = 50
    secret_amount: float = 1.0            # mass pulled from soil into a hidden cache
    secret_lifetime: int = 400            # unclaimed secrets go stale
    max_secrets: int = 5
    worship_piety_gain: float = 0.05
    piety_threshold: float = 0.5
    prayer_piety_cost: float = 0.3
    # Off until NPCs survive hunger (5zorro, 2026-11-02): smiting caused ~70% of
    # collapses and hid the hunger problem. Re-enable for M5 (secrets).
    smiting: bool = False
    smite_threshold: float = 0.5
    smite_gain: float = 0.35
    smite_decay: float = 0.002
    smite_damage: float = 0.3
    prayer_cooldown: int = 30

    # --- occupations (docs/plan-occupations.md, O1) --------------------------
    # Posts with shifts: adults take free posts (lowest id first); a worker not
    # within reach of its post when its shift starts, or who leaves it, is walked
    # there by the code and arrives frazzled; a clean shift is paid a wage. 0 =
    # off. Changes the input size (work senses go last).
    n_posts: int = 0
    day_length: int = 300                 # ticks per day (an NPC lives ~1,500)
    shift_length: int = 100               # ticks per shift; post i starts at i x day / n_posts
    frazzled_ticks: int = 100             # how long the debuff lasts
    frazzled_hunger_multiplier: float = 1.5   # nutrient decay while frazzled
    frazzled_temperature: float = 2.0     # action temperature multiplier while frazzled
    wage: float = 0.4                     # food mass per clean shift (0 = unpaid), from the soil

    # --- stability (run_headless.py --until-stable; ROADMAP M3) ------------
    stable_window: int = 10               # stats samples to judge over
    stable_max_cv: float = 0.15           # population std / mean must stay below this
    stable_max_spawn_fraction: float = 0.1  # top-ups allowed per birth in the window

    # --- clock -------------------------------------------------------------
    # False: only aging pauses while the player is AFK (NPCs still live).
    # True: the whole world freezes while the player is AFK.
    freeze_all_when_afk: bool = False

    # --- numbers -----------------------------------------------------------
    # Width of the engine's floating-point arrays: "float64" (the reference
    # engine's, and every result so far) or "float32" (half the memory traffic;
    # being measured, docs/plan-gpu-backend.md D2). Only the array engine reads it.
    precision: str = "float64"
    # The rounding plug (5zorro's idea, 2026-11-06): every `mass_plug_every` ticks
    # (0 = off), the array engine compares total mass with the true total (kept
    # in float64) and posts the tiny difference to the median soil cell, like an
    # accountant's suspense entry. A difference above `mass_plug_max` of the
    # total isn't rounding: it raises, so a real conservation bug can't hide.
    mass_plug_every: int = 0
    mass_plug_max: float = 1e-5

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def check_sizes(self) -> None:
        """Raise ValueError if a count that sizes the sim's arrays is out of range.

        A shared snapshot's config sets these (docs/SAFETY.md §4), so a crafted
        one could otherwise make the sim allocate huge arrays before any other
        check runs. Both engines call this before building the world."""
        for name, (low, high) in SIZE_LIMITS.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"{name} must be a whole number within {low}-{high}, got {value!r}")
        if self.size ** self.dims > MAX_CELLS:
            raise ValueError(f"size ** dims is {self.size ** self.dims:,} cells; the limit is {MAX_CELLS:,}")


# Allowed ranges for the counts that size arrays (Config.check_sizes); generous,
# research uses far less. extra_stay_actions is capped in npc.build_actions.
SIZE_LIMITS = {
    "dims": (1, 6), "size": (2, 4096),
    "n_food_types": (1, 32), "n_nutrients": (1, 32), "food_patches_per_type": (0, 1024), "n_posts": (0, 1024),
    "hidden_units": (0, 1024), "memory_units": (0, 64), "reaction_queue": (0, 64),
    "memory_slots": (0, 64), "memory_net_hidden": (0, 1024),
    "initial_npcs": (0, 100_000), "max_population": (1, 100_000), "min_population": (0, 100_000),
    "hall_of_fame_size": (0, 10_000), "n_shrines": (0, 1024), "max_secrets": (0, 1024),
}
MAX_CELLS = 2 ** 22          # ~4.2M cells: 2D 2048 per axis, 4D 45 per axis


def parse_overrides(spec: str) -> dict:
    """'metabolism_rate=0.008,hidden_units=24' -> {'metabolism_rate': 0.008, 'hidden_units': 24}.

    Values take the type of the Config default, so typos fail loudly instead
    of being silently ignored by Config.from_dict.
    """
    defaults = Config()
    known = {f.name for f in fields(Config)}
    out = {}
    for item in filter(None, (s.strip() for s in spec.split(","))):
        key, sep, raw = (part.strip() for part in item.partition("="))
        if not sep:
            raise ValueError(f"expected key=value, got {item!r}")
        if key not in known:
            raise ValueError(f"unknown Config field {key!r}")
        kind = type(getattr(defaults, key))
        if kind is bool:
            if raw.lower() not in ("true", "false", "1", "0"):
                raise ValueError(f"{key} needs true/false, got {raw!r}")
            out[key] = raw.lower() in ("true", "1")
        else:
            out[key] = kind(raw)
    return out
