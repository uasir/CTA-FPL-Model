import csv
import hashlib
import io
import json

import pytest

from capture_fplrogue_raw import (
    BOOTSTRAP_URL,
    CSV_URL,
    PAGE_URL,
    CaptureError,
    capture_fplrogue_raw,
)


PAGE = b"""
<html><body>
Gameweek GW11
Players 2
Projection engine xpts_v1
Updated 21 Nov 2026, 07:31 GMT
Model trained 21 Nov 2026, 05:00 GMT
</body></html>
"""
CSV = b"player_id,xPts,xMins\n1,8.2,86\n2,6.7,86\n"
BOOTSTRAP = json.dumps({
    "events": [{"id": 11, "deadline_time": "2026-11-21T11:00:00Z"}]
}).encode()


def run_capture(page=PAGE, csv_data=CSV, bootstrap=BOOTSTRAP, times=None):
    responses = {
        PAGE_URL: (page, "text/html; charset=utf-8"),
        CSV_URL: (csv_data, "text/csv"),
        BOOTSTRAP_URL: (bootstrap, "application/json"),
    }
    clock_values = iter(times or [
        "2026-11-21T08:00:00Z",
        "2026-11-21T08:01:00Z",
        "2026-11-21T08:02:00Z",
    ])
    return capture_fplrogue_raw(
        season="2026-27",
        gameweek=11,
        fetch_bytes=lambda url: responses[url],
        clock=lambda: next(clock_values),
    )


def test_captures_csv_schema_raw_hash_and_provider_timestamps():
    result = run_capture()
    assert result["schema_inspection"]["csv_headers"] == ["player_id", "xPts", "xMins"]
    assert result["schema_inspection"]["csv_row_count"] == 2
    assert result["timing"]["provider_release_at_utc"] == "2026-11-21T07:31:00Z"
    assert result["timing"]["model_trained_at_utc"] == "2026-11-21T05:00:00Z"
    assert result["timing"]["generated_at_utc"] is None
    assert result["timing"]["generation_time_status"] == "NOT_DISCLOSED_AS_DISTINCT_FORECAST_GENERATION_TIME"
    assert result["source"]["csv_raw_sha256"] == hashlib.sha256(CSV).hexdigest()


def test_rejects_wrong_gameweek_or_page_csv_count_mismatch():
    page = PAGE.replace(b"GW11", b"GW10")
    with pytest.raises(CaptureError, match="does not match requested"):
        run_capture(page=page)
    with pytest.raises(CaptureError, match="row count"):
        run_capture(csv_data=b"player_id,xPts\n1,8.2\n")


def test_rejects_post_deadline_capture_and_update():
    with pytest.raises(CaptureError, match="at or after"):
        run_capture(times=[
            "2026-11-21T11:00:00Z",
            "2026-11-21T11:01:00Z",
            "2026-11-21T11:02:00Z",
        ])
    page = PAGE.replace(b"07:31", b"11:01")
    with pytest.raises(CaptureError, match="at or after deadline"):
        run_capture(page=page)


def test_rejects_duplicate_csv_headers_and_ragged_rows():
    with pytest.raises(CaptureError, match="duplicate columns"):
        run_capture(csv_data=b"player_id,player_id\n1,1\n2,2\n")
    with pytest.raises(CaptureError, match="inconsistent column counts"):
        run_capture(csv_data=b"player_id,xPts\n1,8.2\n2,6.7,3\n")
