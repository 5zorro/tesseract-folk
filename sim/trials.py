"""Hall-of-fame trials (5zorro, 2026-11-06; Config.hall_of_fame_trials, 0 = off).

One life is a noisy score (plan-m2 slices R3, R10), so with trials on a finished
life doesn't enter the hall of fame directly. It becomes a candidate, and the
next top-ups are exact clones of its brain (no mutation): its trials. When every
trial life is in, it enters only if enough of its lives passed (and, if asked,
had children); its merit then averages all of them. A candidate is rejected as
soon as it can no longer qualify, so failing brains don't use up more top-ups.

A life passes with at most `hall_of_fame_trial_max_collapses` collapses, or, with
-1 (the default), with a collapse rate below the population's at the time (in
4D no finished life has zero collapses, so the absolute rule admits nobody).

The bookkeeping is plain dicts, shared by both engines (like nursery.py's
hall-of-fame entries); each engine decides when lives finish and spawns clones.
"""
from __future__ import annotations

TRIAL_KEYS = ("passes", "parents", "to_spawn", "out")
MAX_TRIALS = 16


def life_passes(cfg, collapses: int, rate: float, population: float) -> bool:
    if cfg.hall_of_fame_trial_max_collapses >= 0:
        return collapses <= cfg.hall_of_fame_trial_max_collapses
    return population >= 0 and rate < population


def check(cfg) -> None:
    """Raise ValueError if the trial settings can't work."""
    lives = cfg.hall_of_fame_trials + 1
    if not 0 <= cfg.hall_of_fame_trials <= MAX_TRIALS:
        raise ValueError(f"hall_of_fame_trials must be within 0-{MAX_TRIALS}, got {cfg.hall_of_fame_trials!r}")
    if not cfg.hall_of_fame_trials:          # off: the other settings aren't used
        return
    if not 0 <= cfg.hall_of_fame_trial_passes <= lives:
        raise ValueError(f"hall_of_fame_trial_passes must be within 0-{lives} (1 + trials), "
                         f"got {cfg.hall_of_fame_trial_passes!r}")
    if not 0 <= cfg.hall_of_fame_trial_parents <= lives:
        raise ValueError(f"hall_of_fame_trial_parents must be within 0-{lives} (1 + trials), "
                         f"got {cfg.hall_of_fame_trial_parents!r}")
    if cfg.hall_of_fame_trial_max_collapses < -1:
        raise ValueError(f"hall_of_fame_trial_max_collapses must be -1 (relative) or >= 0, "
                         f"got {cfg.hall_of_fame_trial_max_collapses!r}")


def start(cfg, entry: dict, passed: bool, had_kids: bool) -> dict:
    """A candidate from a first life's would-be hall-of-fame entry."""
    n = cfg.hall_of_fame_trials
    return dict(entry, passes=int(passed), parents=int(had_kids), to_spawn=n, out=n)


def add_life(candidate: dict, excess: float, passed: bool, had_kids: bool) -> None:
    candidate["lives"] += 1
    candidate["excess_sum"] += excess
    candidate["passes"] += int(passed)
    candidate["parents"] += int(had_kids)
    candidate["out"] -= 1


def verdict(cfg, candidate: dict) -> str | None:
    """'admit', 'reject', or None while trial lives are still out."""
    left = candidate["out"]
    if (candidate["passes"] + left < cfg.hall_of_fame_trial_passes
            or candidate["parents"] + left < cfg.hall_of_fame_trial_parents):
        return "reject"
    return "admit" if left == 0 else None


def as_entry(candidate: dict) -> dict:
    return {k: v for k, v in candidate.items() if k not in TRIAL_KEYS}


def next_to_spawn(candidates: list[dict]) -> dict | None:
    """The candidate whose clone the next top-up is: lowest id first."""
    return min((c for c in candidates if c["to_spawn"] > 0), key=lambda c: c["id"], default=None)
