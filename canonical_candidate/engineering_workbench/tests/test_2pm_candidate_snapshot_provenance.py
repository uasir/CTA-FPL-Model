import pandas as pd

from sanitize_2pm_candidate_snapshot_provenance import sanitize_candidate_frame


def test_invalid_or_missing_snapshots_are_sentinelized_against_official_deadline():
    frame = pd.DataFrame(
        {
            "deadline_time": [
                "2025-08-15T17:30:00Z",
                "2025-08-15T17:30:00Z",
                "2025-08-15T17:30:00Z",
            ],
            "ep_next_snapshot_at": [
                "2025-08-15T17:24:00Z",  # safe: six minutes before deadline
                "2025-08-15T17:27:00Z",  # unsafe: three minutes before deadline
                None,                    # no provenance
            ],
            "signals_snapshot_at": [
                "2025-08-15T17:24:00Z",
                "2025-08-15T17:31:00Z",  # after deadline
                None,
            ],
            "market_snapshot_at": [
                "2025-08-15T17:24:00Z",
                "2025-08-15T17:27:00Z",
                None,
            ],
            "ar_ep_next": [2.4, 3.1, 4.2],
            "sig_status_risk": [0.0, 1.0, 2.0],
            "sig_chance_playing": [100.0, 75.0, 50.0],
            "sig_has_news": [0.0, 1.0, 1.0],
            "value": [55.0, 56.0, 57.0],
            "selected": [1000.0, 2000.0, 3000.0],
            "transfers_balance": [10.0, 20.0, 30.0],
        }
    )

    clean, report = sanitize_candidate_frame(frame)

    assert clean.loc[0, "ar_ep_next"] == 2.4
    assert clean.loc[1, "ar_ep_next"] == -1.0
    assert clean.loc[2, "ar_ep_next"] == -1.0
    assert pd.isna(clean.loc[1, "ep_next_snapshot_at"])
    assert pd.isna(clean.loc[2, "ep_next_snapshot_at"])

    assert clean.loc[1, "sig_status_risk"] == -1.0
    assert clean.loc[1, "sig_chance_playing"] == -1.0
    assert clean.loc[1, "sig_has_news"] == -1.0
    assert clean.loc[1, "value"] == -1.0
    assert clean.loc[1, "selected"] == -1.0
    assert clean.loc[1, "transfers_balance"] == -1.0

    assert report["groups"]["ep_next_snapshot_at"]["rows_invalidated"] == 2
    assert report["groups"]["signals_snapshot_at"]["rows_invalidated"] == 2
    assert report["groups"]["market_snapshot_at"]["rows_invalidated"] == 2


def test_snapshot_exactly_five_minutes_before_deadline_is_retained():
    frame = pd.DataFrame(
        {
            "deadline_time": ["2025-08-15T17:30:00Z"],
            "ep_next_snapshot_at": ["2025-08-15T17:25:00Z"],
            "signals_snapshot_at": ["2025-08-15T17:25:00Z"],
            "market_snapshot_at": ["2025-08-15T17:25:00Z"],
            "ar_ep_next": [2.4],
            "sig_status_risk": [0.0],
            "sig_chance_playing": [100.0],
            "sig_has_news": [0.0],
            "value": [55.0],
            "selected": [1000.0],
            "transfers_balance": [10.0],
        }
    )

    clean, report = sanitize_candidate_frame(frame)

    assert clean.loc[0, "ar_ep_next"] == 2.4
    assert report["groups"]["ep_next_snapshot_at"]["rows_invalidated"] == 0
