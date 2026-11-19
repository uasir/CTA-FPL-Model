import pytest

from cta_four_layer_pipeline import (
    CONVENTIONAL_FPL_FEATURES, LAYER_FEATURES, LayerResult,
    integrate_player_sequence, require_complete_sequence,
    validate_model_track_input,
)


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


def test_standalone_2pm_accepts_conventional_fpl_features_without_abc():
    validate_model_track_input("standalone_2pm", CONVENTIONAL_FPL_FEATURES)


def test_standalone_2pm_rejects_any_abc_dependency():
    with pytest.raises(ValueError):
        validate_model_track_input("standalone_2pm", ("prior_gw_points", "contextual_threat_score"))


def test_integrated_abc_predictor_does_not_require_conventional_fpl_features():
    abc_features = tuple(name for names in LAYER_FEATURES.values() for name in names)
    validate_model_track_input("integrated_abc", abc_features)
    with pytest.raises(ValueError):
        validate_model_track_input("integrated_abc", ("prior_gw_points", "contextual_threat_score"))


def test_optional_augmented_2pm_requires_both_feature_families():
    validate_model_track_input(
        "abc_augmented_2pm",
        ("prior_gw_points", "contextual_threat_score"),
    )
    with pytest.raises(ValueError):
        validate_model_track_input("abc_augmented_2pm", ("prior_gw_points",))
    with pytest.raises(ValueError):
        validate_model_track_input("abc_augmented_2pm", ("contextual_threat_score",))
