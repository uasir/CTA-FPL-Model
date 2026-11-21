import base64
import hashlib

import pytest

from inspect_fpl_lucho_csv_schema import (
    FPLLuchoSchemaInspectionError,
    inspect_fpl_lucho_csv_schema,
)


def make_capture(csv_raw=b"player_id,player_name,xP_GW11,xP_GW12\n1,Player One,5.2,4.8\n2,Player Two,3.1,4.2\n"):
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
    assert report["column_count"] == 4
    assert report["gameweek_tokens_in_headers"] == [11, 12]
    assert report["normalization_status"] == "SCHEMA_INSPECTED_MAPPING_NOT_APPROVED"
    assert report["privacy"] == "NO_PLAYER_ROW_VALUES_EMITTED"
    assert all(column["semantic_mapping"] is None for column in report["columns"])
    assert "Player One" not in str(report)
    assert "5.2" not in str(report)


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
