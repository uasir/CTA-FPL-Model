"""Small, non-label diagnostic for the Understat fallback API.

This deliberately probes a few known pinned IDs before any expensive candidate
reconstruction. It records exception classes/messages so systemic API failures are
not misreported as hundreds of individually missing player histories.
"""
from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--player-id", action="append", type=str, default=[])
    parser.add_argument("--team-season", action="append", type=str, default=[])
    args = parser.parse_args()

    report = {
        "status": "UNDERSTAT_ACCESS_DIAGNOSTIC",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": "Understat via understatapi",
        "probes": [],
    }
    try:
        from understatapi import UnderstatClient
    except Exception as exc:
        report["import_error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return 2

    failures = 0
    with UnderstatClient() as client:
        for player_id in args.player_id:
            item = {"kind": "player", "id": player_id}
            try:
                payload = client.player(player=player_id).get_match_data()
                item.update({
                    "status": "ok" if payload is not None else "empty",
                    "record_count": len(payload) if payload is not None else 0,
                    "payload_type": type(payload).__name__,
                })
                if payload is None:
                    failures += 1
            except Exception as exc:
                failures += 1
                item.update({
                    "status": "error",
                    "exception_type": type(exc).__name__,
                    "exception": str(exc)[:1200],
                    "traceback": traceback.format_exc(limit=4),
                })
            report["probes"].append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)

        for season in args.team_season:
            item = {"kind": "teams", "season": season, "league": "EPL"}
            try:
                payload = client.league(league="EPL").get_team_data(season=season)
                item.update({
                    "status": "ok" if payload else "empty",
                    "record_count": len(payload) if payload else 0,
                    "payload_type": type(payload).__name__,
                })
                if not payload:
                    failures += 1
            except Exception as exc:
                failures += 1
                item.update({
                    "status": "error",
                    "exception_type": type(exc).__name__,
                    "exception": str(exc)[:1200],
                    "traceback": traceback.format_exc(limit=4),
                })
            report["probes"].append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)

    report["failed_probe_count"] = failures
    report["successful_probe_count"] = len(report["probes"]) - failures
    report["decision"] = (
        "PROCEED_TO_CANDIDATE_BUILD" if failures == 0
        else "STOP_BEFORE_EXPENSIVE_BUILD"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
