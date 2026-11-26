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

import requests

BASE_URL = "https://api.api.sh/understat/v1"
ACCOUNT_URL = "https://api.api.sh/v1/account"
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
            if row.get("date") is None:
                raise ValueError(f"API.SH team {title} {season} row lacks date")
            normalized.append(row)
        if normalized:
            result[title] = {"title": title, "history": normalized}
    if len(result) < 20:
        raise ValueError(f"API.SH league {season} returned only {len(result)} usable teams; expected 20")
    return result


class ApiShUnderstatClient:
    def __init__(self, api_key: str | None = None, session: Any | None = None):
        key = api_key or os.environ.get("APISH_KEY")
        if not key:
            raise RuntimeError("APISH_KEY is required as a GitHub Actions secret")
        self.session = session or requests.Session()
        self.session.headers.update({"x-api-key": key})
        self.last_meta: dict[str, Any] = {}

    def _request(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.get(url, params=params or {}, timeout=120)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"API.SH returned {type(payload).__name__}, expected object")
        if payload.get("success") is False:
            raise RuntimeError(f"API.SH error: {payload.get('error', 'unspecified')}")
        self.last_meta = {
            "request_id": response.headers.get("x-request-id"),
            "credits_used": int(payload.get("credits_used", response.headers.get("x-credits-used", 0)) or 0),
            "credits_remaining": response.headers.get("x-credits-remaining"),
            "cached": payload.get("cached"),
            "fetched_at": payload.get("fetched_at"),
        }
        return payload

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


def _valid_meta(path: Path, *, kind: str, key: str) -> bool:
    meta_path = path.with_suffix(path.suffix + ".meta.json")
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
        )
    except (OSError, ValueError, TypeError):
        return False


def _persist_response(cache_path: Path, payload: Any, *, kind: str, key: str,
                      client: ApiShUnderstatClient) -> None:
    _atomic_json(cache_path, payload)
    meta = {
        "schema_version": CACHE_SCHEMA, "provider": PROVIDER, "kind": kind,
        "key": str(key), "mapping_commit": MAPPING_COMMIT,
        "payload_sha256": _sha256(cache_path), "saved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **client.last_meta,
    }
    _atomic_json(cache_path.with_suffix(cache_path.suffix + ".meta.json"), meta)


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
    required_calls = len(missing_player_ids) + len(missing_seasons)
    if not probe_only and required_calls > credits_remaining:
        raise RuntimeError(
            f"API.SH credits insufficient: {credits_remaining} remaining, "
            f"{required_calls} missing-history calls required. No bulk requests made."
        )

    fetched_players, fetched_teams = [], []
    player_requests = missing_player_ids[:1] if probe_only else missing_player_ids
    team_requests = missing_seasons[:1] if probe_only else missing_seasons
    for player_id in player_requests:
        payload = client.player_history(player_id)
        cache = player_cache / f"{player_id}.json"
        _persist_response(cache, payload, kind="player", key=str(player_id), client=client)
        _copy_checkpoint(cache, player_dir / cache.name)
        _copy_checkpoint(cache.with_suffix(".json.meta.json"), (player_dir / cache.name).with_suffix(".json.meta.json"))
        fetched_players.append(player_id)
        print(f"API.SH checkpointed player {player_id}", flush=True)
    for season in team_requests:
        payload = client.team_histories(season)
        cache = team_cache / f"{season}.json"
        _persist_response(cache, payload, kind="team", key=season, client=client)
        _copy_checkpoint(cache, team_dir / cache.name)
        _copy_checkpoint(cache.with_suffix(".json.meta.json"), (team_dir / cache.name).with_suffix(".json.meta.json"))
        fetched_teams.append(season)
        print(f"API.SH checkpointed team season {season}", flush=True)

    # Probe mode deliberately stops after one player and one team season. The
    # next run restores these checkpoints and only then continues the acquisition.
    remaining_players = [p for p in missing_player_ids if p not in fetched_players]
    remaining_teams = [s for s in missing_seasons if s not in fetched_teams]
    if not probe_only:
        for player_id in remaining_players:
            payload = client.player_history(player_id)
            cache = player_cache / f"{player_id}.json"
            _persist_response(cache, payload, kind="player", key=str(player_id), client=client)
            _copy_checkpoint(cache, player_dir / cache.name)
            _copy_checkpoint(cache.with_suffix(".json.meta.json"), (player_dir / cache.name).with_suffix(".json.meta.json"))
            fetched_players.append(player_id)
            print(f"API.SH checkpointed player {player_id}", flush=True)
        for season in remaining_teams:
            payload = client.team_histories(season)
            cache = team_cache / f"{season}.json"
            _persist_response(cache, payload, kind="team", key=season, client=client)
            _copy_checkpoint(cache, team_dir / cache.name)
            _copy_checkpoint(cache.with_suffix(".json.meta.json"), (team_dir / cache.name).with_suffix(".json.meta.json"))
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
        "fetched_player_histories": fetched_players,
        "fetched_team_seasons": fetched_teams,
        "unresolved_player_ids": unresolved_players,
        "unresolved_team_seasons": unresolved_teams,
    }
