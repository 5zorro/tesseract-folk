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

    # --- conserved mass loop: soil -> food -> body -> bowel -> poop -> soil -
    initial_soil_per_cell: float = 1.0
    initial_food_fraction: float = 0.5
    poop_decompose_rate: float = 0.01

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
    scent_emission: float = 0.05          # per unit of food per tick
    scent_diffusion: float = 0.3
    scent_decay: float = 0.01             # slower than stink, so it reaches farther
    scent_half: float = 1.0               # sensed level is s / (s + scent_half)

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
    mutation_rate: float = 0.1
    mutation_scale: float = 0.3
    action_temperature: float = 0.5
    hall_of_fame_size: int = 20

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

    # --- stability (run_headless.py --until-stable; ROADMAP M3) ------------
    stable_window: int = 10               # stats samples to judge over
    stable_max_cv: float = 0.15           # population std / mean must stay below this
    stable_max_spawn_fraction: float = 0.1  # top-ups allowed per birth in the window

    # --- clock -------------------------------------------------------------
    # False: only aging pauses while the player is AFK (NPCs still live).
    # True: the whole world freezes while the player is AFK.
    freeze_all_when_afk: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


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
