import pytest

from summarize_provider_capture import SummaryError, summarize_capture


def test_sideline_quant_summary_contains_only_safe_metadata_and_aggregation():
    capture = {
        "capture_id": "sq-11",
        "target_gameweek": 11,
        "timing": {
            "generated_at_utc": "2026-11-20T08:00:00Z",
            "captured_at_utc": "2026-11-20T09:00:00Z",
            "deadline_utc": "2026-11-21T11:00:00Z",
        },
        "source": {"raw_sha256": "a" * 64},
        "coverage": {"declared_row_count": 680, "declared_player_count": 672},
        "raw_archives": {"provider_response_base64": "secret raw bytes"},
    }
    normalized = {
        "canonical_snapshot": {"coverage": {"row_count": 680}, "records": [{"expected_points": 99}]},
        "player_gameweek_snapshot": {
            "coverage": {"row_count": 672},
            "decision_eligible": True,
            "records": [{"expected_points": 99}],
        },
        "aggregation_provenance": {
            "method": "SUM(xP) and SUM(e_mins) grouped by player_id within target Gameweek",
        },
        "provider_native_rows": [{"xP": 99}],
        "player_gameweek_sum_xp": [{"expected_points": 99}],
    }
    result = summarize_capture("Sideline Quant", capture, normalized)
    assert result["provider_fixture_row_count"] == 680
    assert result["normalized_fixture_row_count"] == 680
    assert result["normalized_gameweek_player_count"] == 672
    assert result["decision_eligible"] is True
    assert "SUM(xP)" in result["aggregation_method"]
    assert "records" not in result
    assert "raw_archives" not in result
    assert "provider_native_rows" not in result
    assert "secret raw bytes" not in str(result)
    assert "99" not in str(result)


def test_fpl_cat_summary_excludes_player_rows_and_bootstrap():
    capture = {
        "provider_snapshot": {
            "snapshot_id": "cat-11",
            "target_gameweek": 11,
            "timing": {
                "generated_at_utc": "2026-11-20T08:00:00Z",
                "captured_at_utc": "2026-11-20T09:00:00Z",
                "deadline_utc": "2026-11-21T11:00:00Z",
            },
            "source": {"raw_sha256": "c" * 64},
            "records": [{"expected_points": 10}],
        },
        "raw_archives": {"official_fpl_bootstrap_base64": "bootstrap"},
        "capture_status": {"provider_generation_time_status": "VERIFIED"},
    }
    result = summarize_capture("FPL Cat", capture)
    assert result["provider_row_count"] == 1
    assert "records" not in result
    assert "raw_archives" not in result
    assert "bootstrap" not in str(result)


@pytest.mark.parametrize("provider", ["FPLRogue", "FPL Lucho", "FPL Wildcard", "FPL Review"])
def test_rejects_providers_outside_approved_scope(provider):
    with pytest.raises(SummaryError, match="only FPL Cat and Sideline Quant"):
        summarize_capture(provider, {})
