from pathlib import Path

from predict_cta_abc_points import score_rows
from train_cta_abc_points_model import train_model


def _rows():
    rows = []
    for i in range(30):
        rows.append({
            "season": "2017/18",
            "gameweek": str(1 + i // 2),
            "fpl_element_id": str(100 + i),
            "fpl_fixture_id": str(1000 + i),
            "kickoff_time_utc": f"2017-08-{1 + i // 2:02d}T15:00:00Z",
            "research_eligible_for_analysis": "true",
            "target_fpl_total_points": str(2.0 + i * 0.1),
            "fpl_total_points_prior_3_avg": str(3.0 + i * 0.05),
            "fpl_total_points_prior_5_avg": str(2.5 + i * 0.04),
            "fpl_minutes_prior_3_avg": "75",
            "fpl_minutes_prior_5_avg": "70",
            "abc_player_key_pass_rate": str(i * 0.02),
        })
    return rows


def test_train_and_score_reusable_abc_points_model(tmp_path):
    source = tmp_path / "panel.csv"
    source.write_text("fixture,points\n1,2\n", encoding="utf-8")
    out_dir = tmp_path / "model"
    report = train_model(
        _rows(),
        {"point_in_time_status": "RETROSPECTIVE_SOURCE_VINTAGES_NOT_VERIFIED"},
        source,
        out_dir,
        ridge_lambda=1.0,
    )
    assert report["status"] == "CANDIDATE_TRAINED_RESEARCH_ONLY"
    assert report["production_eligible"] is False
    assert report["feature_count"] == 5
    import json
    payload = json.loads((out_dir / "abc_points_model.json").read_text(encoding="utf-8"))
    prediction_rows = [
        {
            "fpl_element_id": "10", "gameweek": "12", "fpl_fixture_id": "A",
            "fpl_total_points_prior_3_avg": "4", "fpl_total_points_prior_5_avg": "3",
            "fpl_minutes_prior_3_avg": "80", "fpl_minutes_prior_5_avg": "75",
            "abc_player_key_pass_rate": "0.5",
        },
        {
            "fpl_element_id": "10", "gameweek": "12", "fpl_fixture_id": "B",
            "fpl_total_points_prior_3_avg": "4", "fpl_total_points_prior_5_avg": "3",
            "fpl_minutes_prior_3_avg": "80", "fpl_minutes_prior_5_avg": "75",
            "abc_player_key_pass_rate": "0.5",
        },
    ]
    fixture, gameweek = score_rows(prediction_rows, payload)
    assert len(fixture) == 2
    assert gameweek[0]["fixture_count"] == 2
    assert gameweek[0]["expected_points"] == fixture[0]["expected_points"] + fixture[1]["expected_points"]


def test_scoring_rejects_duplicate_player_fixture_keys(tmp_path):
    from predict_cta_abc_points import score_rows
    from train_fpl_exploratory_ridge import fit_ridge

    rows = _rows()
    features = [
        "fpl_total_points_prior_3_avg", "fpl_total_points_prior_5_avg",
        "fpl_minutes_prior_3_avg", "fpl_minutes_prior_5_avg",
        "abc_player_key_pass_rate",
    ]
    model = fit_ridge(rows, "target_fpl_total_points", features, 1.0)
    payload = {
        "schema_version": "1.0",
        "model_version": "test",
        "feature_order": features,
        "model": model,
    }
    duplicate = [{
        "fpl_element_id": "10", "gameweek": "12", "fpl_fixture_id": "A",
        **{name: "1" for name in features},
    }] * 2
    import pytest
    with pytest.raises(ValueError, match="Duplicate prediction"):
        score_rows(duplicate, payload)



def test_inference_rejects_mismatched_model_feature_contract():
    from predict_cta_abc_points import score_rows
    from train_fpl_exploratory_ridge import fit_ridge
    import pytest

    rows = _rows()
    features = [
        "fpl_total_points_prior_3_avg", "fpl_total_points_prior_5_avg",
        "fpl_minutes_prior_3_avg", "fpl_minutes_prior_5_avg",
        "abc_player_key_pass_rate",
    ]
    model = fit_ridge(rows, "target_fpl_total_points", features, 1.0)
    payload = {
        "schema_version": "1.0",
        "model_version": "test",
        "feature_order": list(reversed(features)),
        "model": model,
    }
    with pytest.raises(ValueError, match="feature_order"):
        score_rows([], payload)


def test_inference_rejects_incomplete_model_parameter_arrays():
    from predict_cta_abc_points import score_rows
    import pytest

    payload = {
        "schema_version": "1.0",
        "model_version": "test",
        "feature_order": ["f1"],
        "model": {
            "source_feature_names": ["f1"],
            "imputation_values": [0.0],
            "means": [0.0],
            "scales": [1.0],
            "coefficients": [0.0, 0.0],
            "missing_value_policy": "TRAINING_MEDIAN_PLUS_MISSINGNESS_INDICATOR",
        },
    }
    with pytest.raises(ValueError, match="scaling vectors"):
        score_rows([], payload)



def test_research_inference_filters_unverified_rows():
    from predict_cta_abc_points import research_eligible_rows
    import pytest

    rows = [
        {"fpl_element_id": "10", "research_eligible_for_analysis": "true"},
        {"fpl_element_id": "11", "research_eligible_for_analysis": "false"},
    ]
    assert research_eligible_rows(rows) == [rows[0]]
    with pytest.raises(ValueError, match="No research-eligible"):
        research_eligible_rows([rows[1]])
    with pytest.raises(ValueError, match="must carry"):
        research_eligible_rows([{"fpl_element_id": "10"}])
