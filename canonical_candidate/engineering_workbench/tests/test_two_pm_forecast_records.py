import pytest
torch = pytest.importorskip("torch")

from two_component_poisson_transformer import PaperTwoComponentPoissonTransformer
from two_pm_forecast_records import build_forecast_records


def test_forecast_record_preserves_distribution_and_provenance_without_decision_logic():
    model = PaperTwoComponentPoissonTransformer(
        feature_count=8,
        sequence_length=6,
        num_layers=1,
        d_model=16,
        nhead=4,
        dim_feedforward=32,
        dropout=0.0,
    )
    output = model(torch.randn(2, 6, 8))
    records = build_forecast_records(
        output,
        player_ids=[1001, 1002],
        target_gameweeks=[12, 12],
        forecast_as_of="2026-11-23T10:00:00Z",
        training_cutoff="2026-11-01T00:00:00Z",
        feature_schema_version="dastan-286-candidate-v1",
        data_snapshot_hashes={"features": "a" * 64, "fpl_cache": "b" * 64},
        quality_metadata={"status": "RESEARCH_CANDIDATE"},
    )
    assert len(records) == 2
    record = records[0]
    for field in (
        "p", "lambda_1", "lambda_2", "expected_points", "variance",
        "standard_deviation", "probability_6_plus", "probability_8_plus",
        "probability_10_plus", "forecast_as_of", "training_cutoff",
        "data_snapshot_hashes", "feature_schema_version", "model_version",
    ):
        assert field in record
    assert record["probability_6_plus"] >= record["probability_8_plus"]
    assert record["probability_8_plus"] >= record["probability_10_plus"]
    assert record["production_eligible"] is False
    assert "transfer" not in record
    assert "captain" not in record
    assert "squad" not in record


def test_forecast_record_rejects_post_forecast_training_cutoff_and_bad_batch():
    model = PaperTwoComponentPoissonTransformer(
        feature_count=4,
        sequence_length=6,
        num_layers=1,
        d_model=16,
        nhead=4,
        dim_feedforward=32,
    )
    output = model(torch.randn(1, 6, 4))
    common = dict(
        output=output,
        player_ids=[1001],
        target_gameweeks=[12],
        feature_schema_version="schema-v1",
        data_snapshot_hashes={"features": "a" * 64},
    )
    with pytest.raises(ValueError, match="training_cutoff"):
        build_forecast_records(
            **common,
            forecast_as_of="2026-11-01T00:00:00Z",
            training_cutoff="2026-11-02T00:00:00Z",
        )
    with pytest.raises(ValueError, match="equal length"):
        build_forecast_records(
            **{**common, "target_gameweeks": [12, 13]},
            forecast_as_of="2026-11-03T00:00:00Z",
            training_cutoff="2026-11-02T00:00:00Z",
        )
