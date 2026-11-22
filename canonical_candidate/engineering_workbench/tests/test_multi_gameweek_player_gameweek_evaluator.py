import pytest

from multi_gameweek_transfer_evaluator import (
    MultiGameweekTransferError,
    evaluate_multi_gameweek_transfer_bundle,
)


def payload():
    weeks = [12, 13, 14, 15, 16, 17]
    positions = {
        1: "GKP", 2: "GKP",
        3: "DEF", 4: "DEF", 5: "DEF", 6: "DEF", 7: "DEF",
        8: "MID", 9: "MID", 10: "MID", 11: "MID", 12: "MID",
        13: "FWD", 14: "FWD", 15: "FWD", 16: "FWD",
    }
    rows = []
    for gw in weeks:
        for pid, position in positions.items():
            xp = 8.0 if pid == 16 else (2.0 if pid == 15 else 3.0)
            rows.append({
                "fpl_element_id": pid, "gameweek": gw,
                "expected_points": xp, "expected_minutes": 80,
                "team_id": ((pid - 1) // 3) + 1,
                "position": position,
            })
    return {
        "forecast_bundle": {
            "forecast_bundle_id": "fplcat-six-gw-bundle",
            "forecast_snapshot_id": "fplcat-provider-snapshot-hash",
            "provider_source_id": "fpl_cat_partner_projections",
            "provider": {
                "name": "FPL Cat", "product": "partner_projections",
                "variant": "provider_native_xp", "version": "partner-api-v1",
            },
            "model_version": "provider_model_version_not_disclosed",
            "contract_version": "1.0.0-player-gameweek",
            "forecast_grain": "player_gameweek",
            "horizon_gameweeks": weeks,
            "source_snapshot_ids": ["fplcat-provider-snapshot-hash"],
            "player_gameweek_forecasts": rows,
            "fixture_forecasts": None,
        },
        "squad_ids": list(range(1, 16)),
        "starting_xi_ids": [1, 3, 4, 5, 6, 8, 9, 10, 11, 13, 14],
        "transfer_out_id": 15,
        "transfer_in_id": 16,
        "bank": 0.0,
        "selling_price": 5.0,
        "incoming_price": 5.0,
        "free_transfers": 1,
        "hit_cost_points": 4,
    }


def test_evaluates_six_gw_native_player_gameweek_forecasts_without_fixture_detail():
    result = evaluate_multi_gameweek_transfer_bundle(payload())
    assert result["forecast_grain"] == "player_gameweek"
    assert result["horizon_gameweeks"] == [12, 13, 14, 15, 16, 17]
    assert result["action"] == "TRANSFER"
    assert result["gross_horizon_expected_points_delta"] == 30.0
    assert result["fixture_level_transfer_player_detail"] is None
    assert result["transfer"]["hit_cost_points_applied"] == 0


def test_aggregate_grain_rejects_fabricated_fixture_rows():
    source = payload()
    source["forecast_bundle"]["fixture_forecasts"] = [
        {"fpl_element_id": 16, "gameweek": 12, "fixture_id": 123, "expected_points": 8, "expected_minutes": 80}
    ]
    with pytest.raises(MultiGameweekTransferError, match="must not contain fabricated"):
        evaluate_multi_gameweek_transfer_bundle(source)


def test_aggregate_grain_rejects_multiple_unrelated_source_snapshots():
    source = payload()
    source["forecast_bundle"]["source_snapshot_ids"] = ["snap-1", "snap-2", "snap-3", "snap-4", "snap-5", "snap-6"]
    with pytest.raises(MultiGameweekTransferError, match="unique immutable provider snapshot"):
        evaluate_multi_gameweek_transfer_bundle(source)
