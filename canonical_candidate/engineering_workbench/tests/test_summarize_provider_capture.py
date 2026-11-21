import pytest

from summarize_provider_capture import SummaryError, summarize_capture


def test_sideline_quant_summary_contains_only_safe_metadata():
    capture = {
        "capture_id": "sq-11",
        "target_gameweek": 11,
        "timing": {"generated_at_utc": "2026-11-18T03:33:09Z",
                   "captured_at_utc": "2026-11-21T09:00:00Z",
                   "deadline_utc": "2026-11-21T11:00:00Z"},
        "source": {"raw_sha256": "a" * 64},
        "coverage": {"declared_row_count": 672, "declared_player_count": 672},
        "raw_archives": {"provider_response_base64": "secret raw bytes"},
    }
    normalized = {
        "canonical_snapshot": {
            "coverage": {"row_count": 672},
            "decision_eligible": True,
            "records": [{"expected_points": 99}],
        },
        "provider_native_rows": [{"xP": 99}],
    }
    result = summarize_capture("Sideline Quant", capture, normalized)
    assert result["provider_row_count"] == 672
    assert result["decision_eligible"] is True
    assert "records" not in result
    assert "raw_archives" not in result
    assert "provider_native_rows" not in result
    assert "secret raw bytes" not in str(result)
    assert "99" not in str(result)


def test_fplrogue_summary_keeps_schema_but_not_forecast_rows():
    capture = {
        "capture_id": "rogue-11",
        "target_gameweek": 11,
        "timing": {"provider_release_at_utc": "2026-11-21T05:16:00Z",
                   "model_trained_at_utc": "2026-11-21T05:00:00Z",
                   "csv_captured_at_utc": "2026-11-21T09:00:00Z",
                   "deadline_utc": "2026-11-21T11:00:00Z",
                   "generated_at_utc": None},
        "source": {"csv_raw_sha256": "b" * 64, "csv_base64": "private"},
        "schema_inspection": {"csv_headers": ["player", "xPts", "xMins"],
                              "csv_row_count": 672, "rows": [{"xPts": 8.2}]},
        "raw_archives": {"csv_base64": "private"},
    }
    result = summarize_capture("FPLRogue", capture)
    assert result["csv_headers"] == ["player", "xPts", "xMins"]
    assert result["provider_row_count"] == 672
    assert "rows" not in result
    assert "raw_archives" not in result
    assert "private" not in str(result)


def test_fpl_cat_summary_excludes_player_rows_and_bootstrap():
    capture = {
        "provider_snapshot": {
            "snapshot_id": "cat-11",
            "target_gameweek": 11,
            "timing": {"generated_at_utc": "2026-11-20T08:00:00Z",
                       "captured_at_utc": "2026-11-21T09:00:00Z",
                       "deadline_utc": "2026-11-21T11:00:00Z"},
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


def test_wildcard_is_rejected_from_public_summary():
    with pytest.raises(SummaryError, match="must never"):
        summarize_capture("FPL Wildcard", {})
