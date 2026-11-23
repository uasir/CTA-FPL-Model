"""Rebuild pre-deadline price, ownership and transfer-balance inputs from fplcache.

These replace the unvintaged `value`, `selected` and `transfers_balance`
fields carried by retrospective Vaastav Gameweek rows. All values are captured
from the latest accepted snapshot strictly before the official deadline.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd

KEY = ["season", "gameweek", "fpl_code"]
MARKET_FIELDS = ["value", "selected", "transfers_balance"]


def extract_market(
    payload: dict,
    *,
    season: str,
    gameweek: int,
    deadline,
    captured_at,
    source_path: str,
    fplcache_module=None,
) -> list[dict[str, Any]]:
    if fplcache_module is None:
        raise ValueError("fplcache_module is required for official snapshot acceptance")
    if not fplcache_module._accepted_event(payload, gameweek, deadline):
        return []
    if captured_at >= deadline:
        raise RuntimeError("Post-deadline market snapshot selected")

    rows = []
    for player in payload.get("elements", []):
        raw_price = player.get("now_cost")
        raw_selected = player.get("selected_by_percent")
        raw_in = player.get("transfers_in_event")
        raw_out = player.get("transfers_out_event")
        value = -1.0 if raw_price in (None, "") else float(raw_price) / 10.0
        selected = (
            -1.0 if raw_selected in (None, "")
            else float(str(raw_selected).replace(",", ""))
        )
        transfers_balance = (
            -1.0
            if raw_in in (None, "") or raw_out in (None, "")
            else float(raw_in) - float(raw_out)
        )
        rows.append(
            {
                "season": season,
                "gameweek": int(gameweek),
                "fpl_code": int(player["code"]),
                "value": value,
                "selected": selected,
                "transfers_balance": transfers_balance,
                "snapshot_at": captured_at,
                "deadline_time": deadline,
                "age_hours": (deadline - captured_at).total_seconds() / 3600,
                "source": "Randdalf/fplcache",
                "snapshot_path": source_path,
            }
        )
    return rows


def build_market_artifact(
    raw_dir: Path,
    output_dir: Path,
    seasons: list[str],
    fplcache_module,
) -> tuple[Path, dict[str, Any]]:
    frame, season_report = fplcache_module._build_one(
        raw_dir,
        seasons,
        extractor=lambda payload, **kwargs: extract_market(
            payload, fplcache_module=fplcache_module, **kwargs
        ),
        max_age_hours=30.0,
        refresh_index=False,
    )
    if frame.duplicated(KEY).any():
        raise ValueError("Pre-deadline market artifact has duplicate player/Gameweek keys")
    if frame["snapshot_at"].ge(frame["deadline_time"]).any():
        raise ValueError("Pre-deadline market artifact contains post-deadline snapshots")
    for column in MARKET_FIELDS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if not frame[MARKET_FIELDS].notna().all().all():
        raise ValueError("Market artifact contains non-numeric or missing values after sentinel handling")

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "pre_deadline_market.parquet"
    frame.to_parquet(path, index=False)
    report = {
        "status": "PRE_DEADLINE_MARKET_SNAPSHOT_BUILT",
        "admission_status": "PROVENANCE_CHECKED_SNAPSHOT_INPUT",
        "rows": int(len(frame)),
        "season_coverage": {
            str(season): {
                "rows": int(len(rows)),
                "players": int(rows["fpl_code"].nunique()),
                "median_snapshot_age_hours": float(rows["age_hours"].median()),
                "max_snapshot_age_hours": float(rows["age_hours"].max()),
            }
            for season, rows in frame.groupby("season", sort=True)
        },
        "source": "Randdalf/fplcache",
        "acceptance": "target is_next + matching official deadline + snapshot strictly before deadline",
        "fields": {
            "value": "now_cost / 10 (FPL price in millions)",
            "selected": "selected_by_percent",
            "transfers_balance": "transfers_in_event - transfers_out_event",
        },
        "season_resolution": season_report,
        "artifact": str(path),
    }
    (output_dir / "pre_deadline_market.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return path, report
