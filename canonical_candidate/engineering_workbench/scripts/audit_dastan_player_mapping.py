#!/usr/bin/env python3
"""Audit a season-scoped FPL-to-Understat mapping without fuzzy identity joins.

Unmapped FPL players are retained in the output roster with a null Understat ID.
Shared Understat IDs are reported explicitly and never silently treated as one-to-one.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def audit_mapping(roster: list[dict[str, str]], mapping: list[dict[str, str]], release_id: str = "") -> dict:
    if not roster:
        raise ValueError("FPL roster is empty")
    if not mapping:
        raise ValueError("Understat mapping is empty")

    for label, rows in (("roster", roster), ("mapping", mapping)):
        if any(not row.get("fpl_code", "").strip() for row in rows):
            raise ValueError(f"{label} contains a blank fpl_code")
        codes = [row["fpl_code"].strip() for row in rows]
        if len(codes) != len(set(codes)):
            raise ValueError(f"{label} contains duplicate fpl_code values")

    by_code = {row["fpl_code"].strip(): row for row in mapping}
    mapped_id_to_codes: dict[str, list[str]] = defaultdict(list)
    output_rows = []
    unmapped = []
    for player in roster:
        code = player["fpl_code"].strip()
        source = by_code.get(code, {})
        raw_id = (source.get("understat_id") or source.get("understat_player_id") or "").strip()
        status = (source.get("mapping_status") or "").strip().lower()
        confidence = (source.get("confidence") or source.get("confidence_level") or "").strip()
        understat_id = raw_id if raw_id and status not in {"unmapped", "none", "rejected"} else ""
        if understat_id:
            mapped_id_to_codes[understat_id].append(code)
        else:
            unmapped.append(code)
        output_rows.append({
            "season": (player.get("season") or "").strip(),
            "fpl_code": code,
            "fpl_element_id": (player.get("element") or player.get("fpl_element_id") or "").strip(),
            "player_name": (player.get("player_name") or player.get("web_name") or "").strip(),
            "position": (player.get("position") or "").strip(),
            "team_name": (player.get("team_name") or "").strip(),
            "understat_id": understat_id,
            "mapping_status": "mapped" if understat_id else "unmapped",
            "source_mapping_status": status,
            "confidence": confidence,
            "mapping_release_id": release_id,
        })

    shared = {
        understat_id: sorted(codes)
        for understat_id, codes in mapped_id_to_codes.items()
        if len(codes) > 1
    }
    mapped_count = len(roster) - len(unmapped)
    return {
        "schema_version": 1,
        "status": "PASS_WITH_UNMAPPED" if unmapped or shared else "PASS",
        "mapping_release_id": release_id,
        "roster_players": len(roster),
        "mapped_players": mapped_count,
        "unmapped_players": len(unmapped),
        "mapped_coverage_pct": round(100.0 * mapped_count / len(roster), 3),
        "shared_understat_id_count": len(shared),
        "shared_understat_ids": shared,
        "unmapped_fpl_codes": sorted(unmapped),
        "mapping_codes_not_in_roster": sorted(set(by_code) - {r["fpl_code"].strip() for r in roster}),
        "rows": output_rows,
        "join_policy": "exact fpl_code only; no display-name or fuzzy matching",
        "understat_join_ready": not shared and not unmapped,\n        "understat_partial_join_usable": bool(mapped_count) and not shared,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--release-id", default="")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    report = audit_mapping(read_rows(args.roster), read_rows(args.mapping), args.release_id)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {key: value for key, value in report.items() if key not in {"rows", "shared_understat_ids", "unmapped_fpl_codes", "mapping_codes_not_in_roster"}}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
