import pandas as pd
import pytest

from types import SimpleNamespace

from rebuild_2pm_dastan_286_candidate import (
    attach_match_availability_bounds,
    corrected_assignments,
)


def test_corrected_identity_assignments_preserve_historical_gameweek_intervals():
    training = pd.DataFrame(
        [
            {"season": "2024-25", "fpl_code": 437688, "understat_id": 9082,
             "first_gameweek": 1, "last_gameweek": 38, "mapped_rows": 22},
            {"season": "2024-25", "fpl_code": 515501, "understat_id": 5191,
             "first_gameweek": 1, "last_gameweek": 12, "mapped_rows": 8},
        ]
    )
    corrected = pd.DataFrame(
        [
            {"fpl_code": 437688, "understat_id": 9216},
            {"fpl_code": 515501, "understat_id": 10576},
        ]
    )
    result = corrected_assignments(
        training, corrected, ["2024-25"], ["2024-25", "2025-26"]
    )
    assert result["understat_id"].tolist() == [9216, 10576]
    assert result["first_gameweek"].tolist() == [1, 1]
    assert result["last_gameweek"].tolist() == [38, 12]
    assert result["mapped_rows"].tolist() == [22, 8]


def test_corrected_identity_assignments_fail_on_missing_mapping_without_name_fallback():
    training = pd.DataFrame(
        [{"season": "2024-25", "fpl_code": 123, "understat_id": 456,
          "first_gameweek": 1, "last_gameweek": 38, "mapped_rows": 20}]
    )
    corrected = pd.DataFrame(columns=["fpl_code", "understat_id"])
    with pytest.raises(ValueError, match="missing frozen assignment"):
        corrected_assignments(
            training, corrected, ["2024-25"], ["2024-25"]
        )


def test_corrected_identity_function_refuses_active_seasons():
    training = pd.DataFrame(
        columns=["season", "fpl_code", "understat_id", "first_gameweek",
                 "last_gameweek", "mapped_rows"]
    )
    corrected = pd.DataFrame(columns=["fpl_code", "understat_id"])
    with pytest.raises(ValueError, match="Active-season assignments"):
        corrected_assignments(
            training, corrected, ["2026-27"], ["2020-21", "2025-26"]
        )



def test_fixture_availability_uses_conservative_upper_bound_and_finished_flag(tmp_path):
    season_dir = tmp_path / "vaastav" / "2025-26"
    season_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"id": 11, "kickoff_time": "2026-01-01T12:00:00Z", "finished": True},
            {"id": 12, "kickoff_time": "2026-01-03T12:00:00Z", "finished": False},
        ]
    ).to_csv(season_dir / "fixtures.csv", index=False)
    source = SimpleNamespace(VAASTAV_RAW="https://example.invalid/")
    frame = pd.DataFrame(
        [
            {"season": "2025-26", "fixture": 11},
            {"season": "2025-26", "fixture": 12},
        ]
    )
    result = attach_match_availability_bounds(
        frame, tmp_path, source, ["2025-26"]
    )
    assert result.loc[0, "match_available_at"] == pd.Timestamp("2026-01-02T12:00:00Z")
    assert pd.isna(result.loc[1, "match_available_at"])
    assert result["completion_time_quality"].tolist() == [
        "CONSERVATIVE_24H_UPPER_BOUND",
        "NOT_FINISHED",
    ]


def test_fixture_availability_rejects_missing_fixture_metadata(tmp_path):
    season_dir = tmp_path / "vaastav" / "2025-26"
    season_dir.mkdir(parents=True)
    pd.DataFrame(
        [{"id": 11, "kickoff_time": "2026-01-01T12:00:00Z", "finished": True}]
    ).to_csv(season_dir / "fixtures.csv", index=False)
    source = SimpleNamespace(VAASTAV_RAW="https://example.invalid/")
    frame = pd.DataFrame([{"season": "2025-26", "fixture": 999}])
    with pytest.raises(ValueError, match="lack fixture completion metadata"):
        attach_match_availability_bounds(
            frame, tmp_path, source, ["2025-26"]
        )
