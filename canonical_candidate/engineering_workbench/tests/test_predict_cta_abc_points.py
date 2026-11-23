import json

from predict_cta_abc_points import build_report, score_rows, write_json
from train_fpl_exploratory_ridge import fit_ridge


def _training_rows():
    rows = []
    for i in range(20):
        rows.append({
            "target_fpl_total_points": str(2 + i * 0.2),
            "fpl_total_points_prior_3_avg": str(3 + i * 0.1),
            "fpl_total_points_prior_5_avg": str(2.5 + i * 0.1),
            "fpl_minutes_prior_3_avg": "75",
            "fpl_minutes_prior_5_avg": "70",
            "abc_player_key_pass_rate": str(i * 0.02),
        })
    return rows


def test_predict_scores_player_fixtures_and_aggregates_double_gameweek():
    features = [
        "fpl_total_points_prior_3_avg", "fpl_total_points_prior_5_avg",
        "fpl_minutes_prior_3_avg", "fpl_minutes_prior_5_avg",
        "abc_player_key_pass_rate",
    ]
    model = fit_ridge(_training_rows(), "target_fpl_total_points", features, 1.0)
    payload = {"model_version": "abc-points-ridge-v1", "feature_order": features, "model": model}
    rows = [
        {"fpl_element_id": "10", "gameweek": "12", "fixture_id": "501",
         "fpl_total_points_prior_3_avg": "4", "fpl_total_points_prior_5_avg": "3",
         "fpl_minutes_prior_3_avg": "80", "fpl_minutes_prior_5_avg": "75",
         "abc_player_key_pass_rate": "0.5", "research_eligible_for_analysis": "true"},
        {"fpl_element_id": "10", "gameweek": "12", "fixture_id": "502",
         "fpl_total_points_prior_3_avg": "4", "fpl_total_points_prior_5_avg": "3",
         "fpl_minutes_prior_3_avg": "80", "fpl_minutes_prior_5_avg": "75",
         "abc_player_key_pass_rate": "0.5", "research_eligible_for_analysis": "true"},
    ]
    fixture, gameweek = score_rows(rows, payload)
    assert len(fixture) == 2
    assert gameweek[0]["fixture_count"] == 2
    assert gameweek[0]["research_eligible_fixture_count"] == 2
    assert gameweek[0]["expected_points"] == fixture[0]["expected_points"] + fixture[1]["expected_points"]


def test_forecast_report_flags_missing_wyscout_features_and_research_only():
    features = ["fpl_total_points_prior_3_avg", "abc_progressive_passes"]
    rows = [
        {"fpl_element_id": "10", "gameweek": "12",
         "fpl_total_points_prior_3_avg": "4", "abc_progressive_passes": ""}
    ]
    payload = {"model_version": "abc-points-ridge-v1", "feature_order": features}
    manifest = {
        "model_version": "abc-points-ridge-v1", "model_family": "Ridge",
        "training_rows": 2602, "unique_players": 91, "unique_fixtures": 370,
        "point_in_time_status": "NOT_VERIFIED", "decision_weight": 0.0,
        "production_eligible": False, "model_sha256": "not-a-real-hash",
    }
    report = build_report(rows, payload, manifest, {"point_in_time_status": "CURRENT"}, __import__("pathlib").Path(__file__))
    assert report["production_eligible"] is False
    assert report["current_wyscout_fallback_available"] is False
    assert report["features_with_zero_observation"] == ["abc_progressive_passes"]


def test_write_json_emits_parseable_json_with_real_newline(tmp_path):
    path = tmp_path / "report.json"
    write_json(path, {"status": "PASS", "rows": 12})
    raw = path.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert json.loads(raw) == {"status": "PASS", "rows": 12}


def test_forecast_report_includes_prediction_and_feature_range_diagnostics(tmp_path):
    features = ["fpl_total_points_prior_3_avg", "abc_progressive_passes"]
    rows = [
        {"fpl_total_points_prior_3_avg": "4", "abc_progressive_passes": "2"},
        {"fpl_total_points_prior_3_avg": "6", "abc_progressive_passes": ""},
    ]
    payload = {"model_version": "abc-points-ridge-v1", "feature_order": features}
    manifest = {"model_family": "Ridge", "model_sha256": "not-a-real-hash"}
    predictions = [
        {"expected_points": -3.0, "research_eligible_for_analysis": "true"},
        {"expected_points": 5.0, "research_eligible_for_analysis": "false"},
    ]
    report = build_report(
        rows, payload, manifest, {}, __import__("pathlib").Path(__file__), predictions
    )
    distribution = report["prediction_distribution"]
    assert distribution["all_scored_player_fixtures"]["count"] == 2
    assert distribution["all_scored_player_fixtures"]["negative_count"] == 1
    assert distribution["research_eligible_player_fixtures"]["min"] == -3.0
    assert distribution["research_ineligible_player_fixtures"]["max"] == 5.0
    assert report["feature_coverage"]["abc_progressive_passes"]["observed_min"] == 2.0
    assert report["feature_coverage"]["abc_progressive_passes"]["observed_max"] == 2.0
