import pandas as pd
import pytest

from rebuild_2pm_dastan_286_candidate import corrected_assignments


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
