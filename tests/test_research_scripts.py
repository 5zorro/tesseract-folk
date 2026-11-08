"""Research scripts: reruns reuse finished runs by file name, and a rerun with
other settings must not silently reuse them (review 2026-11-08); the hunger
search's bisection."""
from types import SimpleNamespace

import pytest

import scripts.hunger_search as hunger_search
import scripts.variation_ladder as variation_ladder


def test_hunger_search_names_runs_by_brain_size(monkeypatch):
    monkeypatch.setattr(hunger_search, "HIDDEN", 16)
    default = hunger_search.csv_path(4, 0.5).name
    monkeypatch.setattr(hunger_search, "HIDDEN", 32)
    assert default == "hdist-4d-h0.5.csv"                  # runs before 2026-11-08 keep their names
    assert hunger_search.csv_path(4, 0.5).name == "hdist-4d-u32-h0.5.csv"
    monkeypatch.setattr(hunger_search, "KEYS", ("metabolism_rate",))
    assert hunger_search.csv_path(4, 0.5).name == "hdist-4d-body-u32-h0.5.csv"


def args(**kw):
    return SimpleNamespace(**{"rounds": 6, "round_ticks": 50_000, "play_every": 2,
                              "nursery_seeds": [100, 101], **kw})


def rows(rounds, seeds, round_ticks=50_000):
    return [{"arm": "plain", "round": r, "nursery": n, "ticks": r * round_ticks} for r in rounds for n in seeds]


def test_variation_cells_refuse_other_settings(tmp_path):
    path = tmp_path / "var-4d-m1.0-h16.csv"
    variation_ladder.check_settings(path, rows([2, 4, 6], [100, 101]), args())
    cases = [(rows([2, 4, 6], [100, 101]), args(rounds=8)),                 # asked for more rounds
             (rows([2, 4, 6], [100]), args()),                              # other nursery seeds
             (rows([2, 4, 6], [100, 101], 20_000), args()),                 # other round length
             (rows([1, 2, 3, 4, 5, 6], [100, 101]), args())]                # other --play-every
    for found, wanted in cases:
        with pytest.raises(SystemExit, match="other settings"):
            variation_ladder.check_settings(path, found, wanted)


def test_variation_cells_name_a_non_default_hunger():
    assert variation_ladder.cell_name(4, 1.0, 16) == "var-4d-m1.0-h16"
    other = variation_ladder.cell_name(4, 1.0, 16, "nutrient_decay=0.003")
    assert other.startswith("var-4d-m1.0-h16-") and other != variation_ladder.cell_name(4, 1.0, 16)


def test_hunger_search_bisects_between_the_lowest_pass_and_the_fail_below():
    rows = lambda *ls: [{"level": lv, "passes": ok} for lv, ok in ls]  # noqa: E731
    assert hunger_search.next_level(rows((0.5, False), (0.75, True), (1.0, True)), 0.02) == 0.625
    assert hunger_search.next_level(rows((0.5, False), (0.75, False), (1.0, True)), 0.02) == 0.875
    assert hunger_search.next_level(rows((0.5, False), (1.0, False)), 0.02) is None        # nothing passes
    assert hunger_search.next_level(rows((0.75, True), (1.0, True)), 0.02) is None         # no fail below
    assert hunger_search.next_level(rows((0.74, False), (0.75, True)), 0.02) is None       # gap under min_gap
