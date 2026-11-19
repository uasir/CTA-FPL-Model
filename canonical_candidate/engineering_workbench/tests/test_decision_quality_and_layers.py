import math
import pytest

from evaluate_fpl_decision_quality import (
    evaluate_forecast, explain_post_deadline_events, point_error_metrics,
    threshold_probability_report,
)
from cta_four_layer_pipeline import (
    LAYER_FEATURES, LayerResult, integrate_player_sequence, require_complete_sequence,
)


def test_rmse_is_diagnostic_and_haul_probability_is_scored_separately():
    actual = [2, 3, 16, 1, 0, 8]
    predicted = [2, 3, 2, 2, 1, 6]
    metrics = point_error_metrics(actual, predicted)
    assert metrics["mae"] >= 0
    assert metrics["rmse"] >= metrics["mae"]
    assert metrics["large_error_rate_ge_10"] > 0
    report = evaluate_forecast(actual, predicted, {6: [.1,.1,.2,.1,.05,.7],
                                                    8: [.05,.05,.1,.05,.02,.6],
                                                    10: [.01,.01,.05,.01,.01,.3]},
                               ranking_score=predicted, top_k=2)
    assert report["principle"] == "RMSE_IS_DIAGNOSTIC_NOT_SOLE_PROMOTION_GATE"
    assert report["point_errors"]["n"] == len(actual)
    assert report["haul_probabilities"]["6+"]["brier"] >= 0
    assert report["ranking"]["top_k"] == 2


def test_forecast_evaluation_never_drops_large_realised_outcomes():
    report = evaluate_forecast([1, 16, 2], [1, 2, 2])
    assert report["point_errors"]["n"] == 3
    assert report["point_errors"]["absolute_error_p99"] > 13.5


def test_post_deadline_event_annotations_are_explanatory_only():
    result = explain_post_deadline_events([{"event_type": "red_card", "available_at_deadline": False}])
    assert result["excluded_from_forecast_features"] is True
    with pytest.raises(ValueError):
        explain_post_deadline_events([{"event_type": "opponent_injury", "available_at_deadline": True}])


def _layer(name, status="RESEARCH_ONLY"):
    features = {key: 1.0 for key in LAYER_FEATURES[name]}
    coverage = {key: "OBSERVED" for key in features}
    return LayerResult(name, status, features, coverage, "2026-11-18T10:00:00Z", "test-source")


def test_four_layer_contract_preserves_missingness_and_research_status():
    results = [_layer(name) for name in LAYER_FEATURES]
    integrated = integrate_player_sequence(results, "2026-11-18T11:00:00Z")
    assert integrated["status"] == "RESEARCH_ONLY"
    assert integrated["missing_layers"] == []
    assert integrated["features"]["contextual_threat_score"] == 1.0
    with pytest.raises(ValueError):
        require_complete_sequence(integrated)


def test_four_layer_contract_rejects_post_deadline_features_and_silent_zero_fill():
    result = _layer("A_temporal_football_value")
    late = LayerResult(result.layer, result.status, result.features, result.source_coverage,
                       "2026-11-18T12:00:00Z", result.provenance)
    with pytest.raises(ValueError):
        integrate_player_sequence([late], "2026-11-18T11:00:00Z")
    bad_coverage = dict(result.source_coverage)
    bad_coverage["progressive_passes"] = "MISSING"
    invalid = LayerResult(result.layer, result.status, result.features, bad_coverage,
                          result.as_of, result.provenance)
    with pytest.raises(ValueError):
        integrate_player_sequence([invalid], "2026-11-18T11:00:00Z")
