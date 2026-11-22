import base64
import hashlib
import pytest
from m4_covar_residual_bootstrap import ResidualBootstrapError, build_residual_bootstrap_scenarios


def fixture_inputs():
    target = {
        "bundle_type": "M3_CONVENTIONAL_FORECAST_ONLY_COVAR_INPUT",
        "season": "2026-27", "target_gameweek": 12,
        "as_of_utc": "2026-11-27T08:00:00Z", "deadline_utc": "2026-11-27T11:00:00Z",
        "forecast_snapshot_id": "m3-gw12",
        "model_version": "fplcat-v2", "decision_weight": 0.0, "production_eligible": False,
        "point_in_time_status": "M3_SOURCE_TIMESTAMPS_VALIDATED",
        "privacy": {"manager_identity_included": False, "manager_squad_included": False,
                    "bank_or_transfer_state_included": False, "frozen_decision_included": False},
        "source_archives": [
            {"source_type": "provider_forecast", "captured_at_utc": "2026-11-27T07:55:00Z",
             "generated_at_utc": "2026-11-27T07:30:00Z", "raw_payload_base64": base64.b64encode(b"provider").decode(),
             "raw_sha256": hashlib.sha256(b"provider").hexdigest()},
            {"source_type": "player_metadata", "captured_at_utc": "2026-11-27T07:55:00Z",
             "raw_payload_base64": base64.b64encode(b"metadata").decode(),
             "raw_sha256": hashlib.sha256(b"metadata").hexdigest()},
        ],
        "player_forecasts": [
            {"fpl_element_id": 10, "expected_points": 5.0, "expected_minutes": 90},
            {"fpl_element_id": 11, "expected_points": 4.0, "expected_minutes": 75},
        ],
        "player_metadata": [
            {"fpl_element_id": 10, "position": "GKP", "team_id": 1},
            {"fpl_element_id": 11, "position": "MID", "team_id": 2},
        ],
    }
    clusters, rows = [], []
    residuals = [(2, 1, 0, 10), (-2, -1, 0, -10), (1, 0.5, 0, 5), (-1, -0.5, 0, -5), (0, 0, 0, 0)]
    for gw, (a, b, ma, mb) in enumerate(residuals, start=1):
        clusters.append({"gameweek": gw, "outcome_available_at_utc": f"2026-10-{gw+1:02d}T18:00:00Z", "finality_status": "PASS_EXACT_MATCH"})
        for pid, err, minute_err in ((10, a, ma), (11, b, mb)):
            rows.append({"gameweek": gw, "fpl_element_id": pid, "points_error_actual_minus_expected": err,
                         "minutes_error_actual_minus_expected": minute_err,
                         "model_version": "fplcat-v2", "finality_status": "PASS_EXACT_MATCH"})
    panel = {"dataset_type": "MULTI_GAMEWEEK_PROSPECTIVE_CONVENTIONAL_FORECAST_OUTCOME_PANEL",
             "season": "2026-27", "cluster_unit": "GAMEWEEK", "missing_observations_zero_filled": 0,
             "joint_dependence_inferred_from_marginal_player_rows": False,
             "gameweek_clusters": clusters, "matched_rows": rows}
    return target, panel


def test_emits_complete_equal_weight_joint_blocks_and_preserves_target_means():
    target, panel = fixture_inputs()
    result = build_residual_bootstrap_scenarios(target, panel, training_cutoff_utc="2026-11-26T20:00:00Z")
    assert result["scenario_count"] == 5
    assert sum(row["probability"] for row in result["scenarios"]) == pytest.approx(1.0)
    for player_id, expected in (("10", 5.0), ("11", 4.0)):
        values = [next(x["fpl_points"] for x in row["player_outcomes"] if x["player_id"] == player_id) for row in result["scenarios"]]
        assert sum(values) / len(values) == pytest.approx(expected)
    assert result["decision_weight"] == 0.0
    assert result["production_eligible"] is False
    assert result["covar_used"] is False
    assert result["players"][0]["position"] == "GK"
    assert all("minutes" in outcome and isinstance(outcome["played"], bool) for scenario in result["scenarios"] for outcome in scenario["player_outcomes"])



def test_restricts_scenario_universe_to_portfolio_player_ids():
    target, panel = fixture_inputs()
    result = build_residual_bootstrap_scenarios(target, panel, training_cutoff_utc="2026-11-26T20:00:00Z", target_player_ids=[10])
    assert result["target_player_ids"] == ["10"]
    assert result["player_count"] == 1
    assert all(len(scenario["player_outcomes"]) == 1 for scenario in result["scenarios"])


def test_rejects_selected_player_missing_from_target_forecast():
    target, panel = fixture_inputs()
    with pytest.raises(ResidualBootstrapError, match="missing from the M3 forecast"):
        build_residual_bootstrap_scenarios(target, panel, training_cutoff_utc="2026-11-26T20:00:00Z", target_player_ids=[999])

def test_preserves_positive_cross_player_residual_dependence():
    target, panel = fixture_inputs()
    result = build_residual_bootstrap_scenarios(target, panel, training_cutoff_utc="2026-11-26T20:00:00Z")
    left = [next(x["fpl_points"] for x in row["player_outcomes"] if x["player_id"] == "10") for row in result["scenarios"]]
    right = [next(x["fpl_points"] for x in row["player_outcomes"] if x["player_id"] == "11") for row in result["scenarios"]]
    mean_left, mean_right = sum(left) / len(left), sum(right) / len(right)
    covariance = sum((x-mean_left)*(y-mean_right) for x,y in zip(left,right)) / len(left)
    assert covariance > 0


def test_rejects_manager_data_in_target_bundle():
    target, panel = fixture_inputs()
    target["privacy"]["manager_squad_included"] = True
    with pytest.raises(ResidualBootstrapError, match="exclude all manager-specific data"):
        build_residual_bootstrap_scenarios(target, panel, training_cutoff_utc="2026-11-26T20:00:00Z")


def test_rejects_tampered_m3_source_bytes():
    target, panel = fixture_inputs()
    target["source_archives"][0]["raw_payload_base64"] = base64.b64encode(b"tampered").decode()
    with pytest.raises(ResidualBootstrapError, match="SHA-256 mismatch"):
        build_residual_bootstrap_scenarios(target, panel, training_cutoff_utc="2026-11-26T20:00:00Z")


def test_rejects_incomplete_gameweek_blocks_instead_of_zero_filling():
    target, panel = fixture_inputs()
    panel["matched_rows"] = [row for row in panel["matched_rows"] if not (row["gameweek"] == 1 and row["fpl_element_id"] == 11)]
    with pytest.raises(ResidualBootstrapError, match="complete Gameweek residual blocks"):
        build_residual_bootstrap_scenarios(target, panel, training_cutoff_utc="2026-11-26T20:00:00Z")


def test_rejects_outcome_not_available_before_training_cutoff():
    target, panel = fixture_inputs()
    panel["gameweek_clusters"][0]["outcome_available_at_utc"] = "2026-11-27T08:00:00Z"
    with pytest.raises(ResidualBootstrapError, match="not available strictly before"):
        build_residual_bootstrap_scenarios(target, panel, training_cutoff_utc="2026-11-27T08:00:00Z")


def test_rejects_target_gameweek_in_historical_panel():
    target, panel = fixture_inputs()
    panel["gameweek_clusters"][0]["gameweek"] = 12
    with pytest.raises(ResidualBootstrapError, match="target Gameweek cannot"):
        build_residual_bootstrap_scenarios(target, panel, training_cutoff_utc="2026-11-26T20:00:00Z")


def test_rejects_mismatched_model_version():
    target, panel = fixture_inputs()
    panel["matched_rows"][0]["model_version"] = "other-model"
    with pytest.raises(ResidualBootstrapError, match="model versions must match"):
        build_residual_bootstrap_scenarios(target, panel, training_cutoff_utc="2026-11-26T20:00:00Z")


def test_rejects_missing_outcome_availability_timestamp():
    target, panel = fixture_inputs()
    del panel["gameweek_clusters"][0]["outcome_available_at_utc"]
    with pytest.raises(ResidualBootstrapError, match="outcome_available_at_utc"):
        build_residual_bootstrap_scenarios(target, panel, training_cutoff_utc="2026-11-26T20:00:00Z")
