"""Audit defensive raw-source coverage without loading target-score labels.

Only identity, Gameweek, minutes and the four defensive source columns are read.
The script intentionally never loads total_points or any other realised score.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

FIELDS = (
    "defensive_contribution",
    "clearances_blocks_interceptions",
    "recoveries",
    "tackles",
)
USECOLS = ["element", "GW", "minutes", *FIELDS]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_frame(frame: pd.DataFrame) -> dict[str, Any]:
    required = {"element", "GW", "minutes"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Source lacks required audit columns: {missing}")
    out = frame.copy()
    out["GW"] = pd.to_numeric(out["GW"], errors="coerce")
    out["minutes"] = pd.to_numeric(out["minutes"], errors="coerce")
    if out["GW"].isna().any():
        raise ValueError("GW contains null or non-numeric values")
    out["GW"] = out["GW"].astype(int)
    played = out["minutes"].gt(0)
    result: dict[str, Any] = {
        "source_rows": int(len(out)),
        "played_player_fixture_rows": int(played.sum()),
        "gameweeks": {},
        "fields": {},
    }
    for field in FIELDS:
        present = field in out.columns
        if not present:
            result["fields"][field] = {
                "source_column_present": False,
                "finite_values": 0,
                "missing_values": int(played.sum()),
                "observed_zero_values": 0,
                "observed_nonzero_values": 0,
            }
            continue
        values = pd.to_numeric(out.loc[played, field], errors="coerce")
        finite = values.notna() & values.map(lambda x: pd.notna(x) and abs(float(x)) != float("inf"))
        observed = values[finite]
        result["fields"][field] = {
            "source_column_present": True,
            "finite_values": int(finite.sum()),
            "missing_values": int((~finite).sum()),
            "observed_zero_values": int(observed.eq(0).sum()),
            "observed_nonzero_values": int(observed.ne(0).sum()),
        }
    for gw, rows in out.groupby("GW", sort=True):
        played_rows = rows[rows["minutes"].gt(0)]
        result["gameweeks"][str(int(gw))] = {
            "source_rows": int(len(rows)),
            "played_player_fixture_rows": int(len(played_rows)),
            "fields": {},
        }
        for field in FIELDS:
            if field not in rows.columns:
                result["gameweeks"][str(int(gw))]["fields"][field] = {
                    "source_column_present": False,
                    "finite": 0,
                    "missing": int(len(played_rows)),
                    "zero": 0,
                    "nonzero": 0,
                }
                continue
            values = pd.to_numeric(played_rows[field], errors="coerce")
            finite = values.notna() & values.map(lambda x: pd.notna(x) and abs(float(x)) != float("inf"))
            observed = values[finite]
            result["gameweeks"][str(int(gw))]["fields"][field] = {
                "source_column_present": True,
                "finite": int(finite.sum()),
                "missing": int((~finite).sum()),
                "zero": int(observed.eq(0).sum()),
                "nonzero": int(observed.ne(0).sum()),
            }
    return result


def audit_file(
    path: Path, *, season: str, repository: str, commit: str, commit_date: str
) -> dict[str, Any]:
    header = pd.read_csv(path, nrows=0).columns.tolist()
    selected = [column for column in USECOLS if column in header]
    frame = pd.read_csv(path, usecols=selected, low_memory=False)
    report = audit_frame(frame)
    return {
        "season": season,
        "repository": repository,
        "commit": commit,
        "commit_date": commit_date,
        "relative_source_path": f"data/{season}/gws/merged_gw.csv",
        "source_file_bytes": path.stat().st_size,
        "source_file_sha256": sha256(path),
        "source_header": header,
        "audit": report,
        "label_isolation": {
            "total_points_loaded": False,
            "target_score_columns_loaded": False,
            "purpose": "defensive_source_coverage_only",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-2025-26", type=Path, required=True)
    parser.add_argument("--source-2026-27", type=Path, required=True)
    parser.add_argument("--commit-2025-26", required=True)
    parser.add_argument("--commit-date-2025-26", required=True)
    parser.add_argument("--commit-2026-27", required=True)
    parser.add_argument("--commit-date-2026-27", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "selected_columns_only_no_target_points_read",
        "sources": {
            "2025-26": audit_file(
                args.source_2025_26,
                season="2025-26",
                repository="vaastav/Fantasy-Premier-League",
                commit=args.commit_2025_26,
                commit_date=args.commit_date_2025_26,
            ),
            "2026-27": audit_file(
                args.source_2026_27,
                season="2026-27",
                repository="vaastav/Fantasy-Premier-League",
                commit=args.commit_2026_27,
                commit_date=args.commit_date_2026_27,
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
