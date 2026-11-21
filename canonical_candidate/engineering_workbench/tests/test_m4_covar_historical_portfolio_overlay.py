from __future__ import annotations

from m4_covar_historical_portfolio_overlay import build_historical_covar_recommendation_overlay


def make_inputs():
    forecasts = [
        {"fpl_element_id": pid, "expected_points": points, "expected_minutes": 90, "position": pos}
        for pid, points, pos in [
            (1, 5, "GKP"), (2, 4, "DEF"), (3, 5, "DEF"), (4, 6, "DEF"),
            (5, 7, "DEF"), (6, 4, "MID"), (7, 5, "MID"), (8, 6, "MID"),
            (9, 7, "MID"), (10, 8, "MID"), (11, 9, "FWD"), (12, 6, "FWD"),
            (13, 5, "FWD"), (14, 4, "GKP"), (15, 3, "DEF"), (16, 10, "MID"), (17, 8, "DEF"),
        ]
    ]
    recommendation = {
        "system": "personal_squad",
        "forecast_snapshot_id": "snapshot-1",
        "model_version": "m3-conventional-v1",
        "current_squad_plan": {
            "starting_xi": list(range(1, 12)),
            "captain": 11,
        },
        "transfer_recommendation": {
            "alternatives": [
                {"transfer_out_id": 10, "transfer_in_id": 16},
                {"transfer_out_id": 15, "transfer_in_id": 17},
            ]
        },
    }
    ids = list(range(1, 18))
    pairs = []
    for i, left in enumerate(ids):
        for right in ids[i:]:
            if left == right:
                value = 4.0
            else:
                value = 0.2 if left % 2 == right % 2 else -0.1
            pairs.append({
                "player1_id": str(left),
                "player2_id": str(right),
                "shrunk_covariance": value,
            })
    pairs = [{**row, "shrunk_covariance": str(row["shrunk_covariance"])} for row in pairs]
    report = {
        "status": "EXPLORATORY_ONLY",
        "model_trained": False,
        "point_in_time_status": "NOT_VERIFIED",
        "window_gameweeks": [1, 2, 3, 4, 5],
        "window_size": 5,
        "shrinkage": {
            "type": "diagonal",
            "parameter": 0.5,
            "positive_semidefinite_by_construction": True,
        },
    }
    return recommendation, forecasts, report, pairs


def test_overlay_uses_conventional_means_and_historical_covariance_without_changing_decision():
    recommendation, forecasts, report, pairs = make_inputs()
    result = build_historical_covar_recommendation_overlay(
        recommendation=recommendation,
        forecast_rows=forecasts,
        covariance_report=report,
        covariance_pairs=pairs,
    )
    assert result["status"] == "AVAILABLE_HISTORICAL_COVAR_PROXY"
    assert result["decision_weight"] == 0
    assert result["production_eligible"] is False
    assert result["field_comparison_status"] == "NOT_AVAILABLE_NO_JOINT_FIELD_PORTFOLIOS"
    assert len(result["candidate_metrics"]) == 2
    assert result["baseline"]["status"] == "COMPUTED_HISTORICAL_PROXY"
    assert result["candidate_metrics"][0]["expected_points_delta_vs_current"] > 0
    assert result["pareto_frontier_transfer_pairs"]


def test_overlay_fails_closed_when_any_player_lacks_covariance_history():
    recommendation, forecasts, report, pairs = make_inputs()
    pairs = [row for row in pairs if row["player1_id"] != "1" or row["player2_id"] != "1"]
    result = build_historical_covar_recommendation_overlay(
        recommendation=recommendation,
        forecast_rows=forecasts,
        covariance_report=report,
        covariance_pairs=pairs,
    )
    assert result["status"] == "NOT_AVAILABLE_INCOMPLETE_COVARIANCE_COVERAGE"
    assert "1" in result["missing_player_ids"]
    assert result["candidate_metrics"] == []


def test_overlay_rejects_duplicate_covariance_pairs():
    recommendation, forecasts, report, pairs = make_inputs()
    pairs.append(pairs[0])
    try:
        build_historical_covar_recommendation_overlay(
            recommendation=recommendation,
            forecast_rows=forecasts,
            covariance_report=report,
            covariance_pairs=pairs,
        )
    except ValueError as exc:
        assert "duplicate covariance pair" in str(exc)
    else:
        raise AssertionError("duplicate covariance pair was accepted")


def test_overlay_rejects_non_exploratory_or_untrained_covariance():
    recommendation, forecasts, report, pairs = make_inputs()
    report["model_trained"] = True
    try:
        build_historical_covar_recommendation_overlay(
            recommendation=recommendation,
            forecast_rows=forecasts,
            covariance_report=report,
            covariance_pairs=pairs,
        )
    except ValueError as exc:
        assert "not a trained CoVar model" in str(exc)
    else:
        raise AssertionError("trained covariance report was accepted by historical-only overlay")



def test_overlay_rejects_position_mismatched_transfer():
    recommendation, forecasts, report, pairs = make_inputs()
    recommendation["transfer_recommendation"]["alternatives"][0]["transfer_in_id"] = 17
    try:
        build_historical_covar_recommendation_overlay(
            recommendation=recommendation,
            forecast_rows=forecasts,
            covariance_report=report,
            covariance_pairs=pairs,
        )
    except ValueError as exc:
        assert "preserve the outgoing player's position" in str(exc)
    else:
        raise AssertionError("position-mismatched transfer was accepted")


def test_bench_transfer_that_cannot_displace_a_stronger_starter_keeps_xi_unchanged():
    recommendation, forecasts, report, pairs = make_inputs()
    next(row for row in forecasts if row["fpl_element_id"] == 17)["expected_points"] = 3.0
    result = build_historical_covar_recommendation_overlay(
        recommendation=recommendation,
        forecast_rows=forecasts,
        covariance_report=report,
        covariance_pairs=pairs,
    )
    baseline_xi = recommendation["current_squad_plan"]["starting_xi"]
    bench_candidate = next(row for row in result["candidate_metrics"] if row["transfer_out_id"] == 15)
    assert bench_candidate["starting_xi_ids"] == baseline_xi
    assert bench_candidate["expected_points_delta_vs_current"] == 0.0
    assert bench_candidate["variance_delta_vs_current"] == 0.0
