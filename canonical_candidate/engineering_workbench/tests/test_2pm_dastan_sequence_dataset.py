from pathlib import Path
import json

import pandas as pd
import pytest

from build_2pm_dastan_sequence_dataset import (
    build_sequences,
    load_schema,
    validate_input,
)

ROOT = Path(__file__).resolve().parents[1]
FEATURES, _ = load_schema(ROOT / "config" / "2pm_dastan_286_schema.json")


def make_row(fixture, kickoff, *, minutes=0, completed=None, gameweek=1, value=0.0):
    kickoff = pd.to_datetime(kickoff, utc=True)
    deadline = kickoff - pd.Timedelta(hours=3)
    completed_at = (
        pd.to_datetime(completed, utc=True) if completed is not None else pd.NaT
    )
    row = {
        "season": "2026-27",
        "gameweek": gameweek,
        "fixture": fixture,
        "fpl_code": 12345,
        "kickoff_time": kickoff.isoformat(),
        "match_completed_at": (
            completed_at.isoformat() if pd.notna(completed_at) else None
        ),
        "deadline_time": deadline.isoformat(),
        "source_as_of_time": (deadline - pd.Timedelta(minutes=10)).isoformat(),
        "minutes": minutes,
        "total_points": 2.0 if minutes > 0 else None,
    }
    row.update({feature: value for feature in FEATURES})
    row[FEATURES[0]] = value
    return row


def five_history_rows():
    rows = []
    for i in range(5):
        kickoff = pd.Timestamp("2026-08-01T12:00:00Z") + pd.Timedelta(days=2 * i)
        rows.append(
            make_row(
                f"H{i}",
                kickoff.isoformat(),
                minutes=90,
                completed=(kickoff + pd.Timedelta(hours=2)).isoformat(),
                value=float(i + 1),
            )
        )
    return rows


def test_schema_is_exactly_286_unique_ordered_columns():
    assert len(FEATURES) == 286
    assert len(set(FEATURES)) == 286
    assert FEATURES[0] == "player_assists_1"
    assert FEATURES[-1] == "sig_has_news"


def test_builds_five_played_fixture_tokens_plus_target_query_and_keeps_label_separate():
    rows = five_history_rows()
    dgw_early = pd.Timestamp("2026-08-12T12:00:00Z")
    dgw_late = pd.Timestamp("2026-08-12T18:00:00Z")
    # This earlier DGW match finishes after the common deadline and must not
    # enter the late fixture's history.
    rows.append(
        make_row(
            "DGW-EARLY",
            dgw_early.isoformat(),
            minutes=90,
            completed=(dgw_early + pd.Timedelta(hours=2)).isoformat(),
            gameweek=6,
            value=99.0,
        )
    )
    rows.append(
        make_row("DGW-LATE", dgw_late.isoformat(), gameweek=6, value=77.0)
    )
    frame = validate_input(pd.DataFrame(rows), FEATURES, "fixture")
    sequences, report = build_sequences(frame, FEATURES, require_label=False)

    assert len(sequences) == 2
    late = sequences.loc[sequences["fixture_id"].eq("DGW-LATE")].iloc[0]
    assert json.loads(late["history_fixture_ids"]) == ["H0", "H1", "H2", "H3", "H4"]
    assert late[f"token_00__{FEATURES[0]}"] == 1.0
    assert late[f"token_04__{FEATURES[0]}"] == 5.0
    assert late[f"token_05__{FEATURES[0]}"] == 77.0
    assert late["target_points"] is None or pd.isna(late["target_points"])
    assert report["counts"]["emitted"] == 2


def test_insufficient_history_is_not_padded_or_silently_used():
    rows = five_history_rows()[:4]
    kickoff = pd.Timestamp("2026-08-12T12:00:00Z")
    rows.append(make_row("TARGET", kickoff.isoformat()))
    frame = validate_input(pd.DataFrame(rows), FEATURES, "fixture")
    sequences, report = build_sequences(frame, FEATURES)
    assert sequences.empty
    assert report["counts"]["insufficient_previous_played_matches"] == 5


def test_gap_over_21_days_is_rejected():
    rows = []
    for i in range(5):
        kickoff = pd.to_datetime(\n            ["2026-07-01T12:00:00Z", "2026-07-08T12:00:00Z",\n             "2026-07-30T12:00:00Z", "2026-07-31T12:00:00Z",\n             "2026-08-01T12:00:00Z"][i], utc=True\n        )
        rows.append(
            make_row(
                f"H{i}",
                kickoff.isoformat(),
                minutes=90,
                completed=(kickoff + pd.Timedelta(hours=2)).isoformat(),
                value=float(i),
            )
        )
    target_kickoff = pd.Timestamp("2026-08-02T12:00:00Z")
    rows.append(make_row("TARGET", target_kickoff.isoformat()))
    frame = validate_input(pd.DataFrame(rows), FEATURES, "fixture")
    sequences, report = build_sequences(frame, FEATURES)
    assert sequences.empty
    assert report["counts"]["gap_over_21_days"] == 1


def test_non_finite_feature_values_fail_closed():
    rows = five_history_rows()
    rows[-1][FEATURES[0]] = float("nan")
    with pytest.raises(ValueError, match="NaN/inf"):
        validate_input(pd.DataFrame(rows), FEATURES, "fixture")


def test_post_deadline_snapshot_fails_closed():
    rows = five_history_rows()
    rows[-1]["source_as_of_time"] = rows[-1]["deadline_time"]
    with pytest.raises(ValueError, match="at/after its deadline"):
        validate_input(pd.DataFrame(rows), FEATURES, "fixture")
