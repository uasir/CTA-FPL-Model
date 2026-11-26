"""API.SH Understat client with provenance-aware, resumable local checkpoints.

All successful responses are persisted atomically before the next request. The
provider cache is shared across target vintages so overlapping player histories
are acquired once and copied into each Dastan raw-source tree.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

BASE_URL = "https://api.api.sh/understat/v1"
ACCOUNT_URL = "https://api.api.sh/v1/account"
ACCOUNT_LOGS_URL = "https://api.api.sh/v1/account/logs"
RESULTS_URL = "https://api.api.sh/v1/results"
PROVIDER = "api.sh/understat"
CACHE_SCHEMA = 1
MAPPING_COMMIT = "758db9247e8b3a9a870c991064f74d8339d61cd0"
# Histories not required by this experiment; do not let provider outages block it.
EXCLUDED_PLAYER_HISTORY_IDS = {76, 87}
# Shared across target-vintage calls within one workflow process. A new process/run
# starts closed and may retry after the provider has recovered.
RUN_CIRCUIT_BREAKER_OPEN = False


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [value for value in (payload.get("raw"), payload.get("data"), payload) if isinstance(value, dict)]


def _extract_list(payload: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for candidate in _object_candidates(payload):
        for key in keys:
            value = candidate.get(key)
            if isinstance(value, list):
                rows = [row for row in value if isinstance(row, dict)]
                if rows:
                    return rows
            if isinstance(value, dict):
                rows = [row for row in value.values() if isinstance(row, dict)]
                if rows:
                    return rows
    raise ValueError(f"API.SH response omitted expected list {keys}; top-level keys={sorted(payload)}")


def _first(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and value != "":
            return value
    return None


def normalize_player_matches(rows: list[dict[str, Any]], player_id: int) -> list[dict[str, Any]]:
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
    output = []
    for source in rows:
        row = dict(source)
        for target, names in aliases.items():
            if row.get(target) is None:
                value = _first(source, names)
                if value is not None:
                    row[target] = value
        if row.get("season") is not None:
            value = str(row["season"])
            if len(value) >= 4 and value[:4].isdigit():
                row["season"] = value[:4]
        missing = [key for key in ("season", "date", "h_team", "a_team") if row.get(key) is None]
        if missing:
            raise ValueError(f"API.SH player {player_id} row lacks {missing}")
        output.append(row)
    if not output:
        raise ValueError(f"API.SH returned no match rows for player {player_id}")
    return output


def normalize_one_team(payload: dict[str, Any], expected_team: str, season: str) -> dict[str, Any]:
    """Normalize one API.SH /team response without substituting league aggregates."""
    candidates = _object_candidates(payload)
    if isinstance(payload.get("team"), dict):
        candidates.insert(0, payload["team"])
    team_obj = next((item for item in candidates if isinstance(item.get("history"), list)), None)
    if team_obj is None:
        raise ValueError(f"API.SH /team response for {expected_team} {season} omitted match history")
    title = str(team_obj.get("title") or team_obj.get("name") or expected_team).strip()
    if title.casefold() != expected_team.casefold():
        raise ValueError(f"API.SH /team identity mismatch: requested {expected_team}, received {title}")
    normalized = []
    for source in team_obj["history"]:
        if not isinstance(source, dict):
            continue
        row = dict(source)
        aliases = {
            "date": ("date", "datetime", "match_date"), "h_a": ("h_a", "home_away", "venue"),
            "scored": ("scored", "goals_for", "goals"), "missed": ("missed", "goals_against", "conceded"),
            "xG": ("xG", "xg"), "xGA": ("xGA", "xga"), "deep": ("deep",),
            "deep_allowed": ("deep_allowed",), "ppda": ("ppda",),
            "ppda_allowed": ("ppda_allowed",), "pts": ("pts", "points"),
        }
        for target, names in aliases.items():
            if target not in row:
                value = _first(source, names)
                if value is not None:
                    row[target] = value
        if row.get("h_a") is None and source.get("is_home") is not None:
            row["h_a"] = "h" if str(source["is_home"]).lower() in {"true", "1", "yes"} else "a"
        if row.get("h_a") is not None:
            venue = str(row["h_a"]).lower()
            row["h_a"] = "h" if venue in {"home", "h"} else "a" if venue in {"away", "a"} else row["h_a"]
        required = ("date", "h_a", "scored", "missed", "xG", "xGA", "deep", "deep_allowed", "pts", "ppda", "ppda_allowed")
        missing = [field for field in required if field not in row]
        if missing:
            raise ValueError(f"API.SH team {expected_team} {season} row lacks required team metrics {missing}")
        normalized.append(row)
    if not normalized:
        raise ValueError(f"API.SH returned no match rows for team {expected_team} {season}")
    return {"title": expected_team, "history": normalized}


def normalize_team_histories(teams: dict[str, dict[str, Any]], season: str) -> dict[str, dict[str, Any]]:
    """Validate a complete 20-team season assembled from individual /team calls."""
    if len(teams) != 20:
        raise ValueError(f"API.SH team histories for {season}: got {len(teams)} teams; expected 20")
    for name, item in teams.items():
        if item.get("title") != name or not isinstance(item.get("history"), list) or not item["history"]:
            raise ValueError(f"Invalid team checkpoint for {name} {season}")
    return teams


def _remaining_credits(payload: dict[str, Any], header_value: Any = None) -> int:
    """Read the available balance from API.SH account JSON or its response header."""
    if header_value not in (None, ""):
        return int(header_value)

    # API.SH's live account endpoint exposes the current balance as
    # credits.total, alongside its free/plan/payg components.
    credit_summary = payload.get("credits")
    if isinstance(credit_summary, dict):
        total = credit_summary.get("total")
        if isinstance(total, (int, float, str)):
            try:
                parsed_total = int(total)
                if parsed_total >= 0:
                    return parsed_total
            except (TypeError, ValueError):
                pass
        bucket_values = [
            credit_summary.get(name) for name in ("free", "plan", "payg")
        ]
        if bucket_values and all(
            isinstance(value, (int, float, str)) for value in bucket_values
        ):
            try:
                parsed_buckets = [int(value) for value in bucket_values]
                if all(value >= 0 for value in parsed_buckets):
                    return sum(parsed_buckets)
            except (TypeError, ValueError):
                pass

    scalar_keys = {
        "credits_remaining", "remaining_credits", "available_credits",
        "total_credits_remaining", "credit_balance", "credits_available",
    }
    bucket_keys = {
        "free_credits", "free_monthly_credits", "monthly_free_credits",
        "plan_credits", "payg_credits", "pay_as_you_go_credits",
        "topup_credits", "top_up_credits",
    }

    def walk(value: Any):
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).lower().replace("-", "_")
                if normalized in scalar_keys and isinstance(child, (int, float, str)):
                    try:
                        yield ("total", int(child))
                    except (TypeError, ValueError):
                        pass
                elif normalized in bucket_keys and isinstance(child, (int, float, str)):
                    try:
                        yield ("bucket", int(child))
                    except (TypeError, ValueError):
                        pass
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    found = list(walk(payload))
    totals = [value for kind, value in found if kind == "total"]
    if totals:
        return max(totals)
    buckets = [value for kind, value in found if kind == "bucket"]
    if buckets:
        return sum(buckets)
    def shape(value: Any, prefix: str = "") -> list[str]:
        paths: list[str] = []
        if isinstance(value, dict):
            for key, child in value.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                paths.append(path)
                paths.extend(shape(child, path))
        elif isinstance(value, list) and value:
            paths.extend(shape(value[0], f"{prefix}[]"))
        elif prefix:
            paths.append(f"{prefix} ({type(value).__name__})")
        return paths

    # Keep diagnostics safe: report field paths and primitive types only, never
    # account values, API keys, emails, or billing identifiers.
    field_shape = shape(payload)
    raise RuntimeError(
        "API.SH account response did not expose a recognized remaining-credit field; "
        f"top_level_keys={sorted(payload)}, nested_field_paths={field_shape[:80]}. "
        "No provider data requests were made."
    )


class ApiShUnderstatClient:
    def __init__(self, api_key: str | None = None, session: Any | None = None):
        key = api_key or os.environ.get("APISH_KEY")
        if not key:
            raise RuntimeError("APISH_KEY is required as a GitHub Actions secret")
        self.session = session or requests.Session()
        self.session.headers.update({"x-api-key": key})
        self.last_meta: dict[str, Any] = {}
        self.last_payload: dict[str, Any] | None = None
        self.last_url: str | None = None
        self.last_params: dict[str, Any] = {}
        self.last_error_meta: dict[str, Any] = {}

    def _request(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_params = dict(params or {})
        response = self.session.get(url, params=request_params, timeout=120)
        status_code = getattr(response, "status_code", 200)
        if status_code >= 400:
            # Preserve provider diagnostics before raising: request IDs and Retry-After
            # are essential for distinguishing API.SH gateway failures from source-site
            # failures and for support escalation. Never persist request credentials.
            headers = getattr(response, "headers", {}) or {}
            self.last_error_meta = {
                "status_code": status_code,
                "request_id": headers.get("x-request-id"),
                "retry_after": headers.get("Retry-After"),
                "credits_used": headers.get("x-credits-used"),
                "credits_remaining": headers.get("x-credits-remaining"),
                "endpoint": urlparse(url).path,
                "params": request_params,
                "response_body_excerpt": str(getattr(response, "text", ""))[:1000],
            }
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"API.SH returned {type(payload).__name__}, expected object")
        if payload.get("success") is False:
            raise RuntimeError(f"API.SH error: {payload.get('error', 'unspecified')}")
        self.last_payload = payload
        self.last_url = url
        self.last_params = request_params
        self.last_meta = {
            "request_id": response.headers.get("x-request-id"),
            "credits_used": int(payload.get("credits_used", response.headers.get("x-credits-used", 0)) or 0),
            "credits_remaining": response.headers.get("x-credits-remaining"),
            "cached": payload.get("cached"),
            "fetched_at": payload.get("fetched_at"),
            "endpoint": urlparse(url).path,
            "params": request_params,
        }
        return payload

    def account_logs(self) -> list[dict[str, Any]]:
        """Read successful Understat calls from the free, 30-day account log."""
        records: list[dict[str, Any]] = []
        before = None
        while True:
            params = {"status": "ok", "output": "ndjson"}
            if before:
                params["before"] = before
            response = self.session.get(ACCOUNT_LOGS_URL, params=params, timeout=120)
            response.raise_for_status()
            body = response.text.strip()
            if not body:
                break
            page_records = []
            try:
                for line in body.splitlines():
                    if line.strip():
                        value = json.loads(line)
                        if isinstance(value, list):
                            page_records.extend(_log_records(value))
                        elif isinstance(value, dict):
                            nested = _log_records(value)
                            page_records.extend(nested if nested else [value])
            except json.JSONDecodeError:
                page_records = _log_records(response.json())
            records.extend(page_records)
            before = response.headers.get("x-next-cursor")
            if not before or not page_records:
                break
        return records

    def result(self, request_id: str) -> dict[str, Any]:
        return self._request(f"{RESULTS_URL}/{request_id}")

    def account(self) -> tuple[dict[str, Any], int]:
        payload = self._request(ACCOUNT_URL)
        remaining = _remaining_credits(payload, self.last_meta.get("credits_remaining"))
        self.last_meta["credits_remaining"] = remaining
        return payload, remaining

    def player_history(self, player_id: int) -> list[dict[str, Any]]:
        payload = self._request(f"{BASE_URL}/player", {
            "id": str(player_id), "include_shots": "false", "raw": "true",
        })
        rows = _extract_list(payload, ("matches", "history", "player_matches"))
        return normalize_player_matches(rows, player_id)

    def team_history(self, team: str, season: str) -> dict[str, Any]:
        payload = self._request(f"{BASE_URL}/team", {
            "team": team, "season": int(str(season).split("-")[0]), "raw": "true",
        })
        return normalize_one_team(payload, team, season)



def _log_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for candidate in (payload, payload.get("data"), payload.get("raw")):
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
        if isinstance(candidate, dict):
            for key in ("logs", "items", "requests", "results"):
                value = candidate.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
    return []

def _record_route(record: dict[str, Any]) -> str:
    value = _first(record, ("route", "endpoint", "path", "url", "request_url"))
    if value is None:
        return ""
    parsed = urlparse(str(value))
    return parsed.path if parsed.scheme else str(value).split("?", 1)[0]

def _record_params(record: dict[str, Any]) -> dict[str, Any]:
    for name in ("params", "query", "query_params", "request_params"):
        value = record.get(name)
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
                if isinstance(decoded, dict):
                    return decoded
            except json.JSONDecodeError:
                return {key: values[-1] for key, values in parse_qs(value.lstrip("?")).items()}
    for name in ("url", "request_url", "route", "endpoint", "path"):
        value = record.get(name)
        if value:
            return {key: values[-1] for key, values in parse_qs(urlparse(str(value)).query).items()}
    return {}

def _result_body(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("response", "body", "payload", "result"):
        value = payload.get(key)
        if isinstance(value, dict) and any(
            field in value for field in ("raw", "data", "matches", "history", "teams")
        ):
            return value
    return payload

def recover_remote_histories(
    client: ApiShUnderstatClient, missing_player_ids: list[int],
    missing_team_requests: list[tuple[str, str]], player_cache: Path, team_cache: Path,
) -> tuple[list[int], list[tuple[str, str]], list[str]]:
    """Recover successful player and per-team responses from API.SH's free result store."""
    records = client.account_logs()
    wanted_players = set(map(int, missing_player_ids))
    wanted_teams = set(missing_team_requests)
    matches: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        route = _record_route(record).rstrip("/")
        params = _record_params(record)
        request_id = _first(record, ("request_id", "requestId", "id"))
        if not request_id:
            continue
        if route.endswith("/understat/v1/player") or route.endswith("/player"):
            value = _first(params, ("id", "player_id"))
            if value is not None and str(value).isdigit() and int(value) in wanted_players:
                matches.setdefault(("player", str(int(value))), record)
        elif route.endswith("/understat/v1/team") or route.endswith("/team"):
            team, year = str(params.get("team", "")), str(params.get("season", ""))
            for season, requested_team in wanted_teams:
                if team.casefold() == requested_team.casefold() and year == str(int(season.split("-")[0])):
                    matches.setdefault(("team", f"{season}|{requested_team}"), record)
    recovered_players, recovered_teams, unrecoverable = [], [], []
    for (kind, key), record in sorted(matches.items()):
        request_id = str(_first(record, ("request_id", "requestId", "id")))
        try:
            response_payload = client.result(request_id)
            body = _result_body(response_payload)
            if kind == "player":
                rows = _extract_list(body, ("matches", "history", "player_matches"))
                normalized = normalize_player_matches(rows, int(key))
                destination = player_cache / f"{key}.json"
            else:
                season, team = key.split("|", 1)
                normalized = normalize_one_team(body, team, season)
                destination = team_cache / _team_cache_filename(season, team)
            client.last_payload = response_payload
            client.last_meta = {
                "request_id": request_id, "credits_used": int(record.get("credits_used") or 1),
                "credits_remaining": None, "cached": record.get("cached"),
                "fetched_at": record.get("created_at") or record.get("timestamp"),
                "endpoint": _record_route(record), "params": _record_params(record),
                "recovered_from_remote_result": True,
            }
            _persist_response(destination, normalized, kind=kind, key=key, client=client)
            if kind == "player":
                recovered_players.append(int(key))
            else:
                recovered_teams.append((season, team))
            print(f"API.SH free recovery: {kind} {key} from request {request_id}", flush=True)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 410:
                unrecoverable.append(f"{kind}:{key}:{request_id}:result_expired")
            else:
                raise
    return recovered_players, recovered_teams, unrecoverable

def _valid_meta(path: Path, *, kind: str, key: str) -> bool:
    """Validate both normalized checkpoint and the exact provider response it came from."""
    meta_path = path.with_suffix(".meta")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        payload = json.loads(path.read_text(encoding="utf-8"))
        cache_root = path.parent.parent
        raw_relative = meta.get("raw_response_path")
        if not isinstance(raw_relative, str) or not raw_relative:
            return False
        raw_path = (cache_root / raw_relative).resolve()
        if cache_root.resolve() not in raw_path.parents:
            return False
        if raw_path.is_file():
            if meta.get("raw_response_sha256") != _sha256(raw_path):
                return False
            # A response checkpoint must remain parseable JSON, not merely match a stale hash.
            json.loads(raw_path.read_text(encoding="utf-8"))
        elif cache_root.name != "understat" or not meta.get("raw_response_sha256"):
            # Shared-cache entries must retain the raw body. Dastan source-tree copies
            # intentionally carry the same sidecar but not a duplicate responses folder.
            return False
        return (
            meta.get("schema_version") == CACHE_SCHEMA
            and meta.get("provider") == PROVIDER
            and meta.get("kind") == kind
            and str(meta.get("key")) == str(key)
            and meta.get("mapping_commit") == MAPPING_COMMIT
            and meta.get("payload_sha256") == _sha256(path)
            and bool(payload)
            and (normalize_player_matches(payload, int(key)) if kind == "player" else normalize_one_team(payload, key.split("|", 1)[1], key.split("|", 1)[0]))
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _persist_response(cache_path: Path, payload: Any, *, kind: str, key: str,
                      client: ApiShUnderstatClient) -> None:
    request_id = client.last_meta.get("request_id")
    raw_response = getattr(client, "last_payload", None)
    if not request_id or raw_response is None:
        raise RuntimeError(
            "API.SH response cannot be checkpointed safely: request ID or exact response body is missing"
        )
    _atomic_json(cache_path, payload)
    response_path = cache_path.parent.parent / "responses" / f"{request_id}.json"
    _atomic_json(response_path, raw_response)
    meta = {
        "schema_version": CACHE_SCHEMA, "provider": PROVIDER, "kind": kind,
        "key": str(key), "mapping_commit": MAPPING_COMMIT,
        "payload_sha256": _sha256(cache_path),
        "raw_response_path": response_path.relative_to(cache_path.parent.parent).as_posix(),
        "raw_response_sha256": _sha256(response_path),
        "saved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **client.last_meta,
    }
    _atomic_json(cache_path.with_suffix(".meta"), meta)


def _copy_checkpoint(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    shutil.copyfile(source, temporary)
    temporary.replace(destination)


def _team_cache_filename(season: str, team: str) -> str:
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", team.casefold()).strip("-")
    return f"{season}--{slug}.json"


FPL_TO_UNDERSTAT = {
    "Man City": "Manchester City", "Man Utd": "Manchester United",
    "Newcastle": "Newcastle United", "Nott'm Forest": "Nottingham Forest",
    "Sheffield Utd": "Sheffield United", "Spurs": "Tottenham",
    "West Brom": "West Bromwich Albion", "Wolves": "Wolverhampton Wanderers",
}


def _season_team_names(raw_dir: Path, season: str) -> list[str]:
    path = raw_dir / "vaastav" / season / "teams.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Pinned Vaastav teams.csv is required to enumerate {season}: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        names = [FPL_TO_UNDERSTAT.get(row["name"], row["name"]) for row in csv.DictReader(handle)]
    names = sorted(set(name.strip() for name in names if name and name.strip()))
    if len(names) != 20:
        raise ValueError(f"Pinned Vaastav {season} teams.csv maps to {len(names)} distinct Understat teams, expected 20")
    return names


def _write_complete_team_season(team_cache: Path, raw_team_dir: Path, season: str, names: list[str]) -> bool:
    histories = {}
    for team in names:
        path = team_cache / _team_cache_filename(season, team)
        key = f"{season}|{team}"
        if not _valid_meta(path, kind="team", key=key):
            return False
        histories[team] = json.loads(path.read_text(encoding="utf-8"))
    _atomic_json(raw_team_dir / f"{season}.json", normalize_team_histories(histories, season))
    return True


def _apply_call_budget(
    player_ids: list[int], team_requests: list[tuple[str, str]], max_calls: int | None,
) -> tuple[list[int], list[tuple[str, str]]]:
    if max_calls is None:
        return list(player_ids), list(team_requests)
    if max_calls < 0:
        raise ValueError("max_calls_this_run must be non-negative")
    selected_players = list(player_ids[:max_calls])
    team_budget = max(0, max_calls - len(selected_players))
    return selected_players, list(team_requests[:team_budget])


def download_missing_histories(
    raw_dir: Path, missing_players: list[int], missing_team_seasons: list[str],
    *, cache_root: Path, probe_only: bool = False, preflight_only: bool = False,
    max_calls_this_run: int | None = None,
) -> dict[str, Any]:
    """Restore all validated checkpoints, then acquire only missing player/team records."""
    global RUN_CIRCUIT_BREAKER_OPEN
    client = ApiShUnderstatClient()
    cache_root.mkdir(parents=True, exist_ok=True)
    player_cache, team_cache = cache_root / "players", cache_root / "teams"
    player_dir, team_dir = raw_dir / "understat" / "players", raw_dir / "understat" / "teams"
    player_dir.mkdir(parents=True, exist_ok=True)
    team_dir.mkdir(parents=True, exist_ok=True)

    restored_players, restored_team_members = [], []
    excluded_player_ids = []
    missing_player_ids = []
    for player_id in sorted(set(map(int, missing_players))):
        cache = player_cache / f"{player_id}.json"
        destination = player_dir / cache.name
        if _valid_meta(cache, kind="player", key=str(player_id)):
            _copy_checkpoint(cache, destination)
            _copy_checkpoint(cache.with_suffix(".meta"), destination.with_suffix(".meta"))
            restored_players.append(player_id)
        elif _valid_meta(destination, kind="player", key=str(player_id)):
            _copy_checkpoint(destination, cache)
            restored_players.append(player_id)
        elif player_id in EXCLUDED_PLAYER_HISTORY_IDS:
            excluded_player_ids.append(player_id)
        else:
            missing_player_ids.append(player_id)

    team_names_by_season = {
        season: _season_team_names(raw_dir, season)
        for season in sorted(set(map(str, missing_team_seasons)))
    }
    missing_team_requests = []
    for season, names in team_names_by_season.items():
        for team in names:
            key = f"{season}|{team}"
            cache = team_cache / _team_cache_filename(season, team)
            destination = team_dir / cache.name
            if _valid_meta(cache, kind="team", key=key):
                _copy_checkpoint(cache, destination)
                _copy_checkpoint(cache.with_suffix(".meta"), destination.with_suffix(".meta"))
                restored_team_members.append((season, team))
            elif _valid_meta(destination, kind="team", key=key):
                _copy_checkpoint(destination, cache)
                restored_team_members.append((season, team))
            else:
                missing_team_requests.append((season, team))

    if missing_player_ids or missing_team_requests or preflight_only:
        account_payload, credits_remaining = client.account()
        recovered_players, recovered_teams, unrecoverable = recover_remote_histories(
            client, missing_player_ids, missing_team_requests, player_cache, team_cache
        )
    else:
        account_payload = {}
        credits_remaining = 0
        recovered_players, recovered_teams, unrecoverable = [], [], []

    credits_info = account_payload.get("credits", {}) if isinstance(account_payload, dict) else {}
    free_resets_at = credits_info.get("free_resets_at") if isinstance(credits_info, dict) else None

    for player_id in recovered_players:
        source = player_cache / f"{player_id}.json"
        _copy_checkpoint(source, player_dir / source.name)
        _copy_checkpoint(source.with_suffix(".meta"), (player_dir / source.name).with_suffix(".meta"))
        restored_players.append(player_id)
        missing_player_ids.remove(player_id)
    for season, team in recovered_teams:
        source = team_cache / _team_cache_filename(season, team)
        _copy_checkpoint(source, team_dir / source.name)
        _copy_checkpoint(source.with_suffix(".meta"), (team_dir / source.name).with_suffix(".meta"))
        restored_team_members.append((season, team))
        missing_team_requests.remove((season, team))
    if unrecoverable:
        raise RuntimeError("Successful API.SH requests were found but their free 30-day results have expired. Refusing to pay again: " + "; ".join(unrecoverable))

    required_calls = len(missing_player_ids) + len(missing_team_requests)
    probe_marker = cache_root / "probe_complete.json"
    probe_already_done = probe_only and probe_marker.is_file()
    player_requests = missing_player_ids[:1] if probe_only and not probe_already_done else ([] if probe_only else missing_player_ids)
    team_requests = missing_team_requests[:1] if probe_only and not probe_already_done else ([] if probe_only else missing_team_requests)
    if not probe_only:
        effective_budget = (
            min(max_calls_this_run, credits_remaining)
            if max_calls_this_run is not None else None
        )
        player_requests, team_requests = _apply_call_budget(
            player_requests, team_requests, effective_budget
        )
    # Target vintages are prepared sequentially in one process. Do not send more
    # paid requests to a provider that already returned two consecutive 503s in
    # an earlier target during this same workflow run.
    if RUN_CIRCUIT_BREAKER_OPEN and not probe_only:
        player_requests, team_requests = [], []
    planned_calls = len(player_requests) + len(team_requests)
    if preflight_only:
        unresolved_seasons = sorted({
            season for season, _team in missing_team_requests
        })
        return {
            "provider": PROVIDER, "mapping_commit": MAPPING_COMMIT,
            "probe_only": False, "preflight_only": True,
            "credits_remaining_before": credits_remaining,
            "free_credits_reset_at": free_resets_at,
            "max_calls_this_run": max_calls_this_run,
            "required_calls_before_acquisition": required_calls,
            "planned_calls_this_run": 0,
            "restored_player_histories": restored_players,
            "excluded_player_history_ids": excluded_player_ids,
            "restored_team_members": [{"season": s, "team": t} for s, t in restored_team_members],
            "restored_team_seasons": sorted({s for s, _ in restored_team_members}),
            "remote_recovered_player_histories": recovered_players,
            "remote_recovered_team_members": [{"season": s, "team": t} for s, t in recovered_teams],
            "fetched_player_histories": [],
            "fetched_team_members": [],
            "fetched_team_seasons": [],
            "probe_errors": [], "acquisition_errors": [],
            "provider_unavailable_circuit_breaker_open": RUN_CIRCUIT_BREAKER_OPEN,
            "unresolved_player_ids": missing_player_ids,
            "unresolved_team_seasons": unresolved_seasons,
            "unresolved_team_requests": [
                {"season": season, "team": team}
                for season, team in missing_team_requests
            ],
            "unresolved_team_member_count": len(missing_team_requests),
            "acquisition_started": False,
        }
    print(
        f"API.SH pre-acquisition check: {credits_remaining} credits remaining; "
        f"{required_calls} calls outstanding overall; {planned_calls} planned this run; "
        f"free credits reset at {free_resets_at or 'not reported'}.",
        flush=True,
    )
    if planned_calls > credits_remaining:
        raise RuntimeError(
            f"API.SH credits insufficient: {credits_remaining} remaining, {planned_calls} calls planned "
            f"({required_calls} outstanding overall). No provider data requests were made."
        )

    fetched_players, fetched_team_members, probe_errors = [], [], []
    acquisition_errors: list[str] = []
    provider_failure_diagnostics: list[dict[str, Any]] = []
    consecutive_503_failures = 0
    provider_unavailable = RUN_CIRCUIT_BREAKER_OPEN and not probe_only

    def record_acquisition_failure(label: str, exc: Exception) -> None:
        global RUN_CIRCUIT_BREAKER_OPEN
        nonlocal consecutive_503_failures, provider_unavailable
        status = getattr(getattr(exc, "response", None), "status_code", None)
        diagnostic = dict(getattr(client, "last_error_meta", {}) or {})
        if diagnostic:
            diagnostic["label"] = label
            provider_failure_diagnostics.append(diagnostic)
        message = f"{label}: {type(exc).__name__}: {exc}"
        if probe_only:
            probe_errors.append(message)
            print(f"API.SH probe request failed (no automatic retry): {message}; diagnostics={diagnostic}", flush=True)
            return
        if status == 503:
            acquisition_errors.append(message)
            consecutive_503_failures += 1
            print(
                f"API.SH temporary 503 for {label}; preserving checkpoints and continuing "
                f"to one independent request ({consecutive_503_failures}/2 consecutive 503s).",
                flush=True,
            )
            if consecutive_503_failures >= 2:
                provider_unavailable = True
                RUN_CIRCUIT_BREAKER_OPEN = True
                print(
                    "API.SH circuit breaker opened after two consecutive 503 responses; "
                    "remaining histories stay unresolved for a later resumed run.",
                    flush=True,
                )
            return
        raise exc

    for player_id in player_requests:
        if provider_unavailable:
            break
        try:
            payload = client.player_history(player_id)
            cache = player_cache / f"{player_id}.json"
            _persist_response(cache, payload, kind="player", key=str(player_id), client=client)
            _copy_checkpoint(cache, player_dir / cache.name)
            _copy_checkpoint(cache.with_suffix(".meta"), (player_dir / cache.name).with_suffix(".meta"))
            fetched_players.append(player_id)
            consecutive_503_failures = 0
            print(f"API.SH checkpointed player {player_id}", flush=True)
        except Exception as exc:
            record_acquisition_failure(f"player {player_id}", exc)

    for season, team in team_requests:
        if provider_unavailable:
            break
        try:
            payload = client.team_history(team, season)
            key = f"{season}|{team}"
            cache = team_cache / _team_cache_filename(season, team)
            _persist_response(cache, payload, kind="team", key=key, client=client)
            _copy_checkpoint(cache, team_dir / cache.name)
            _copy_checkpoint(cache.with_suffix(".meta"), (team_dir / cache.name).with_suffix(".meta"))
            fetched_team_members.append((season, team))
            consecutive_503_failures = 0
            print(f"API.SH checkpointed team {team} {season}", flush=True)
        except Exception as exc:
            record_acquisition_failure(f"team {team} {season}", exc)

    if probe_only and not probe_already_done and (not missing_player_ids or fetched_players) and (not missing_team_requests or fetched_team_members):
        _atomic_json(probe_marker, {
            "provider": PROVIDER, "mapping_commit": MAPPING_COMMIT,
            "completed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sample_player_ids": fetched_players,
            "sample_team_requests": [{"season": s, "team": t} for s, t in fetched_team_members],
        })

    complete_team_seasons, unresolved_team_seasons = [], []
    for season, names in team_names_by_season.items():
        if _write_complete_team_season(team_cache, team_dir, season, names):
            complete_team_seasons.append(season)
        else:
            unresolved_team_seasons.append(season)

    unresolved_players = [p for p in missing_player_ids if p not in fetched_players]
    return {
        "provider": PROVIDER, "mapping_commit": MAPPING_COMMIT,
        "probe_only": probe_only, "credits_remaining_before": credits_remaining,
        "free_credits_reset_at": free_resets_at,
        "max_calls_this_run": max_calls_this_run,
        "required_calls_before_acquisition": required_calls, "planned_calls_this_run": planned_calls,
        "restored_player_histories": restored_players,
        "excluded_player_history_ids": excluded_player_ids,
        "restored_team_members": [{"season": s, "team": t} for s, t in restored_team_members],
        "restored_team_seasons": sorted({s for s, _ in restored_team_members}),
        "remote_recovered_player_histories": recovered_players,
        "remote_recovered_team_members": [{"season": s, "team": t} for s, t in recovered_teams],
        "fetched_player_histories": fetched_players,
        "fetched_team_members": [{"season": s, "team": t} for s, t in fetched_team_members],
        "fetched_team_seasons": complete_team_seasons,
        "probe_errors": probe_errors,
        "acquisition_errors": acquisition_errors,
        "provider_failure_diagnostics": provider_failure_diagnostics,
        "provider_unavailable_circuit_breaker_open": provider_unavailable,
        "unresolved_player_ids": unresolved_players,
        "unresolved_team_seasons": unresolved_team_seasons,
        "unresolved_team_requests": [
            {"season": season, "team": team}
            for season, names in team_names_by_season.items() for team in names
            if not _valid_meta(
                team_cache / _team_cache_filename(season, team),
                kind="team", key=f"{season}|{team}",
            )
        ],
        "unresolved_team_member_count": sum(
            1 for season, names in team_names_by_season.items() for team in names
            if not _valid_meta(team_cache / _team_cache_filename(season, team), kind="team", key=f"{season}|{team}")
        ),
    }
