import json

import pytest

from capture_external_fpl_forecasts import capture, sha256, validate_payload


ROGUE_CSV = (
    "player_id,player,team,position,price,three_gw_xpts,next_gw_xpts,"
    "floor,ceiling,expected_minutes,start_probability,ownership_percent,"
    "gameweek,captured_at,model_version\n"
    "1,Player One,TST,MID,5.0,12.0,4.2,1,8,80,0.8,1.0,11,"
    "2026-11-19T09:45:00Z,xpts_v1\n"
).encode()
LUCHO_CSV = b"id,name,team,position,price,xp_gw11,fixtures_gw11\n1,Player One,TST,MID,5.0,4.2,TST\n"


def test_sideline_quant_preserves_fixture_grain_and_checks_gameweek():
    payload = {
        "gameweek": 11, "generated_at": "2026-11-18T03:33:09Z",
        "n_players": 672, "n_rows": 672, "rows": [{"player_id": 1}],
    }
    result = validate_payload(
        "sideline_quant_fixture_xp", json.dumps(payload).encode(),
        11, "application/json",
    )
    assert result["row_count"] == 672
    assert result["grain"] == "player_fixture"
    with pytest.raises(ValueError, match="gameweek mismatch"):
        validate_payload(
            "sideline_quant_fixture_xp", json.dumps(payload).encode(),
            12, "application/json",
        )


def test_provider_csv_schemas_and_variants_are_explicit():
    lucho = validate_payload("fpl_lucho_served_xp_csv", LUCHO_CSV, 11, "text/csv")
    assert lucho["row_count"] == 1
    assert lucho["player_id_column"] == "id"
    assert lucho["forecast_column"] == "xp_gw11"
    assert lucho["variant"] == "served_xP_not_assumed_Odds_xP"
    rogue = validate_payload("fpl_rogue_accepted_xpts_csv", ROGUE_CSV, 11, "text/csv")
    assert rogue["row_count"] == 1
    assert rogue["player_id_column"] == "player_id"
    assert rogue["forecast_column"] == "next_gw_xpts"
    assert rogue["variant"] == "accepted_xpts_v1"
    with pytest.raises(ValueError, match="different target gameweek"):
        validate_payload("fpl_rogue_accepted_xpts_csv", ROGUE_CSV.replace(b",11,", b",12,"), 11, "text/csv")


def test_capture_writes_exact_raw_bytes_and_hashes(tmp_path):
    payload = json.dumps({
        "gameweek": 11, "generated_at": "2026-11-18T03:33:09Z",
        "n_players": 1, "n_rows": 1, "rows": [{"player_id": 1}],
    }).encode()
    responses = {
        "https://sidelinequant.com/data/gw/11/projections.json":
            (payload, "application/json", "https://sidelinequant.com/data/gw/11/projections.json"),
        "https://www.fplrogue.com/research/projections.csv":
            (ROGUE_CSV, "text/csv", "https://www.fplrogue.com/research/projections.csv"),
        "https://fpllucho.pythonanywhere.com/export/predictions.csv":
            (LUCHO_CSV, "text/csv", "https://fpllucho.pythonanywhere.com/export/predictions.csv"),
    }
    manifest = capture(11, tmp_path, lambda url: responses[url])
    assert manifest["capture_status"] == "PASS_RAW_OUTPUTS_CAPTURED"
    for item in manifest["sources"]:
        raw = (tmp_path / item["raw_file"]).read_bytes()
        assert item["sha256"] == sha256(raw)


def test_html_response_is_not_misclassified_as_forecast_data():
    with pytest.raises(ValueError, match="HTML"):
        validate_payload("fpl_lucho_served_xp_csv", b"<html/>", 11, "text/html")
