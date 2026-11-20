from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pytest
from build_matched_abc_2pm_fold_manifest import build_manifest

def abc(key, fixtures, points, minutes=90, eligible=True):
    season, player, gw = key
    return {"season": season, "fpl_element_id": player, "gameweek": str(gw),
            "fixture_ids": json.dumps(fixtures), "target_fpl_total_points": str(points),
            "target_fpl_minutes": str(minutes), "research_eligible_for_model": str(eligible)}

def fpl(key, fixtures, points, minutes=90):
    season, player, gw = key
    return [{"season": season.replace("/", "-"), "fpl_element_id": player, "gameweek": str(gw),
        "fixture_id": fixture, "target_total_points": str(points / len(fixtures)),
        "target_minutes": str(minutes / len(fixtures)), "prior_gameweeks_count": "2",
        "prior_gw_points": "4", "prior3_gw_points_avg": "4.0", "prior5_gw_points_avg": "3.5",
        "prior_gw_minutes": "80", "prior3_gw_minutes_avg": "80", "prior5_gw_minutes_avg": "75",
        "prior5_appearance_rate": "1.0", "season_appearance_rate": "1.0",
        "season_to_date_minutes": "180", "season_to_date_points_per90": "4.0",
        "prior3_gw_xg_avg": "0.2", "prior3_gw_xa_avg": "0.1"} for fixture in fixtures]

def sample(n_gw=26, n_players=3):
    a, f = [], []
    for gw in range(1, n_gw + 1):
        for player_num in range(1, n_players + 1):
            key = ("2017/18", str(player_num), gw)
            fixture, points = f"{gw}-{player_num}", gw + player_num
            a.append(abc(key, [fixture], points))
            f.extend(fpl(key, [fixture], points))
    return a, f

def test_builds_same_key_hashes_and_disjoint_chronological_partitions():
    a, f = sample()
    report = build_manifest(a, f, min_train_gameweeks=18, test_window=4,
        min_fit_rows=1, min_calibration_rows=1, min_test_rows=1)
    assert report["status"] == "PASS_MATCHED_FOLD_MANIFEST"
    assert report["actual_points_and_minutes_parity"] == "PASS"
    assert report["fixture_id_set_parity"] == "PASS"
    assert len(report["_private_partition_keys"]) == sum(
        fold["fit_player_gameweeks"] + fold["calibration_player_gameweeks"] + fold["test_player_gameweeks"]
        for fold in report["folds"]
    )
    for fold in report["folds"]:
        assert not (set(fold["fit_gameweeks"]) & set(fold["calibration_gameweeks"]))
        assert not (set(fold["fit_gameweeks"]) & set(fold["test_gameweeks"]))
        assert not (set(fold["calibration_gameweeks"]) & set(fold["test_gameweeks"]))
        assert fold["status"] == "READY"

def test_target_mismatch_fails_closed_instead_of_intersection_drop():
    a, f = sample()
    f[3]["target_total_points"] = "999"
    report = build_manifest(a, f, min_train_gameweeks=18, min_fit_rows=1,
        min_calibration_rows=1, min_test_rows=1)
    assert report["status"] == "FAIL_CLOSED_TARGET_OR_FIXTURE_PARITY"
    assert report["folds"] == []
    assert any("ACTUAL_POINTS_MISMATCH" in x["reasons"] for x in report["mismatch_examples"])

def test_missing_fixture_fails_closed():
    a, f = sample()
    f = f[:3] + f[4:]
    report = build_manifest(a, f, min_train_gameweeks=18, min_fit_rows=1,
        min_calibration_rows=1, min_test_rows=1)
    assert report["status"] == "FAIL_CLOSED_TARGET_OR_FIXTURE_PARITY"

def test_double_gameweek_targets_are_summed_and_fixture_sets_compared():
    key = ("2017/18", "7", 20)
    a, f = [abc(key, ["f1", "f2"], 8, 150)], fpl(key, ["f1", "f2"], 8, 150)
    a2, f2 = sample()
    a.extend(a2); f.extend(f2)
    report = build_manifest(a, f, min_train_gameweeks=18, min_fit_rows=1,
        min_calibration_rows=1, min_test_rows=1)
    assert report["status"] == "PASS_MATCHED_FOLD_MANIFEST"

def test_conflicting_lagged_fpl_features_across_dgw_fails():
    key = ("2017/18", "7", 1)
    a, f = [abc(key, ["f1", "f2"], 8, 150)], fpl(key, ["f1", "f2"], 8, 150)
    a2, f2 = sample()
    a.extend(a2); f.extend(f2)
    f[1]["prior3_gw_points_avg"] = "99"
    with pytest.raises(ValueError, match="Conflicting lagged FPL history feature"):
        build_manifest(a, f, min_train_gameweeks=18)

def test_noneligible_abc_rows_are_not_admitted():
    a, f = sample()
    a[3]["research_eligible_for_model"] = "False"
    report = build_manifest(a, f, min_train_gameweeks=18, min_fit_rows=1,
        min_calibration_rows=1, min_test_rows=1)
    assert report["eligible_abc_player_gameweeks"] == len(a) - 4
    assert report["abc_exclusion_counts"]["ABC_NOT_RESEARCH_ELIGIBLE"] == 1


def test_test_fold_is_blocked_when_required_2pm_last5_baseline_is_missing():
    a, f = sample()
    # With this sample the first test block starts at GW20.
    target = next(row for row in f if row["gameweek"] == "20" and row["fpl_element_id"] == "1")
    target["prior5_gw_points_avg"] = ""
    report = build_manifest(a, f, min_train_gameweeks=18, min_fit_rows=1,
        min_calibration_rows=1, min_test_rows=1)
    assert report["status"] == "BLOCKED_FOLD_COVERAGE"
    assert report["folds"][0]["status"] == "BLOCKED"
    assert "TEST_KEYS_MISSING_2PM_LAST5_BASELINE" in report["folds"][0]["blocking_reasons"]
