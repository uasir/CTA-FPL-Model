from build_manager_cta_coverage_report import build_report


def player_forecast(element, verified, prior, position):
    return {
        "fpl_element_id": element,
        "cta": {
            "identity_verified": verified,
            "source_snapshot_as_of": "2026-11-10T12:21:18+00:00",
            "fixtures": [{
                "prior_matches_count": prior,
                "snapshot_available_as_of_deadline": True,
                "features": {
                    "cta_prior3_matches_shots_avg": 2.0 if prior else None,
                    "cta_prior3_matches_key_passes_avg": 1.0 if prior else None,
                },
            }],
        },
    }


def picks_payload():
    return {
        "entry_history": {"event": 11, "bank": 9, "value": 1005},
        "picks": [
            {
                "element": i,
                "position": i,
                "is_captain": i == 1,
                "is_vice_captain": i == 2,
            }
            for i in range(1, 16)
        ],
    }


def snapshot():
    return {
        "forecast_snapshot_id": "snapshot-1",
        "forecast_quality": {"data_coverage": {"target_gameweek": 11}},
        "player_forecasts": [
            player_forecast(i, i <= 8, 3 if i <= 6 else 0, i)
            for i in range(1, 16)
        ],
    }


def test_manager_cta_coverage_uses_real_picks_and_keeps_decision_weight_zero():
    report = build_report(421025, picks_payload(), snapshot())
    assert report["status"] == "PASS_MANAGER_CTA_COVERAGE"
    assert report["entry_id"] == 421025
    assert report["squad_size"] == 15
    assert report["starting_xi_count"] == 11
    assert report["bench_count"] == 4
    assert report["squad_players_with_verified_identity"] == 8
    assert report["squad_players_with_prior_history"] == 6
    assert report["squad_players_with_cta_evidence"] == 6
    assert report["starting_xi_with_cta_evidence"] == 6
    assert report["bench_with_cta_evidence"] == 0
    assert report["captain_has_cta_evidence"] is True
    assert report["vice_captain_has_cta_evidence"] is True
    assert report["cta_decision_weight_applied"] is False
    assert report["cta_ranking_effect"] == "NONE"
    assert report["free_transfers_status"] == "NOT_READ_FROM_PUBLIC_PICKS_ENDPOINT"


def test_manager_report_is_partial_when_forecast_is_missing_for_a_pick():
    data = snapshot()
    data["player_forecasts"] = data["player_forecasts"][:-1]
    report = build_report(421025, picks_payload(), data)
    assert report["status"] == "PARTIAL_MANAGER_CTA_COVERAGE"
    assert report["forecast_missing_squad_players"] == 1


def test_duplicate_player_ids_fail_closed():
    payload = picks_payload()
    payload["picks"][1]["element"] = payload["picks"][0]["element"]
    try:
        build_report(421025, payload, snapshot())
    except ValueError as exc:
        assert "duplicate FPL element" in str(exc)
    else:
        raise AssertionError("duplicate player IDs must fail closed")



def test_manager_picks_event_must_match_forecast_gameweek():
    payload = picks_payload()
    payload["entry_history"]["event"] = 10
    try:
        build_report(421025, payload, snapshot())
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("picks from a different gameweek must be rejected")
