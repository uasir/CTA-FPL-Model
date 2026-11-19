import json

import pytest

from capture_external_fpl_forecasts import capture, sha256, validate_payload


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


def test_csv_outputs_are_labelled_without_inventing_variant_or_schema():
    raw = b"fpl_id,player_name,gw11_xp\n1,Player One,4.2\n"
    result = validate_payload("fpl_lucho_served_xp_csv", raw, 11, "text/csv")
    assert result["row_count"] == 1
    assert result["variant"] == "served_xP_not_assumed_Odds_xP"
    rogue = validate_payload("fpl_rogue_accepted_xpts_csv", raw, 11, "text/csv")
    assert rogue["variant"] == "accepted_xpts_v1"
    assert sha256(raw) == sha256(raw)


def test_capture_writes_exact_raw_bytes_and_hashes(tmp_path):
    payload = json.dumps({
        "gameweek": 11, "generated_at": "2026-11-18T03:33:09Z",
        "n_players": 1, "n_rows": 1, "rows": [{"player_id": 1}],
    }).encode()
    csv_bytes = b"id,name,xp\n1,Player One,4.2\n"
    responses = {
        "https://sidelinequant.com/data/gw/11/projections.json":
            (payload, "application/json", "https://sidelinequant.com/data/gw/11/projections.json"),
        "https://www.fplrogue.com/research/projections.csv":
            (csv_bytes, "text/csv", "https://www.fplrogue.com/research/projections.csv"),
        "https://fpllucho.pythonanywhere.com/export/predictions.csv":
            (csv_bytes, "text/csv", "https://fpllucho.pythonanywhere.com/export/predictions.csv"),
    }
    manifest = capture(11, tmp_path, lambda url: responses[url])
    assert manifest["capture_status"] == "PASS_RAW_OUTPUTS_CAPTURED"
    for item in manifest["sources"]:
        raw = (tmp_path / item["raw_file"]).read_bytes()
        assert item["sha256"] == sha256(raw)


def test_html_response_is_not_misclassified_as_forecast_data():
    with pytest.raises(ValueError, match="HTML"):
        validate_payload("fpl_lucho_served_xp_csv", b"<html/>", 11, "text/html")
