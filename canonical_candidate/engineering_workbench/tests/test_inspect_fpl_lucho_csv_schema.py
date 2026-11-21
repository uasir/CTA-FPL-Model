import base64
import hashlib

import pytest

from inspect_fpl_lucho_csv_schema import (
    FPLLuchoSchemaInspectionError,
    inspect_fpl_lucho_csv_schema,
)


def make_capture(csv_raw=b"player_id,player_name,xP_GW11,xP_GW12,xP_GW13,xP_GW14\n1,Player One,5.2,4.8,4.1,3.9\n2,Player Two,3.1,4.2,3.8,3.5\n"):
    return {
        "capture_id": "test-capture",
        "target_gameweek": 11,
        "provider": {
            "name": "FPL Lucho",
            "product": "forecast_csv",
            "variant": "served_odds_anchored_xp",
        },
        "source": {"sha256": {"csv": hashlib.sha256(csv_raw).hexdigest()}},
        "raw_archives": {"csv_base64": base64.b64encode(csv_raw).decode("ascii")},
    }


def test_inspection_reports_schema_without_emitting_player_values():
    report = inspect_fpl_lucho_csv_schema(make_capture())
    assert report["row_count"] == 2
    assert report["column_count"] == 6
    assert report["gameweek_tokens_in_headers"] == [11, 12, 13, 14]
    assert report["expected_gameweeks_from_page"] == [11, 12, 13, 14]
    assert report["gameweek_coverage_status"] == "MATCHES_PAGE_ADVERTISED_FOUR_GAMEWEEK_WINDOW"
    assert report["normalization_status"] == "SCHEMA_INSPECTED_MAPPING_NOT_APPROVED"
    assert report["privacy"] == "NO_PLAYER_ROW_VALUES_EMITTED"
    assert all(column["semantic_mapping"] is None for column in report["columns"])
    assert "Player One" not in str(report)
    assert "5.2" not in str(report)



def test_inspection_flags_csv_window_that_does_not_match_page_window():
    raw = b"player_id,player_name,xp_gw12,xp_gw13,xp_gw14,xp_gw15\\n1,Private Name,5,4,3,2\\n"
    report = inspect_fpl_lucho_csv_schema(make_capture(raw))
    assert report["expected_gameweeks_from_page"] == [11, 12, 13, 14]
    assert report["gameweek_tokens_in_headers"] == [12, 13, 14, 15]
    assert report["gameweek_coverage_status"] == "CSV_GAMEWEEK_HEADERS_DO_NOT_MATCH_PAGE_WINDOW"
    assert "Private Name" not in str(report)

def test_inspection_rejects_capture_hash_mismatch():
    capture = make_capture()
    capture["source"]["sha256"]["csv"] = "0" * 64
    with pytest.raises(FPLLuchoSchemaInspectionError, match="SHA-256"):
        inspect_fpl_lucho_csv_schema(capture)


def test_inspection_rejects_wrong_provider_variant():
    capture = make_capture()
    capture["provider"]["variant"] = "raw_model_xp"
    with pytest.raises(FPLLuchoSchemaInspectionError, match="provider identity"):
        inspect_fpl_lucho_csv_schema(capture)


@pytest.mark.parametrize("csv_raw", [
    b"player_id,player_id\n1,2\n",
    b"player_id,name,xP\n1,Player One\n",
    b"player_id,name,xP\n",
])
def test_inspection_rejects_ambiguous_or_invalid_csv(csv_raw):
    with pytest.raises(FPLLuchoSchemaInspectionError):
        inspect_fpl_lucho_csv_schema(make_capture(csv_raw))
