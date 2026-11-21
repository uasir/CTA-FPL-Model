import base64
import json

import pytest

from capture_fpl_lucho_raw import CaptureError, capture_fpl_lucho_raw


PAGE = """<html><body>Built: 21-Nov-2026 09:13 UTC · next GW: 11 xP model last calculated: Sat 21 Nov 2026, 09:03 UTC</body></html>""".encode("utf-8")
CSV = b"player_id,player_name,xP_GW11,xP_GW12\n1,Player One,5.2,4.8\n2,Player Two,3.1,4.2\n"
BOOTSTRAP = json.dumps({
    "events": [{"id": 11, "deadline_time": "2026-11-22T14:00:00Z"}]
}).encode()


def make_capture(*, gameweek=11, csv_raw=CSV, page_raw=PAGE, deadline="2026-11-22T14:00:00Z"):
    payloads = {
        "https://fpllucho.pythonanywhere.com/forecast": (page_raw, "text/html; charset=utf-8"),
        "https://fpllucho.pythonanywhere.com/export/predictions.csv": (csv_raw, "text/csv"),
        "https://fantasy.premierleague.com/api/bootstrap-static/": (
            json.dumps({"events": [{"id": 11, "deadline_time": deadline}]}).encode(),
            "application/json",
        ),
    }
    def fetch(url):
        return payloads[url]
    times = iter([
        "2026-11-21T09:14:00Z",
        "2026-11-21T09:14:01Z",
        "2026-11-21T09:14:02Z",
    ])
    return capture_fpl_lucho_raw(
        season="2026-27", gameweek=gameweek, fetch=fetch, clock=lambda: next(times)
    )


def test_capture_preserves_served_variant_and_raw_csv_without_guessing_columns():
    result = make_capture()
    assert result["provider"]["name"] == "FPL Lucho"
    assert result["provider"]["product"] == "forecast_csv"
    assert result["provider"]["variant"] == "served_odds_anchored_xp"
    from forecast_provider_registry import get_active_provider
    registered = get_active_provider("FPL Lucho")
    assert result["provider"]["product"] == registered["product"]
    assert result["provider"]["variant"] == registered["forecast_variant"]
    assert result["timing"]["generated_at_utc"] is None
    assert result["timing"]["page_built_at_utc"] == "2026-11-21T09:13:00Z"
    assert result["timing"]["raw_model_last_calculated_at_utc"] == "2026-11-21T09:03:00Z"
    assert result["schema_inspection"]["csv_headers"] == [
        "player_id", "player_name", "xP_GW11", "xP_GW12"
    ]
    assert result["schema_inspection"]["csv_row_count"] == 2
    assert base64.b64decode(result["raw_archives"]["csv_base64"]) == CSV


def test_capture_rejects_wrong_target_gameweek():
    with pytest.raises(CaptureError, match="does not match requested"):
        make_capture(gameweek=12)


def test_capture_rejects_post_deadline_capture():
    with pytest.raises(CaptureError, match="at or after"):
        make_capture(deadline="2026-11-21T09:14:01Z")


def test_capture_rejects_duplicate_csv_headers():
    with pytest.raises(CaptureError, match="duplicate headers"):
        make_capture(csv_raw=b"player_id,player_id\n1,2\n")


def test_capture_rejects_inconsistent_csv_row_width():
    with pytest.raises(CaptureError, match="inconsistent column counts"):
        make_capture(csv_raw=b"player_id,name,xP\n1,Player One\n")

def test_capture_marks_csv_gameweek_coverage_unverified_until_columns_are_mapped():
    result = make_capture()
    assert result["coverage"]["provider_advertised_forecast_window_gameweeks"] == 4
    assert result["coverage"]["csv_gameweek_coverage_status"] == (
        "UNVERIFIED_PENDING_EXPLICIT_COLUMN_MAPPING"
    )


def test_capture_rejects_headers_that_duplicate_after_whitespace_normalization():
    with pytest.raises(CaptureError, match="after whitespace normalization"):
        make_capture(csv_raw=b"player_id, player_id \n1,2\n")

