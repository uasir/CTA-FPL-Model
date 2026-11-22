import pytest

from team_exposure_correlation import (\n    TeamExposureError, build_team_exposure_report,\n    build_team_exposure_report_from_forecast_bundle,\n)


def forecasts():
    rows = []
    for gw in range(12, 17):
        for pid, team, pos, xp in (
            (1, 1, "DEF", 5.0), (2, 1, "DEF", 4.0),
            (3, 2, "MID", 6.0), (4, 2, "FWD", 5.0),
        ):
            rows.append({"fpl_element_id": pid, "team_id": team, "position": pos,
                         "gameweek": gw, "expected_points": xp})
    return rows


def scenarios():
    rows = []
    for gw in range(12, 17):
        for scenario, clean_sheet, goals in (
            ("low", 0.0, 0.0), ("mid", 4.0, 3.0), ("high", 6.0, 8.0),
        ):
            rows.append({
                "gameweek": gw, "scenario_id": scenario,
                "scenario_set_id": "frozen-joint-scenario-set-v1",
                "forecast_snapshot_id": "fplcat-bundle-gw12-gw16",
                "model_version": "fplcat-fixture-xp-v2",
                "player_points": {
                    1: clean_sheet, 2: clean_sheet, 3: goals, 4: goals * 0.8,
                },
            })
    return rows


def scenario_provenance():
    return {
        "scenario_set_id": "frozen-joint-scenario-set-v1",
        "forecast_snapshot_id": "fplcat-bundle-gw12-gw16",
        "model_version": "fplcat-fixture-xp-v2",
        "generated_at_utc": "2026-11-22T05:30:00Z",
        "captured_at_utc": "2026-11-22T05:45:00Z",
        "source_url": "https://example.test/joint-scenarios.json",
        "raw_sha256": "a" * 64,
        "scenario_count": 15,
    }


def test_five_gameweek_team_stacking_and_joint_covariance_are_reported():
    result = build_team_exposure_report(
        squad_player_ids=[1, 2, 3, 4],
        player_gameweek_forecasts=forecasts(),
        joint_scenarios=scenarios(),
        forecast_snapshot_id="fplcat-bundle-gw12-gw16",
        model_version="fplcat-fixture-xp-v2",
        joint_scenario_provenance=scenario_provenance(),
    )
    assert result["horizon_size"] == 5
    assert result["expected_points_are_additive"] is True
    arsenal_like = next(row for row in result["team_exposure"] if row["team_id"] == 1)
    assert arsenal_like["player_count"] == 2
    assert arsenal_like["stack_type"] == "DEFENSIVE_CLEAN_SHEET_EXPOSURE"
    defensive_pair = next(row for row in result["pairwise_player_dependence"]
                          if (row["player_a_id"], row["player_b_id"]) == (1, 2))
    assert defensive_pair["correlation_horizon"] == 1.0
    assert defensive_pair["portfolio_variance_contribution"] > 0
    assert result["decision_weight"] == 0
    assert result["production_eligible"] is False


def test_no_scenarios_does_not_invent_correlation_from_same_team():
    result = build_team_exposure_report(
        squad_player_ids=[1, 2, 3, 4],
        player_gameweek_forecasts=forecasts(),
    )
    pair = next(row for row in result["pairwise_player_dependence"]
                if (row["player_a_id"], row["player_b_id"]) == (1, 2))
    assert pair["correlation_horizon"] is None
    assert pair["status"] == "NOT_ESTIMABLE_INSUFFICIENT_JOINT_SCENARIOS"
    assert result["covariance_status"] == "NOT_AVAILABLE_NO_JOINT_SCENARIOS"


def test_horizon_must_be_at_least_five_gameweeks():
    rows = [row for row in forecasts() if row["gameweek"] < 16]
    with pytest.raises(TeamExposureError, match="at least 5"):
        build_team_exposure_report(squad_player_ids=[1, 2, 3, 4],
                                   player_gameweek_forecasts=rows)


def test_incomplete_player_gameweek_coverage_fails_closed():
    rows = [row for row in forecasts() if not (row["fpl_element_id"] == 1 and row["gameweek"] == 12)]
    with pytest.raises(TeamExposureError, match="coverage is incomplete"):
        build_team_exposure_report(squad_player_ids=[1, 2, 3, 4],
                                   player_gameweek_forecasts=rows)


def test_duplicate_player_gameweek_forecast_is_rejected():
    rows = forecasts()
    rows.append(dict(rows[0]))
    with pytest.raises(TeamExposureError, match="duplicate"):
        build_team_exposure_report(squad_player_ids=[1, 2, 3, 4],
                                   player_gameweek_forecasts=rows)


def test_joint_scenarios_require_snapshot_and_scenario_set_provenance():
    with pytest.raises(TeamExposureError, match="joint_scenario_provenance is required"):
        build_team_exposure_report(
            squad_player_ids=[1, 2, 3, 4],
            player_gameweek_forecasts=forecasts(),
            joint_scenarios=scenarios(),
        )


def test_joint_scenario_snapshot_mismatch_is_rejected():
    rows = scenarios()
    rows[0]["forecast_snapshot_id"] = "different-bundle"
    with pytest.raises(TeamExposureError, match="does not match forecast bundle"):
        build_team_exposure_report(
            squad_player_ids=[1, 2, 3, 4],
            player_gameweek_forecasts=forecasts(),
            joint_scenarios=rows,
            forecast_snapshot_id="fplcat-bundle-gw12-gw16",
            model_version="fplcat-fixture-xp-v2",
            joint_scenario_provenance=scenario_provenance(),
        )


def test_incomplete_joint_scenario_player_vector_is_rejected():
    rows = scenarios()
    rows[0]["player_points"].pop(4)
    with pytest.raises(TeamExposureError, match="missing squad players"):
        build_team_exposure_report(
            squad_player_ids=[1, 2, 3, 4],
            player_gameweek_forecasts=forecasts(),
            joint_scenarios=rows,
            forecast_snapshot_id="fplcat-bundle-gw12-gw16",
            model_version="fplcat-fixture-xp-v2",
            joint_scenario_provenance=scenario_provenance(),
        )


def test_insufficient_scenarios_in_any_gameweek_is_rejected():
    rows = [row for row in scenarios() if not (row["gameweek"] == 14 and row["scenario_id"] in {"mid", "high"})]
    provenance = scenario_provenance()
    provenance["scenario_count"] = len(rows)
    with pytest.raises(TeamExposureError, match="at least two complete"):
        build_team_exposure_report(
            squad_player_ids=[1, 2, 3, 4],
            player_gameweek_forecasts=forecasts(),
            joint_scenarios=rows,
            forecast_snapshot_id="fplcat-bundle-gw12-gw16",
            model_version="fplcat-fixture-xp-v2",
            joint_scenario_provenance=provenance,
        )


def test_joint_scenario_hash_and_generation_timing_are_validated():
    provenance = scenario_provenance()
    provenance["raw_sha256"] = "not-a-hash"
    with pytest.raises(TeamExposureError, match="64-character SHA-256"):
        build_team_exposure_report(
            squad_player_ids=[1, 2, 3, 4],
            player_gameweek_forecasts=forecasts(),
            joint_scenarios=scenarios(),
            forecast_snapshot_id="fplcat-bundle-gw12-gw16",
            model_version="fplcat-fixture-xp-v2",
            joint_scenario_provenance=provenance,
        )


def forecast_bundle():
    return {
        "forecast_bundle_id": "fplcat-bundle-gw12-gw16",
        "forecast_snapshot_id": "fplcat-bundle-gw12-gw16",
        "model_version": "fplcat-fixture-xp-v2",
        "horizon_gameweeks": [12, 13, 14, 15, 16],
        "source_snapshot_ids": [f"immutable-gw{gw}" for gw in range(12, 17)],
        "player_gameweek_forecasts": forecasts(),
    }


def test_verified_forecast_bundle_connects_to_tecm_without_inventing_covariance():
    result = build_team_exposure_report_from_forecast_bundle(
        forecast_bundle(), squad_player_ids=[1, 2, 3, 4]
    )
    assert result["forecast_snapshot_id"] == "fplcat-bundle-gw12-gw16"
    assert result["model_version"] == "fplcat-fixture-xp-v2"
    assert result["horizon_gameweeks"] == [12, 13, 14, 15, 16]
    assert result["covariance_status"] == "NOT_AVAILABLE_NO_JOINT_SCENARIOS"
    assert result["decision_weight"] == 0
    assert result["production_eligible"] is False


def test_tecm_rejects_mismatched_forecast_bundle_identity():
    source = forecast_bundle()
    source["forecast_snapshot_id"] = "other-snapshot"
    with pytest.raises(TeamExposureError, match="bundle and snapshot IDs"):
        build_team_exposure_report_from_forecast_bundle(
            source, squad_player_ids=[1, 2, 3, 4]
        )


def test_tecm_bundle_adapter_accepts_provenance_bound_joint_scenarios():
    result = build_team_exposure_report_from_forecast_bundle(
        forecast_bundle(),
        squad_player_ids=[1, 2, 3, 4],
        joint_scenarios=scenarios(),
        joint_scenario_provenance=scenario_provenance(),
    )
    assert result["covariance_status"] == "JOINT_SCENARIO_ESTIMATE"
    assert result["joint_scenario_provenance"]["scenario_set_id"] == "frozen-joint-scenario-set-v1"
