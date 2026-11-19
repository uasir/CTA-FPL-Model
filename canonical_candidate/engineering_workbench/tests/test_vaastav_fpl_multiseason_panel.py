from build_vaastav_fpl_multiseason_panel import build_season_rows, evaluate, read_csv_bytes, source_gameweek
from train_fpl_exploratory_ridge import FEATURES


def source_row(element, gw, points, minutes=90, xg="0.2", xa="0.1", fixture=1, home="True"):
    return {
        "element": str(element),
        "round": str(gw),
        "kickoff_time": f"2024-08-{gw:02d}T12:00:00Z",
        "minutes": str(minutes),
        "total_points": str(points),
        "expected_goals": xg,
        "expected_assists": xa,
        "was_home": home,
        "fixture": str(fixture),
        # Deliberately present: must never enter the predictor.
        "xP": "999",
        "selected": "999999",
        "modified": "2024-08-30T00:00:00Z",
    }


def test_builder_uses_only_prior_gameweeks_and_aggregates_double_gameweeks():
    rows = [
        source_row(10, 1, 4, xg="0.1", xa="0.0", fixture=1),
        source_row(10, 2, 6, xg="0.3", xa="0.2", fixture=2),
        source_row(10, 3, 2, xg="0.1", xa="0.0", fixture=3),
        source_row(10, 3, 3, xg="0.2", xa="0.1", fixture=4, home="False"),
    ]
    panel = build_season_rows("2024-25", rows)
    gw3 = [row for row in panel if row["gameweek"] == 3]
    assert len(gw3) == 2
    for row in gw3:
        assert row["prior_gw_points"] == 6
        assert row["prior3_gw_points_avg"] == 5
        assert row["prior5_gw_points_avg"] == 5
        assert row["prior3_gw_xg_avg"] == 0.2
        assert row["prior5_appearance_rate"] == 1.0
        assert row["season_appearance_rate"] == 1.0
        assert row["season_to_date_minutes"] == 180.0
        assert row["target_total_points"] in {2, 3}
    assert "xP" not in FEATURES
    assert "selected" not in FEATURES
    assert "modified" not in FEATURES


def test_missing_historical_xg_stays_missing_not_zero():
    rows = [
        source_row(10, 1, 4, xg="", xa=""),
        source_row(10, 2, 6, xg="", xa=""),
        source_row(10, 3, 2, xg="0.0", xa="0.0"),
    ]
    panel = build_season_rows("2024-25", rows)
    gw3 = next(row for row in panel if row["gameweek"] == 3)
    assert gw3["prior3_gw_xg_avg"] is None
    assert gw3["prior3_gw_xa_avg"] is None


def test_multiseason_evaluation_uses_chronological_season_gameweek_holdout():
    rows = []
    for season_index, season in enumerate(("2023-24", "2024-25")):
        for gw in range(1, 13):
            for player in (10, 20):
                rows.append({
                    "season": season,
                    "fpl_element_id": str(player),
                    "gameweek": gw,
                    "kickoff_time": f"{2023 + season_index}-08-{gw:02d}T12:00:00+00:00",
                    "prior_gameweeks_count": gw - 1,
                    "prior_gw_points": float(gw + player / 10) if gw > 1 else None,
                    "prior_gw_minutes": 90.0 if gw > 1 else None,
                    "prior3_gw_points_avg": float(gw + player / 10),
                    "prior5_gw_points_avg": float(gw + player / 10),
                    "prior3_gw_minutes_avg": 90.0,
                    "prior5_gw_minutes_avg": 90.0,
                    "prior3_gw_xg_avg": 0.2,
                    "prior3_gw_xa_avg": 0.1,
                    "season_to_date_points_per90": 5.0,
                    "was_home": float(gw % 2),
                    "target_total_points": float((gw % 5) + player / 10),
                    "target_minutes": 90.0,
                })
    report = evaluate(rows)
    assert report["status"] == "RESEARCH_ONLY"
    assert report["point_in_time_status"] == "NOT_VERIFIED_RETROSPECTIVE_SOURCE_VINTAGES"
    assert report["validation_seasons"] == ["2024-25"]
    assert report["validation_first_gameweek"][0] == "2024-25"
    assert report["validation_last_gameweek"][0] == "2024-25"
    assert report["scored_player_gameweeks"] > 0
    assert report["per_season_validation_metrics"].keys() == {"2024-25"}
    assert "zero_minute_player_gameweek_share" in report
    assert report["positive_minute_conditional_diagnostic"]["scored_player_gameweeks_with_positive_minutes"] > 0
    assert "actual minutes are not available" in report["positive_minute_conditional_diagnostic"]["interpretation"]


def test_source_csv_reader_supports_legacy_windows_1252_names():
    payload = "name,element\nAndré,10\n".encode("cp1252")
    rows, encoding = read_csv_bytes(payload)
    assert encoding == "cp1252"
    assert rows[0]["name"] == "André"



def test_2019_20_covid_shifted_source_gameweeks_are_normalized():
    raw = {"GW": "47", "round": "47"}
    assert source_gameweek(raw, "2019-20") == 38
    assert source_gameweek({"GW": "39", "round": "39"}, "2019-20") == 30
    assert source_gameweek({"GW": "29", "round": "29"}, "2019-20") == 29


def test_covid_gameweek_normalization_does_not_apply_to_other_seasons():
    assert source_gameweek({"GW": "47", "round": "47"}, "2020-21") == 47
