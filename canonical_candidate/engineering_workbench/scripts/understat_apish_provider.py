"""API.SH Understat client with provenance-aware, resumable local checkpoints.

All successful responses are persisted atomically before the next request. The
provider cache is shared across target vintages so overlapping player histories
are acquired once and copied into each Dastan raw-source tree.
"""
from __future__ import annotations

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


def normalize_team_histories(payload: dict[str, Any], season: str) -> dict[str, dict[str, Any]]:
    teams_payload = None
    for candidate in _object_candidates(payload):
        value = candidate.get("teams")
        if isinstance(value, dict):
            teams_payload = list(value.values())
            break
        if isinstance(value, list):
            teams_payload = value
            break
    if teams_payload is None:
        raise ValueError(f"API.SH league response omitted raw team histories for {season}")
    result: dict[str, dict[str, Any]] = {}
    for team in teams_payload:
        if not isinstance(team, dict):
            continue
        title = str(team.get("title") or team.get("name") or "").strip()
        history = team.get("history")
        if not title or not isinstance(history, list) or not history:
            continue
        normalized = []
        for source in history:
            if not isinstance(source, dict):
                continue
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
            if row.get("h_a") is None and source.get("is_home") is not None:
                row["h_a"] = "h" if str(source["is_home"]).lower() in {"true", "1", "yes"} else "a"
            if row.get("h_a") is not None:
                venue = str(row["h_a"]).lower()
                row["h_a"] = "h" if venue in {"home", "h"} else "a" if venue in {"away", "a"} else row["h_a"]
            required_fields = (
                "date", "h_a", "scored", "missed", "xG", "xGA",
                "deep", "deep_allowed", "ppda", "ppda_allowed", "pts",
            )
            missing = [field for field in required_fields if row.get(field) is None]
            if missing:
                raise ValueError(
                    f"API.SH team {title} {season} row lacks required team metrics {missing}"
                )
            normalized.append(row)
        if normalized:
            result[title] = {"title": title, "history": normalized}
    if len(result) != 20:
        raise ValueError(f"API.SH league {season} returned {len(result)} usable teams; expected exactly 20")
    return result


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

    def _request(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_params = dict(params or {})
        response = self.session.get(url, params=request_params, timeout=120)
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
            params = {"status": "ok", "route": "/understat/v1/", "output": "ndjson"}
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
                        if isinstance(value, dict):
                            page_records.append(value)
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
        remaining = self.last_meta.get("credits_remaining")
        if remaining is None:
            raise RuntimeError("API.SH account response omitted x-credits-remaining; refusing bulk acquisition")
        return payload, int(remaining)

    def player_history(self, player_id: int) -> list[dict[str, Any]]:
        payload = self._request(f"{BASE_URL}/player", {
            "id": str(player_id), "include_shots": "false", "raw": "true",
        })
        rows = _extract_list(payload, ("matches", "history", "player_matches"))
        return normalize_player_matches(rows, player_id)

    def team_histories(self, season: str) -> dict[str, dict[str, Any]]:
        payload = self._request(f"{BASE_URL}/league", {
            "league": "EPL", "season": int(str(season).split("-")[0]), "raw": "true",
        })
        return normalize_team_histories(payload, season)



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
    for name in ("url", "request_url"):
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
    missing_seasons: list[str], player_cache: Path, team_cache: Path,
) -> tuple[list[int], list[str], list[str]]:
    """Recover successful remote responses for free before credit-consuming calls."""
    records = client.account_logs()
    wanted_players = set(map(int, missing_player_ids))
    wanted_seasons = {str(v): int(str(v).split("-")[0]) for v in missing_seasons}
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
                matches[("player", str(int(value)))] = record
        elif route.endswith("/understat/v1/league") or route.endswith("/league"):
            if str(params.get("league", "")).upper() == "EPL":
                year = str(params.get("season", ""))
                for season, season_year in wanted_seasons.items():
                    if year == str(season_year):
                        matches[("team", season)] = record
    recovered_players: list[int] = []
    recovered_seasons: list[str] = []
    unrecoverable: list[str] = []
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
                normalized = normalize_team_histories(body, key)
                destination = team_cache / f"{key}.json"
            client.last_payload = body
            client.last_meta = {
                "request_id": request_id,
                "credits_used": int(record.get("credits_used") or 1),
                "credits_remaining": None,
                "cached": record.get("cached"),
                "fetched_at": record.get("created_at") or record.get("timestamp"),
                "endpoint": _record_route(record),
                "params": _record_params(record),
                "recovered_from_remote_result": True,
            }
            _persist_response(destination, normalized, kind=kind, key=key, client=client)
            if kind == "player":
                recovered_players.append(int(key))
            else:
                recovered_seasons.append(key)
            print(f"API.SH free recovery: {kind} {key} from request {request_id}", flush=True)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 410:
                unrecoverable.append(f"{kind}:{key}:{request_id}:result_expired")
            else:
                raise
    return recovered_players, recovered_seasons, unrecoverable

def _valid_meta(path: Path, *, kind: str, key: str) -> bool:
    meta_path = path.with_suffix(".meta")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        payload = json.loads(path.read_text(encoding="utf-8"))
        return (
            meta.get("schema_version") == CACHE_SCHEMA
            and meta.get("provider") == PROVIDER
            and meta.get("kind") == kind
            and str(meta.get("key")) == str(key)
            and meta.get("mapping_commit") == MAPPING_COMMIT
            and meta.get("payload_sha256") == _sha256(path)
            and bool(payload)
            and (normalize_player_matches(payload, int(key)) if kind == "player" else normalize_team_histories({"raw": {"teams": payload}}, key))
        )
    except (OSError, ValueError, TypeError):
        return False


def _persist_response(cache_path: Path, payload: Any, *, kind: str, key: str,
                      client: ApiShUnderstatClient) -> None:
    _atomic_json(cache_path, payload)
    request_id = client.last_meta.get("request_id")
    raw_response = getattr(client, "last_payload", None)
    if request_id and raw_response is not None:
        response_path = cache_path.parent.parent / "responses" / f"{request_id}.json"
        _atomic_json(response_path, raw_response)
    meta = {
        "schema_version": CACHE_SCHEMA, "provider": PROVIDER, "kind": kind,
        "key": str(key), "mapping_commit": MAPPING_COMMIT,
        "payload_sha256": _sha256(cache_path), "saved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **client.last_meta,
    }
    _atomic_json(cache_path.with_suffix(".meta"), meta)


def _copy_checkpoint(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    shutil.copyfile(source, temporary)
    temporary.replace(destination)


def download_missing_histories(
    raw_dir: Path, missing_players: list[int], missing_team_seasons: list[str],
    *, cache_root: Path, probe_only: bool = False,
) -> dict[str, Any]:
    """Restore shared checkpoints first; acquire only missing records, saving each immediately."""
    client = ApiShUnderstatClient()
    cache_root.mkdir(parents=True, exist_ok=True)
    player_cache = cache_root / "players"
    team_cache = cache_root / "teams"
    player_dir = raw_dir / "understat" / "players"
    team_dir = raw_dir / "understat" / "teams"
    restored_players, restored_teams = [], []

    missing_player_ids = []
    for player_id in sorted(set(map(int, missing_players))):
        cache = player_cache / f"{player_id}.json"
        destination = player_dir / f"{player_id}.json"
        if _valid_meta(cache, kind="player", key=str(player_id)):
            _copy_checkpoint(cache, destination)
            restored_players.append(player_id)
        elif destination.is_file() and destination.stat().st_size and not cache.exists():
            # Raw-run-local files from an earlier API.SH run are reused only when
            # their matching provenance sidecar validates.
            if _valid_meta(destination, kind="player", key=str(player_id)):
                _copy_checkpoint(destination, cache)
                restored_players.append(player_id)
            else:
                missing_player_ids.append(player_id)
        else:
            missing_player_ids.append(player_id)

    missing_seasons = []
    for season in sorted(set(map(str, missing_team_seasons))):
        cache = team_cache / f"{season}.json"
        destination = team_dir / f"{season}.json"
        if _valid_meta(cache, kind="team", key=season):
            _copy_checkpoint(cache, destination)
            restored_teams.append(season)
        elif destination.is_file() and destination.stat().st_size and not cache.exists():
            if _valid_meta(destination, kind="team", key=season):
                _copy_checkpoint(destination, cache)
                restored_teams.append(season)
            else:
                missing_seasons.append(season)
        else:
            missing_seasons.append(season)

    account, credits_remaining = client.account()
    recovered_players, recovered_seasons, unrecoverable = recover_remote_histories(
        client, missing_player_ids, missing_seasons, player_cache, team_cache
    )
    for player_id in recovered_players:
        _copy_checkpoint(player_cache / f"{player_id}.json", player_dir / f"{player_id}.json")
        _copy_checkpoint(player_cache / f"{player_id}.meta", player_dir / f"{player_id}.meta")
        restored_players.append(player_id)
        missing_player_ids.remove(player_id)
    for season in recovered_seasons:
        _copy_checkpoint(team_cache / f"{season}.json", team_dir / f"{season}.json")
        _copy_checkpoint(team_cache / f"{season}.meta", team_dir / f"{season}.meta")
        restored_teams.append(season)
        missing_seasons.remove(season)
    if unrecoverable:
        raise RuntimeError(
            "Successful API.SH requests were found but their free 30-day results have expired. "
            "Refusing to pay for them again without review: " + "; ".join(unrecoverable)
        )
    required_calls = len(missing_player_ids) + len(missing_seasons)
    if not probe_only and required_calls > credits_remaining:
        raise RuntimeError(
            f"API.SH credits insufficient: {credits_remaining} remaining, "
            f"{required_calls} missing-history calls required. No bulk requests made."
        )

    fetched_players, fetched_teams = [], []
    probe_marker = cache_root / "probe_complete.json"
    probe_already_done = probe_only and probe_marker.is_file()
    player_requests = (
        missing_player_ids[:1] if probe_only and not probe_already_done
        else [] if probe_only else missing_player_ids
    )
    team_requests = (
        missing_seasons[:1] if probe_only and not probe_already_done
        else [] if probe_only else missing_seasons
    )
    probe_calls = len(player_requests) + len(team_requests)
    if probe_calls > credits_remaining:
        raise RuntimeError(
            f"API.SH probe requires {probe_calls} credits but only {credits_remaining} remain; "
            "no provider data requests were made."
        )
    for player_id in player_requests:
        payload = client.player_history(player_id)
        cache = player_cache / f"{player_id}.json"
        _persist_response(cache, payload, kind="player", key=str(player_id), client=client)
        _copy_checkpoint(cache, player_dir / cache.name)
        _copy_checkpoint(cache.with_suffix(".meta"), (player_dir / cache.name).with_suffix(".meta"))
        fetched_players.append(player_id)
        print(f"API.SH checkpointed player {player_id}", flush=True)
    for season in team_requests:
        payload = client.team_histories(season)
        cache = team_cache / f"{season}.json"
        _persist_response(cache, payload, kind="team", key=season, client=client)
        _copy_checkpoint(cache, team_dir / cache.name)
        _copy_checkpoint(cache.with_suffix(".meta"), (team_dir / cache.name).with_suffix(".meta"))
        fetched_teams.append(season)
        print(f"API.SH checkpointed team season {season}", flush=True)

    # One shared marker makes the probe a one-time, bounded action across both
    # target vintages and future push-triggered audit runs. Bulk mode ignores it.
    if probe_only and not probe_already_done and (fetched_players or fetched_teams):
        _atomic_json(probe_marker, {
            "provider": PROVIDER, "mapping_commit": MAPPING_COMMIT,
            "completed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sample_player_ids": fetched_players, "sample_team_seasons": fetched_teams,
        })

    # Probe mode deliberately stops after one player and one team season. The
    # next bulk run restores these checkpoints and continues the remaining acquisition.
    remaining_players = [p for p in missing_player_ids if p not in fetched_players]
    remaining_teams = [s for s in missing_seasons if s not in fetched_teams]
    if not probe_only:
        for player_id in remaining_players:
            payload = client.player_history(player_id)
            cache = player_cache / f"{player_id}.json"
            _persist_response(cache, payload, kind="player", key=str(player_id), client=client)
            _copy_checkpoint(cache, player_dir / cache.name)
            _copy_checkpoint(cache.with_suffix(".meta"), (player_dir / cache.name).with_suffix(".meta"))
            fetched_players.append(player_id)
            print(f"API.SH checkpointed player {player_id}", flush=True)
        for season in remaining_teams:
            payload = client.team_histories(season)
            cache = team_cache / f"{season}.json"
            _persist_response(cache, payload, kind="team", key=season, client=client)
            _copy_checkpoint(cache, team_dir / cache.name)
            _copy_checkpoint(cache.with_suffix(".meta"), (team_dir / cache.name).with_suffix(".meta"))
            fetched_teams.append(season)
            print(f"API.SH checkpointed team season {season}", flush=True)

    unresolved_players = [p for p in missing_player_ids if p not in fetched_players]
    unresolved_teams = [s for s in missing_seasons if s not in fetched_teams]
    return {
        "provider": PROVIDER, "mapping_commit": MAPPING_COMMIT,
        "probe_only": probe_only, "credits_remaining_before": credits_remaining,
        "required_calls_before_acquisition": required_calls,
        "restored_player_histories": restored_players,
        "restored_team_seasons": restored_teams,
        "remote_recovered_player_histories": recovered_players,
        "remote_recovered_team_seasons": recovered_seasons,
        "fetched_player_histories": fetched_players,
        "fetched_team_seasons": fetched_teams,
        "unresolved_player_ids": unresolved_players,
        "unresolved_team_seasons": unresolved_teams,
    }
