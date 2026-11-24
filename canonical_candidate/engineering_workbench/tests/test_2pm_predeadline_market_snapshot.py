from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from build_2pm_predeadline_market_snapshot import (
    extract_market,
    filter_snapshot_safety_buffer,
)
from rebuild_2pm_dastan_286_candidate import (
    audit_market_value_parity,
    validate_reconstruction_coverage,
)


def accepted_fplcache():
    deadline = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
    return SimpleNamespace(
        _accepted_event=lambda payload, gameweek, target_deadline: (
            any(
                int(event["id"]) == gameweek
                and event.get("is_next")
                and datetime.fromisoformat(event["deadline_time"].replace("Z", "+00:00")) == target_deadline
                for event in payload.get("events", [])
            )
        )
    ), deadline


def test_market_snapshot_extracts_price_ownership_and_transfer_balance():
    fplcache, deadline = accepted_fplcache()
    captured = deadline - timedelta(hours=4)
    payload = {
        "events": [{"id": 20, "is_next": True, "deadline_time": deadline.isoformat()}],
        "elements": [
            {
                "code": 123,
                "now_cost": 55,
                "selected_by_percent": "7.3",
                "transfers_in_event": 100,
                "transfers_out_event": 40,
            }
        ],
    }
    rows = extract_market(
        payload,
        season="2025-26",
        gameweek=20,
        deadline=deadline,
        captured_at=captured,
        source_path="cache/2026/01/10/0800.json.xz",
        fplcache_module=fplcache,
    )
    assert len(rows) == 1
    assert rows[0]["value"] == 55.0
    assert rows[0]["selected"] == 7.3
    assert rows[0]["transfers_balance"] == 60.0
    assert rows[0]["snapshot_at"] == captured


def test_market_snapshot_rejects_post_deadline_capture():
    fplcache, deadline = accepted_fplcache()
    payload = {
        "events": [{"id": 20, "is_next": True, "deadline_time": deadline.isoformat()}],
        "elements": [{"code": 123, "now_cost": 55, "selected_by_percent": "7.3",
                      "transfers_in_event": 100, "transfers_out_event": 40}],
    }
    with pytest.raises(RuntimeError, match="Post-deadline"):
        extract_market(
            payload,
            season="2025-26",
            gameweek=20,
            deadline=deadline,
            captured_at=deadline,
            source_path="post-deadline.json.xz",
            fplcache_module=fplcache,
        )


def test_market_snapshot_rejects_wrong_gameweek_or_deadline():
    fplcache, deadline = accepted_fplcache()
    payload = {
        "events": [{"id": 20, "is_next": False, "deadline_time": deadline.isoformat()}],
        "elements": [{"code": 123, "now_cost": 55, "selected_by_percent": "7.3",
                      "transfers_in_event": 100, "transfers_out_event": 40}],
    }
    rows = extract_market(
        payload,
        season="2025-26",
        gameweek=20,
        deadline=deadline,
        captured_at=deadline - timedelta(hours=2),
        source_path="wrong-gw.json.xz",
        fplcache_module=fplcache,
    )
    assert rows == []



def test_five_minute_safety_buffer_drops_borderline_snapshots():
    frame = pd.DataFrame(
        [
            {"fpl_code": 1, "age_hours": 4 / 60},
            {"fpl_code": 2, "age_hours": 5 / 60},
            {"fpl_code": 3, "age_hours": 6 / 60},
        ]
    )
    safe, removed = filter_snapshot_safety_buffer(frame, safety_buffer_minutes=5)
    assert removed == 1
    assert safe["fpl_code"].tolist() == [2, 3]


def test_five_minute_safety_buffer_rejects_missing_capture_age():
    frame = pd.DataFrame(
        [
            {"fpl_code": 1, "age_hours": None},
            {"fpl_code": 2, "age_hours": 7 / 60},
        ]
    )
    safe, removed = filter_snapshot_safety_buffer(frame, safety_buffer_minutes=5)
    assert removed == 1
    assert safe["fpl_code"].tolist() == [2]



def test_market_value_parity_audit_detects_native_price_unit_mismatch(tmp_path):
    market_path = tmp_path / "market.parquet"
    pd.DataFrame(
        [{
            "season": "2025-26", "gameweek": 20, "fpl_code": 123,
            "value": 55.0, "selected": 7.3, "transfers_balance": 60.0,
        }]
    ).to_parquet(market_path, index=False)
    source = pd.DataFrame(
        [{
            "season": "2025-26", "gameweek": 20, "fpl_code": 123,
            "value": 55.0, "selected": 7.3, "transfers_balance": 60.0,
        }]
    )
    report = audit_market_value_parity(source, market_path)
    assert report["fields"]["value"]["exact_match_rate"] == 1.0

    source.loc[0, "value"] = 5.5
    report = audit_market_value_parity(source, market_path)
    assert report["fields"]["value"]["exact_match_rate"] == 0.0
    assert report["fields"]["value"]["mean_absolute_difference"] == 49.5



def test_286_feature_family_coverage_requires_every_reconstruction_path():
    features = (
        [f"player_feature_{i}" for i in range(115)]
        + [f"team_feature_{i}" for i in range(60)]
        + [f"opp_feature_{i}" for i in range(60)]
        + ["opp_status_league_rank"]
        + [f"p_any_{i}" for i in range(3)]
        + [f"p60_{i}" for i in range(3)]
        + [f"e_minutes_{i}" for i in range(3)]
        + [f"ar_feature_{i}" for i in range(32)]
        + ["ar_ep_next", "is_home_num", "status_league_rank", "value", "selected", "transfers_balance"]
        + ["sig_status_risk", "sig_chance_playing", "sig_has_news"]
    )
    player_report = {
        "player_rolling_feature_count": 115,
        "availability_feature_count": 9,
        "defensive_player_history_feature_count": 26,
    }
    team_report = {
        "team_feature_count": 60,
        "opponent_feature_count": 60,
        "direct_rank_columns": ["status_league_rank", "opp_status_league_rank"],
    }
    fixture_report = {"fixture_context_columns": [f"context_{i}" for i in range(6)]}
    report = validate_reconstruction_coverage(
        features,
        player_report,
        team_report,
        fixture_report,
        pd.DataFrame(columns=features),
    )
    assert len(features) == 286
    assert report["reconstruction_path_total"] == 286
    team_report["team_feature_count"] = 59
    with pytest.raises(RuntimeError, match="cover 285/286"):
        validate_reconstruction_coverage(
            features,
            player_report,
            team_report,
            fixture_report,
            pd.DataFrame(columns=features),
        )
