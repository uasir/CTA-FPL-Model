import base64
import hashlib
import json

import pytest

from parse_sideline_quant_snapshot import (
    SidelineQuantParseError,
    parse_sideline_quant_capture,
)


def make_capture(rows=None):
    rows = rows or [
        {"player_id": 1, "fixture_id": 101, "gameweek": 11, "xP": 2.2,
         "e_mins": 80, "p_start": 0.9, "sigma": 2.1, "gw_sigma": 3.4, "gw_p10": 1.2, "gw_p90": 8.7},
        {"player_id": 1, "fixture_id": 102, "gameweek": 11, "xP": 3.3,
         "e_mins": 75, "p_start": 0.85, "sigma": 2.0, "gw_sigma": 3.4, "gw_p10": 1.2, "gw_p90": 8.7},
        {"player_id": 2, "fixture_id": 103, "gameweek": 11, "xP": 4.0,
         "e_mins": 90, "p_start": 0.99, "sigma": 1.5, "gw_sigma": 1.5, "gw_p10": 2.0, "gw_p90": 6.0},
    ]
    provider = {
        "schema_version": "1.0",
        "generated_at": "2026-11-20T08:00:00Z",
        "gameweek": 11,
        "deadline": "2026-11-21T11:00:00Z",
        "n_players": 2,
        "n_rows": len(rows),
        "rows": rows,
    }
    bootstrap = {"elements": [{"id": 1}, {"id": 2}, {"id": 3}]}
    raw = json.dumps(provider).encode()
    boot = json.dumps(bootstrap).encode()
    return {
        "capture_id": "sq-gw11-test",
        "season": "2026-27",
        "target_gameweek": 11,
        "provider": {"name": "Sideline Quant"},
        "timing": {
            "generated_at_utc": "2026-11-20T08:00:00Z",
            "captured_at_utc": "2026-11-20T09:00:00Z",
            "deadline_utc": "2026-11-21T11:00:00Z",
        },
        "source": {
            "url": "https://sidelinequant.com/data/gw/11/projections.json",
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_snapshot_id": "sha256:" + hashlib.sha256(raw).hexdigest(),
        },
        "coverage": {"declared_row_count": len(rows)},
        "raw_archives": {
            "provider_response_base64": base64.b64encode(raw).decode(),
            "official_fpl_bootstrap_base64": base64.b64encode(boot).decode(),
        },
    }


def test_preserves_fixture_grain_and_native_rows():
    result = parse_sideline_quant_capture(make_capture())
    snapshot = result["canonical_snapshot"]
    assert snapshot["grain"] == "player_fixture"
    assert snapshot["coverage"]["identity_resolution_status"] == "VERIFIED"
    assert len(snapshot["records"]) == 3
    assert snapshot["records"][0]["fixture_id"] == 101
    assert result["provider_native_rows"][0]["gw_sigma"] == 3.4
    assert result["aggregation_provenance"]["native_fixture_rows_preserved"] is True


def test_explicitly_sums_fixture_xp_for_double_gameweek_player():
    result = parse_sideline_quant_capture(make_capture())
    by_id = {row["fpl_element_id"]: row for row in result["player_gameweek_sum_xp"]}
    assert by_id[1]["expected_points"] == pytest.approx(5.5)
    assert by_id[1]["expected_minutes"] == pytest.approx(155.0)
    assert by_id[1]["fixture_count"] == 2
    assert by_id[1]["aggregation"] == "SUM_OF_PROVIDER_FIXTURE_XP_AND_EXPECTED_MINUTES"
    assert by_id[2]["expected_points"] == pytest.approx(4.0)
    assert by_id[2]["expected_minutes"] == pytest.approx(90.0)


def test_maps_publisher_gameweek_distribution_without_summing_it():
    result = parse_sideline_quant_capture(make_capture())
    by_id = {row["fpl_element_id"]: row for row in result["player_gameweek_sum_xp"]}
    # gw_sigma is the published SD of the player's total GW points; the
    # canonical contract stores variance, so square it exactly once.
    assert by_id[1]["points_variance"] == pytest.approx(3.4 ** 2)
    assert by_id[1]["q10"] == pytest.approx(1.2)
    assert by_id[1]["q90"] == pytest.approx(8.7)
    assert by_id[2]["points_variance"] == pytest.approx(1.5 ** 2)
    assert "p_start" not in by_id[1]
    assert "sigma" not in by_id[1]
    assert "gw_sigma" not in by_id[1]
    assert result["aggregation_provenance"]["gameweek_distribution_fields"][
        "consistency_checked_across_fixture_rows"
    ] is True


def test_rejects_inconsistent_gameweek_distribution_across_fixtures():
    capture = make_capture()
    provider = json.loads(base64.b64decode(capture["raw_archives"]["provider_response_base64"]))
    provider["rows"][1]["gw_sigma"] = 9.9
    raw = json.dumps(provider).encode()
    capture["raw_archives"]["provider_response_base64"] = base64.b64encode(raw).decode()
    capture["source"]["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    capture["source"]["raw_snapshot_id"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    with pytest.raises(SidelineQuantParseError, match="inconsistent gw_sigma"):
        parse_sideline_quant_capture(capture)


def test_rejects_invalid_fpl_player_identity():
    capture = make_capture()
    provider = json.loads(base64.b64decode(capture["raw_archives"]["provider_response_base64"]))
    provider["rows"][0]["player_id"] = 99999
    raw = json.dumps(provider).encode()
    capture["raw_archives"]["provider_response_base64"] = base64.b64encode(raw).decode()
    capture["source"]["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    capture["source"]["raw_snapshot_id"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    with pytest.raises(SidelineQuantParseError, match="valid FPL element ID"):
        parse_sideline_quant_capture(capture)


def test_rejects_duplicate_player_fixture_key():
    capture = make_capture()
    provider = json.loads(base64.b64decode(capture["raw_archives"]["provider_response_base64"]))
    provider["rows"][1]["fixture_id"] = provider["rows"][0]["fixture_id"]
    raw = json.dumps(provider).encode()
    capture["raw_archives"]["provider_response_base64"] = base64.b64encode(raw).decode()
    capture["source"]["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    capture["source"]["raw_snapshot_id"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    with pytest.raises(SidelineQuantParseError, match="duplicate player-fixture"):
        parse_sideline_quant_capture(capture)


def test_rejects_bad_gameweek_or_declared_counts():
    capture = make_capture()
    provider = json.loads(base64.b64decode(capture["raw_archives"]["provider_response_base64"]))
    provider["rows"][0]["gameweek"] = 10
    raw = json.dumps(provider).encode()
    capture["raw_archives"]["provider_response_base64"] = base64.b64encode(raw).decode()
    capture["source"]["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    capture["source"]["raw_snapshot_id"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    with pytest.raises(SidelineQuantParseError, match="gameweek"):
        parse_sideline_quant_capture(capture)



def test_builds_canonical_player_gameweek_snapshot_with_provenance():
    from parse_sideline_quant_snapshot import build_sideline_quant_player_gameweek_snapshot

    result = parse_sideline_quant_capture(make_capture())
    derived = result["player_gameweek_snapshot"]
    assert derived["grain"] == "player_gameweek"
    assert derived["coverage"]["identity_resolution_status"] == "VERIFIED"
    assert derived["provider"]["product"] == "gameweek_projections"
    assert derived["provider"]["variant"] == "provider_native_xp"
    assert derived["records"][0]["expected_points"] == pytest.approx(5.5)
    assert derived["records"][0]["expected_minutes"] == pytest.approx(155.0)
    assert derived["records"][0]["points_variance"] == pytest.approx(3.4 ** 2)
    assert derived["coverage"]["source_fixture_row_count"] == 3
    assert derived["decision_eligible"] is True


def test_rejects_unprovenanced_or_wrong_source_aggregation():
    from parse_sideline_quant_snapshot import (
        SidelineQuantParseError,
        build_sideline_quant_player_gameweek_snapshot,
    )

    result = parse_sideline_quant_capture(make_capture())
    rows = result["player_gameweek_sum_xp"]
    rows[0]["aggregation"] = "UNVERIFIED_SUM"
    with pytest.raises(SidelineQuantParseError, match="lacks documented sum-xP/expected-minutes provenance"):
        build_sideline_quant_player_gameweek_snapshot(result["canonical_snapshot"], rows)
