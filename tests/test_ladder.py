"""scripts/ladder.py: nursery reuse and the per-goal verdicts (M2 slices 3d-3e)."""
import pytest

from scripts.ladder import nursery_path, reusable, train, verdicts

SHAPE = (2, 12, 3.0, 4, ())


def test_a_nursery_is_reused_only_when_trained_the_same_way(tmp_path):
    assert train([(SHAPE, 100, 30, tmp_path)])[0].startswith("trained")
    msgs = train([(SHAPE, 100, 30, tmp_path), (SHAPE, 101, 30, tmp_path)])   # a batch: one kept, one new
    assert [m.split()[0] for m in msgs] == ["kept", "trained"]
    path = nursery_path(tmp_path, SHAPE, 100)
    assert reusable(path, SHAPE, 100, 30)
    with pytest.raises(ValueError, match="ticks"):
        reusable(path, SHAPE, 100, 60)
    with pytest.raises(ValueError, match="hidden_units"):
        reusable(path, SHAPE[:3] + (8, ()), 100, 30)   # same folder, other brain size


def test_a_changed_default_blocks_reuse(tmp_path):
    import json
    train([(SHAPE, 100, 30, tmp_path)])
    path = nursery_path(tmp_path, SHAPE, 100)
    state = json.loads((path / "state.json").read_text())
    state["config"]["mutation_lineage"] = False        # trained before a default changed
    (path / "state.json").write_text(json.dumps(state))
    with pytest.raises(ValueError, match="mutation_lineage"):
        reusable(path, SHAPE, 100, 30)


def row(brains, seed, collapse, excess, **kw):
    return {"dims": 2, "hidden": 4, "brains": brains, "seed": seed, "collapse_rate": collapse,
            "min_nutrient": 0.5, "diet_diversity": 0.95, "zone_types_per_life": 2.8,
            "approach_excess": excess, **kw}


def test_verdicts_check_every_goal_against_scratch():
    rows = [row("scratch", s, 2.0, 0.05) for s in (0, 1)]
    rows += [row("n100", s, 1.0, 0.10) for s in (0, 1)]
    (line,) = verdicts(rows)
    assert all(line["goals"].values())
    assert line["excess_vs_scratch"] == pytest.approx(0.05)
    rows[-1]["approach_excess"] = -0.01                  # one run doesn't seek its food
    assert not verdicts(rows)[0]["goals"]["seeks diet"]
