from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pandas as pd
import pytest

from build_2pm_predeadline_market_snapshot import (
    extract_market,
    filter_snapshot_safety_buffer,
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
