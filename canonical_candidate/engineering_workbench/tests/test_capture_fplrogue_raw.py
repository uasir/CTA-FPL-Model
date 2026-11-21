import hashlib, json
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
        run(page=PAGE.replace(b"07:31",b"11:01"))


def test_rejects_duplicate_headers_and_ragged_rows():
    with pytest.raises(CaptureError, match="duplicate headers"):
        run(csv_data=b"player_id,player_id\n1,1\n2,2\n")
    with pytest.raises(CaptureError, match="inconsistent row widths"):
        run(csv_data=b"player_id,xPts\n1,8.2\n2,6.7,3\n")
