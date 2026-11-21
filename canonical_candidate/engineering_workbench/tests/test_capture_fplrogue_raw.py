import base64, hashlib, json
import pytest
from capture_fplrogue_raw import BOOTSTRAP_URL, CSV_URL, PAGE_URL, CaptureError, capture_fplrogue_raw

PAGE = b"<html><body>Gameweek GW11 Players 2 Projection engine xpts_v1 Updated 21 Nov 2026, 07:31 GMT Model trained 21 Nov 2026, 05:00 GMT</body></html>"
CSV = b"player_id,xPts,xMins\n1,8.2,86\n2,6.7,86\n"
BOOTSTRAP = json.dumps({"events":[{"id":11,"deadline_time":"2026-11-21T11:00:00Z"}]}).encode()


def run(page=PAGE, csv_data=CSV, bootstrap=BOOTSTRAP, times=None):
    responses = {PAGE_URL:(page,"text/html"), CSV_URL:(csv_data,"text/csv"),
                 BOOTSTRAP_URL:(bootstrap,"application/json")}
    ticks = iter(times or ["2026-11-21T08:00:00Z","2026-11-21T08:01:00Z","2026-11-21T08:02:00Z"])
    return capture_fplrogue_raw(season="2026-27", gameweek=11,
        fetch_bytes=lambda url:responses[url], clock=lambda:next(ticks))


def test_capture_preserves_csv_schema_hash_and_distinct_times():
    result = run()
    assert result["schema_inspection"]["csv_headers"] == ["player_id","xPts","xMins"]
    assert result["schema_inspection"]["csv_row_count"] == 2
    assert result["timing"]["provider_release_at_utc"] == "2026-11-21T07:31:00Z"
    assert result["timing"]["model_trained_at_utc"] == "2026-11-21T05:00:00Z"
    assert result["timing"]["generated_at_utc"] is None
    assert result["source"]["csv_raw_sha256"] == hashlib.sha256(CSV).hexdigest()


def test_rejects_wrong_gameweek_and_csv_count():
    with pytest.raises(CaptureError, match="does not match requested"):
        run(page=PAGE.replace(b"GW11",b"GW10"))
    with pytest.raises(CaptureError, match="row count"):
        run(csv_data=b"player_id,xPts\n1,8.2\n")


def test_rejects_late_capture_or_release():
    with pytest.raises(CaptureError, match="at or after"):
        run(times=["2026-11-21T11:00:00Z","2026-11-21T11:01:00Z","2026-11-21T11:02:00Z"])
    with pytest.raises(CaptureError, match="at or after official deadline"):
        run(page=PAGE.replace(b"07:31",b"11:01"), times=["2026-11-21T11:02:00Z","2026-11-21T11:03:00Z","2026-11-21T11:04:00Z"])


def test_rejects_duplicate_headers_and_ragged_rows():
    with pytest.raises(CaptureError, match="duplicate headers"):
        run(csv_data=b"player_id,player_id\n1,1\n2,2\n")
    with pytest.raises(CaptureError, match="inconsistent row widths"):
        run(csv_data=b"player_id,xPts\n1,8.2\n2,6.7,3\n")



def test_provider_identity_matches_active_registry():
    result = run()
    assert result["provider"]["product"] == "accepted_projections_release"
    assert result["provider"]["variant"] == "provider_native_xpts"


def test_schema_inspector_reports_exact_columns_without_semantic_mapping():
    from capture_fplrogue_raw import capture_fplrogue_raw
    from inspect_fplrogue_csv_schema import inspect_fplrogue_csv_schema

    capture = run()
    inspected = inspect_fplrogue_csv_schema(capture)
    assert [column["header"] for column in inspected["columns"]] == ["player_id", "xPts", "xMins"]
    assert inspected["row_count"] == 2
    assert all(column["semantic_mapping"] is None for column in inspected["columns"])
    assert inspected["normalization_status"] == "SCHEMA_INSPECTED_MAPPING_NOT_APPROVED"


def test_schema_inspector_rejects_ragged_and_duplicate_headers():
    from inspect_fplrogue_csv_schema import (
        FPLRogueSchemaInspectionError,
        inspect_fplrogue_csv_schema,
    )

    def raw_capture(csv_data):
        return {"capture_id": "fixture", "target_gameweek": 11,
                "source": {"csv_raw_sha256": hashlib.sha256(csv_data).hexdigest()},
                "raw_archives": {"csv_base64": base64.b64encode(csv_data).decode("ascii")}}

    with pytest.raises(FPLRogueSchemaInspectionError, match="ragged"):
        inspect_fplrogue_csv_schema(raw_capture(b"player_id,xPts\\n1,8.2,extra\\n2,9.0\\n"))
    with pytest.raises(FPLRogueSchemaInspectionError, match="duplicate"):
        inspect_fplrogue_csv_schema(raw_capture(b"player_id,player_id\\n1,8.2\\n2,6.7\\n"))
