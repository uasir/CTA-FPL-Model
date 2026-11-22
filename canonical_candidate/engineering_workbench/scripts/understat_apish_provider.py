"""API.SH-backed Understat history importer.

The upstream Understat site now returns an HTML error page to the automated
client. This adapter uses API.SH's documented JSON endpoints instead of trying
to bypass the site's crawler restrictions.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://api.api.sh/understat/v1"


def _object_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for value in (payload.get("raw"), payload.get("data"), payload):
        if isinstance(value, dict):
            candidates.append(value)
    return candidates


def _extract_list(payload: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for candidate in _object_candidates(payload):
        for key in keys:
            value = candidate.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
            if isinstance(value, dict):
                return [row for row in value.values() if isinstance(row, dict)]
    raise ValueError(
        f"API.SH response omitted expected list {keys}; top-level keys={sorted(payload)}"
    )


def _first(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and value != "":
            return value
    return None


def normalize_player_matches(rows: list[dict[str, Any]], player_id: int) -> list[dict[str, Any]]:
    """Return Understat-compatible player match rows with stable required keys."""
    output = []
    for source in rows:
        row = dict(source)
        aliases = {
            "season": ("season", "season_start_year", "start_year"),
            "date": ("date", "datetime", "match_date"),
            "h_team": ("h_team", "home_team", "home_team_title", "h_team_title"),
            "a_team": ("a_team", "away_team", "away_team_title", "a_team_title"),
            "time": ("time", "minutes", "mins"),
            "goals": ("goals", "player_goals"),
            "assists": ("assists", "player_assists"),
            "shots": ("shots", "total_shots"),
            "key_passes": ("key_passes", "keyPasses"),
            "xG": ("xG", "xg"),
            "xA": ("xA", "xa"),
            "npg": ("npg", "non_penalty_goals"),
            "npxG": ("npxG", "non_penalty_xg"),
            "xGChain": ("xGChain", "xg_chain"),
            "xGBuildup": ("xGBuildup", "xg_buildup"),
        }
        for target, names in aliases.items():
            if row.get(target) is None:
                value = _first(source, names)
                if value is not None:
                    row[target] = value
        missing = [name for name in ("season", "date", "h_team", "a_team") if row.get(name) is None]
        if missing:
            raise ValueError(
                f"API.SH player {player_id} match row lacks identity fields {missing}; "
                f"available={sorted(source)}"
            )
        output.append(row)
    if not output:
        raise ValueError(f"API.SH returned no player match rows for Understat ID {player_id}")
    return output


def normalize_team_history(rows: list[dict[str, Any]], team_name: str, season: str) -> list[dict[str, Any]]:
    """Return team match history in the shape consumed by Dastan's live loader."""
    output = []
    for source in rows:
        row = dict(source)
        aliases = {
            "date": ("date", "datetime", "match_date"),
            "h_a": ("h_a", "home_away", "venue"),
            "scored": ("scored", "goals_for", "goals"),
            "missed": ("missed", "goals_against", "conceded"),
            "xG": ("xG", "xg"),
            "xGA": ("xGA", "xga"),
            "deep": ("deep",),
            "deep_allowed": ("deep_allowed",),
            "ppda": ("ppda",),
            "ppda_allowed": ("ppda_allowed",),
            "pts": ("pts", "points"),
        }
        for target, names in aliases.items():
            if row.get(target) is None:
                value = _first(source, names)
                if value is not None:
                    row[target] = value
        if row.get("date") is None:
            raise ValueError(
                f"API.SH team {team_name} {season} row lacks date; available={sorted(source)}"
            )
        output.append(row)
    if not output:
        raise ValueError(f"API.SH returned no team history for {team_name} {season}")
    return output


class ApiShUnderstatClient:
    """Small, bounded client for the documented API.SH Understat endpoints."""

    def __init__(self, api_key: str | None = None, session: Any | None = None):
        key = api_key or os.environ.get("APISH_KEY")
        if not key:
            raise RuntimeError(
                "APISH_KEY is required. Create an API.SH key and add it as a "
                "GitHub Actions repository secret named APISH_KEY."
            )
        self.session = session or requests.Session()
        self.session.headers.update({"x-api-key": key})

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        last_error = None
        for attempt in range(3):
            try:
                response = self.session.get(
                    f"{BASE_URL}/{endpoint.lstrip('/')}",
                    params=params,
                    timeout=120,
                )
                if response.status_code in (429, 503):
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2 ** attempt
                    time.sleep(min(max(delay, 1.0), 30.0))
                    last_error = RuntimeError(
                        f"API.SH {endpoint} returned HTTP {response.status_code}"
                    )
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError(f"API.SH {endpoint} returned {type(payload).__name__}")
                if payload.get("success") is False:
                    raise RuntimeError(
                        f"API.SH {endpoint} error: {payload.get('error', 'unspecified')}"
                    )
                return payload
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"API.SH {endpoint} failed after three attempts: {last_error}")

    def player_history(self, player_id: int) -> tuple[list[dict[str, Any]], int]:
        payload = self._get(
            "player",
            {
                "id": str(player_id),
                "include_shots": "false",
                "fresh": "true",
                "raw": "true",
            },
        )
        rows = _extract_list(payload, ("matches", "history", "player_matches"))
        return normalize_player_matches(rows, player_id), int(payload.get("credits_used", 1))

    def team_history(self, team_name: str, season: str) -> tuple[list[dict[str, Any]], int]:
        payload = self._get(
            "team",
            {
                "team": team_name,
                "season": int(str(season).split("-")[0]),
                "fresh": "true",
                "raw": "true",
            },
        )
        rows = _extract_list(payload, ("history", "matches", "team_matches"))
        return normalize_team_history(rows, team_name, season), int(payload.get("credits_used", 1))


def load_monthly_usage(path: Path, budget: int) -> dict[str, Any]:
    month = time.strftime("%Y-%m", time.gmtime())
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("month") == month:
                used = int(payload.get("calls_reserved", 0))
                return {"month": month, "calls_reserved": used, "budget": budget}
        except Exception:
            pass
    return {"month": month, "calls_reserved": 0, "budget": budget}


def reserve_monthly_calls(path: Path, calls: int, budget: int) -> dict[str, Any]:
    """Reserve provider credits before dispatch to avoid unexpected paid overage."""
    usage = load_monthly_usage(path, budget)
    total = usage["calls_reserved"] + int(calls)
    if total > budget:
        raise RuntimeError(
            f"API.SH local credit guard would exceed {budget} calls this month "
            f"({usage['calls_reserved']} already reserved + {calls} requested). "
            "Raise APISH_MONTHLY_CREDIT_BUDGET only after reviewing billing."
        )
    usage["calls_reserved"] = total
    usage["last_reserved_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(usage, indent=2) + "\n", encoding="utf-8")
    return usage
