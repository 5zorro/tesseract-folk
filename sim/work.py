"""Occupations (docs/plan-occupations.md, O1): posts, shifts, the fallback walk,
the frazzled debuff and wages.

Shared by both engines. The rules run on NPC-like objects (the reference's
NPC records or the array engine's NPCViews); posts are few, so a loop over
workers is cheap. Senses and the walk step have array versions in
simulation.py that must match these exactly (tests/test_engines.py).

A day is `day_length` ticks; post i's shift starts at i x day / n_posts and
lasts `shift_length`. At a shift's first tick a worker within reach of its
post (its cell or one step away) is on time; one that isn't, or that leaves
during the shift, is walked there by the code and arrives frazzled. A shift
worked cleanly (on time, never walked) is paid at the first tick after it.
"""
from __future__ import annotations

import numpy as np

from . import keyed
from .world import wrapped_delta

WORK_COUNTERS = ("work_assigned", "work_on_time", "work_late", "work_left", "work_walk_ticks",
                 "work_paid")


def work_inputs(cfg) -> int:
    """Senses for Config.n_posts: has a post, on shift, time until the next
    shift starts (/ day), within reach, frazzled (/ frazzled_ticks), and the
    direction to the post (dims)."""
    return 5 + cfg.dims if cfg.n_posts else 0


def check_work_settings(cfg) -> None:
    if cfg.n_posts < 0:
        raise ValueError(f"n_posts must be >= 0, got {cfg.n_posts!r}")
    if not cfg.n_posts:
        return
    if cfg.day_length < 2:
        raise ValueError(f"day_length must be at least 2, got {cfg.day_length!r}")
    if not 0 < cfg.shift_length < cfg.day_length:     # a tick off shift is when wages are paid
        raise ValueError(f"shift_length must be within 1-{cfg.day_length - 1}, got {cfg.shift_length!r}")
    if cfg.frazzled_ticks < 0:
        raise ValueError(f"frazzled_ticks must be >= 0, got {cfg.frazzled_ticks!r}")
    for name, low in (("frazzled_hunger_multiplier", 0.0), ("wage", 0.0)):
        value = getattr(cfg, name)
        if not (np.isfinite(value) and value >= low):
            raise ValueError(f"{name} must be a number >= {low:g}, got {value!r}")
    if not (np.isfinite(cfg.frazzled_temperature) and cfg.frazzled_temperature > 0):
        raise ValueError(f"frazzled_temperature must be a number > 0, got {cfg.frazzled_temperature!r}")


def place_posts(cfg, world, keys) -> list[tuple[tuple, int]]:
    """Each post's cell (keyed, so it follows from the seed) and shift start."""
    return [(world.random_cell(keys.stream(0, i, keyed.POST)), i * cfg.day_length // cfg.n_posts)
            for i in range(cfg.n_posts)]


def check_worker(npc, n_posts: int) -> None:
    """A record's work fields (snapshots may be shared: docs/SAFETY.md section 4)."""
    post = int(npc.post)
    if not (post == -1 or 0 <= post < n_posts):
        raise ValueError(f"NPC {npc.id}: post {post} is out of range (this world has {n_posts})")
    if int(npc.frazzled) < 0:
        raise ValueError(f"NPC {npc.id}: frazzled must be >= 0")


def within_reach(pos, post, size: int) -> bool:
    return int(np.abs(wrapped_delta(pos, post, size)).sum()) <= 1


def walk_action(action_index: dict, pos, post, size: int) -> int:
    """One step of the fallback walk: along the axis with the farthest to go
    (the lowest such axis on a tie), toward the post."""
    delta = wrapped_delta(pos, post, size)
    axis = int(np.argmax(np.abs(delta)))
    return action_index[f"move{'+' if delta[axis] > 0 else '-'}{axis}"]


def sense(cfg, tick: int, npc, posts) -> np.ndarray:
    """The work senses of one NPC (see work_inputs)."""
    d = cfg.dims
    out = np.zeros(5 + d)
    if cfg.frazzled_ticks:
        out[4] = npc.frazzled / cfg.frazzled_ticks
    if npc.post >= 0:
        cell, start = posts[npc.post]
        delta = wrapped_delta(npc.pos, cell, cfg.size)
        out[0] = 1.0
        out[1] = 1.0 if (tick - start) % cfg.day_length < cfg.shift_length else 0.0
        out[2] = ((start - tick) % cfg.day_length) / cfg.day_length
        out[3] = 1.0 if np.abs(delta).sum() <= 1 else 0.0
        out[5:] = delta / (cfg.size / 2)
    return out


def assign(sim, free_posts: list[int], candidates: list) -> None:
    """Free posts, lowest first, to adults without one, lowest id first."""
    for k, npc in zip(free_posts, candidates):
        npc.post = k
        sim.stats.count("work_assigned")


def tend(sim, npc, posts) -> None:
    """A worker's start-of-tick update: pay a finished clean shift, end a walk
    that arrived (or whose shift ended), and start the fallback walk for a
    worker who is late or has left its post."""
    cfg = sim.cfg
    cell, start = posts[npc.post]
    offset = (sim.tick - start) % cfg.day_length
    on = offset < cfg.shift_length
    reach = within_reach(npc.pos, cell, cfg.size)
    if offset == cfg.shift_length:                # the first tick off shift
        if npc.shift_clean and cfg.wage > 0:
            pay(sim, npc)
        npc.shift_clean = False
    if npc.walking and (reach or not on):
        npc.walking = False
    if not on:
        return
    if offset == 0:
        npc.on_post = npc.shift_clean = reach
        if reach:
            sim.stats.count("work_on_time")
    if reach:
        npc.on_post = True
    elif not npc.walking:
        sim.stats.count("work_left" if npc.on_post else "work_late")
        npc.walking = True
        npc.frazzled = cfg.frazzled_ticks
        npc.shift_clean = False


def pay(sim, npc) -> None:
    """A wage of the food rich in the worker's lowest nutrient, into its hands
    (up to its carry room), out of the soil like a top-up's body."""
    cfg = sim.cfg
    rich = np.asarray(sim.world.rich)
    wanted = np.flatnonzero(rich == int(np.argmin(npc.nutrients)))
    t = int(wanted[0]) if wanted.size else 0
    amount = min(cfg.wage, cfg.carry_capacity - float(npc.inventory.sum()))
    if amount <= 1e-12:
        return
    got = sim.world.take_from_soil(amount)
    if got:
        npc.inventory[t] += got
        sim.stats.count("work_paid")
