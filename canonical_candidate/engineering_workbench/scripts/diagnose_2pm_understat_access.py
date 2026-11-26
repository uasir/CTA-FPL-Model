"""Small, non-label diagnostic for direct Understat AJAX access.

The probe is intentionally capped at two logical HTTP requests. It records
response metadata and readable HTML error-page text so HTTP 200 responses that
are not JSON are not mistaken for successful API access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import traceback
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


class VisibleTextParser(HTMLParser):
    """Extract a compact, human-readable diagnostic from an HTML response."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.parts.append(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--player-id", action="append", type=str, default=[])
    parser.add_argument("--team-season", action="append", type=str, default=[])
    args = parser.parse_args()

    report = {
        "status": "UNDERSTAT_ACCESS_DIAGNOSTIC",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": "Understat direct AJAX via understatapi",
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
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2

    import requests

    last_http: dict = {}
    request_count = 0
    stop_after_unusable_response = False
    original_request = requests.sessions.Session.request

    class StopDiagnostic(RuntimeError):
        """Stop after an unusable response or the strict request cap."""

    def observed_request(session, method, url, *request_args, **kwargs):
        nonlocal request_count, stop_after_unusable_response
        request_count += 1
        if request_count > 2:
            raise StopDiagnostic("Diagnostic hard limit: two HTTP requests")

        response = original_request(session, method, url, *request_args, **kwargs)
        body = response.text
        content_type = (response.headers.get("content-type") or "").lower()
        visible = VisibleTextParser()
        is_html = "html" in content_type or body.lstrip().lower().startswith(
            ("<!doctype html", "<html")
        )
        if is_html:
            visible.feed(body)

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
            "body_length": len(body),
            "body_sha256": hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest(),
            "body_preview": body[:2000],
            "html_visible_text": " ".join(visible.parts)[:1200] if is_html else None,
            "response_classification": (
                "HTML_ERROR_OR_INTERSTITIAL_PAGE"
                if is_html else
                "JSON_CONTENT_TYPE"
                if "json" in content_type else
                "NON_JSON_OR_UNTYPED_RESPONSE"
            ),
        })

        if response.status_code in {401, 403, 407, 429} or response.status_code >= 500:
            stop_after_unusable_response = True
            raise StopDiagnostic(
                f"Stopping after HTTP {response.status_code}; no further endpoint requests"
            )
        if is_html or ("json" not in content_type and content_type):
            stop_after_unusable_response = True
            raise StopDiagnostic(
                "Stopping after non-JSON response; no further endpoint requests"
            )
        return response

    requests.sessions.Session.request = observed_request
    failures = 0
    try:
        with UnderstatClient() as client:
            for player_id in args.player_id:
                if stop_after_unusable_response or request_count >= 2:
                    break
                item = {"kind": "player", "id": player_id}
                last_http.clear()
                try:
                    payload = client.player(player=player_id).get_match_data()
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
                        "status": "unusable_response" if stop_after_unusable_response else "error",
                        "exception_type": type(exc).__name__,
                        "exception": str(exc)[:1200],
                        "traceback": traceback.format_exc(limit=4),
                    })
                if last_http:
                    item["http"] = dict(last_http)
                report["probes"].append(item)
                print(json.dumps(item, ensure_ascii=False), flush=True)

            if not stop_after_unusable_response and request_count < 2:
                import time
                time.sleep(2)
            for season in args.team_season:
                if stop_after_unusable_response or request_count >= 2:
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
                        "status": "unusable_response" if stop_after_unusable_response else "error",
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
    report["stopped_after_unusable_response"] = stop_after_unusable_response
    # Retain the previous key for downstream summary compatibility.
    report["stopped_after_provider_response"] = stop_after_unusable_response
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
