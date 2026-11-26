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

    # Capture the HTTP response behind understatapi's JSONDecodeError. The
    # library otherwise discards status/body details, making 403/429/5xx and
    # provider-side HTML challenges indistinguishable.
    import requests

    last_http: dict = {}
    request_count = 0
    access_stop = False
    original_request = requests.sessions.Session.request

    class StopAfterProviderResponse(RuntimeError):
        """Stop the diagnostic after a provider-side denial or server failure."""

    def observed_request(session, method, url, *args, **kwargs):
        nonlocal request_count, access_stop
        request_count += 1
        if request_count > 2:
            raise StopAfterProviderResponse("Diagnostic hard limit: two HTTP requests")
        response = original_request(session, method, url, *args, **kwargs)
        last_http.clear()
        last_http.update({
            "method": method,
            "url": response.url,
            "status_code": response.status_code,
            "reason": response.reason,
            "content_type": response.headers.get("content-type"),
            "server": response.headers.get("server"),
            "cf_ray": response.headers.get("cf-ray"),
            "retry_after": response.headers.get("retry-after"),
            "body_preview": response.text[:500],
        })
        if response.status_code in {401, 403, 407, 429} or response.status_code >= 500:
            access_stop = True
            raise StopAfterProviderResponse(
                f"Stopping after HTTP {response.status_code}; no further endpoint requests will be made"
            )
        return response

    requests.sessions.Session.request = observed_request
    failures = 0
    try:
        with UnderstatClient() as client:
            for player_id in args.player_id:
                if access_stop or request_count >= 2:
                    break
                item = {"kind": "player", "id": player_id}
                last_http.clear()
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
                        "status": "access_or_transport_stop" if access_stop else "error",
                        "exception_type": type(exc).__name__,
                        "exception": str(exc)[:1200],
                        "traceback": traceback.format_exc(limit=4),
                    })
                if last_http:
                    item["http"] = dict(last_http)
                report["probes"].append(item)
                print(json.dumps(item, ensure_ascii=False), flush=True)

            if not access_stop and request_count < 2:
                import time
                time.sleep(2)
            for season in args.team_season:
                if access_stop or request_count >= 2:
                    break
                item = {"kind": "teams", "season": season, "league": "EPL"}
                last_http.clear()
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
                        "status": "access_or_transport_stop" if access_stop else "error",
                        "exception_type": type(exc).__name__,
                        "exception": str(exc)[:1200],
                        "traceback": traceback.format_exc(limit=4),
                    })
                if last_http:
                    item["http"] = dict(last_http)
                report["probes"].append(item)
                print(json.dumps(item, ensure_ascii=False), flush=True)
    finally:
        requests.sessions.Session.request = original_request
    report["http_request_count"] = request_count
    report["stopped_after_provider_response"] = access_stop
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
