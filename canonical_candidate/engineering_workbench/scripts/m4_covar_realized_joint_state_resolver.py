"""Resolve an official realized player-Gameweek vector against a declared joint
state catalogue using exact outcomes only. No interpolation or marginal inference.
"""
from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


class RealizedJointStateResolverError(ValueError):
    """The realized outcome or declared joint-state catalogue is invalid."""


RESOLVER_NAME = "m4-covar-exact-realized-state-resolver"
RESOLVER_VERSION = "1.0.0"


def canonical_json_sha256(value: Any) -> str:
    """Hash canonical UTF-8 JSON for stable catalogue/universe evidence."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise RealizedJointStateResolverError(f"{field} must be a finite numeric value")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RealizedJointStateResolverError(f"{field} must be a finite numeric value") from exc
    if not result.is_finite():
        raise RealizedJointStateResolverError(f"{field} must be a finite numeric value")
    return result


def _player_id(value: Any, field: str) -> str:
    if isinstance(value, bool) or value is None:
        raise RealizedJointStateResolverError(f"{field} must be a non-empty player ID")
    result = str(value).strip()
    if not result:
        raise RealizedJointStateResolverError(f"{field} must be a non-empty player ID")
    return result


def _outcome_vector(
    rows: Any, *, actual: bool, expected_player_ids: set[str] | None = None
) -> tuple[dict[str, tuple[Decimal, bool, Decimal]], set[str]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        raise RealizedJointStateResolverError("player_outcomes must be a non-empty sequence")
    result = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise RealizedJointStateResolverError(f"player_outcomes[{index}] must be an object")
        pid = _player_id(row.get("fpl_element_id") if actual else row.get("player_id"), f"player_outcomes[{index}].player_id")
        if pid in result:
            raise RealizedJointStateResolverError(f"duplicate player outcome for {pid}")
        minutes = _decimal(row.get("minutes"), f"{pid}.minutes")
        points = _decimal(row.get("total_points") if actual else row.get("fpl_points"), f"{pid}.fpl_points")
        if minutes < 0:
            raise RealizedJointStateResolverError(f"{pid}.minutes cannot be negative")
        played = row.get("played_any_fixture") if actual else row.get("played")
        if not isinstance(played, bool):
            raise RealizedJointStateResolverError(f"{pid}.played must be boolean")
        result[pid] = (minutes, played, points)
    ids = set(result)
    if expected_player_ids is not None and ids != expected_player_ids:
        raise RealizedJointStateResolverError("scenario player universe differs from realized player universe")
    return result, ids


def resolve_realized_joint_state(
    *,
    realized_player_gameweek_rows: Sequence[Mapping[str, Any]],
    joint_state_catalogue: Sequence[Mapping[str, Any]],
    season: str,
    gameweek_id: str,
    realized_source_bytes: bytes,
    finality_audit: Mapping[str, Any],
) -> dict[str, Any]:
    """Match exact official realized outcomes to exactly one catalogue state.

    The catalogue is the complete state universe declared by the forecast
    producer. A successful result is directly consumable by the forecast
    outcome-pairing builder. No player rows are filled, dropped, or inferred.
    """
    if not isinstance(season, str) or not season.strip():
        raise RealizedJointStateResolverError("season is required")
    if not isinstance(gameweek_id, str) or not gameweek_id.strip():
        raise RealizedJointStateResolverError("gameweek_id is required")
    if not isinstance(realized_source_bytes, bytes) or not realized_source_bytes:
        raise RealizedJointStateResolverError("exact realized source bytes are required")
    if not isinstance(finality_audit, Mapping):
        raise RealizedJointStateResolverError("finality_audit must be an object")
    if (
        finality_audit.get("season") != season
        or str(finality_audit.get("event_id")) != str(gameweek_id)
        or finality_audit.get("status") != "PASS_EXACT_MATCH"
        or finality_audit.get("finality_reconciled") is not True
        or finality_audit.get("point_in_time_status") != "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT"
    ):
        raise RealizedJointStateResolverError("matching official retrospective finality audit must pass exact reconciliation")

    if not isinstance(realized_player_gameweek_rows, Sequence) or isinstance(realized_player_gameweek_rows, (str, bytes)) or not realized_player_gameweek_rows:
        raise RealizedJointStateResolverError("realized_player_gameweek_rows must be non-empty")
    actual_rows = []
    for row in realized_player_gameweek_rows:
        if not isinstance(row, Mapping):
            raise RealizedJointStateResolverError("realized rows must be objects")
        if row.get("season") != season or str(row.get("gameweek")) != str(gameweek_id):
            raise RealizedJointStateResolverError("all realized rows must match requested season and Gameweek")
        actual_rows.append(row)
    actual, player_ids = _outcome_vector(actual_rows, actual=True)
    sorted_player_ids = sorted(player_ids)
    player_universe_sha256 = canonical_json_sha256(sorted_player_ids)

    if not isinstance(joint_state_catalogue, Sequence) or isinstance(joint_state_catalogue, (str, bytes)) or not joint_state_catalogue:
        raise RealizedJointStateResolverError("joint_state_catalogue must be non-empty")
    catalogue_ids = set()
    matches = []
    catalogue_canonical = []
    for index, state in enumerate(joint_state_catalogue):
        if not isinstance(state, Mapping):
            raise RealizedJointStateResolverError(f"joint_state_catalogue[{index}] must be an object")
        state_id = str(state.get("scenario_id", "")).strip()
        if not state_id or state_id in catalogue_ids:
            raise RealizedJointStateResolverError("catalogue scenario IDs must be unique and non-empty")
        catalogue_ids.add(state_id)
        vector, _ = _outcome_vector(state.get("player_outcomes"), actual=False, expected_player_ids=player_ids)
        normalized = {
            "scenario_id": state_id,
            "player_outcomes": [
                {
                    "player_id": pid,
                    "minutes": str(vector[pid][0]),
                    "played": vector[pid][1],
                    "fpl_points": str(vector[pid][2]),
                }
                for pid in sorted(vector)
            ],
        }
        catalogue_canonical.append(normalized)
        if vector == actual:
            matches.append(state_id)

    state_catalogue_sha256 = canonical_json_sha256(catalogue_canonical)
    realized_source_sha256 = hashlib.sha256(realized_source_bytes).hexdigest()
    base = {
        "season": season,
        "gameweek_id": str(gameweek_id),
        "state_catalogue_sha256": state_catalogue_sha256,
        "player_universe_sha256": player_universe_sha256,
        "realized_source_sha256": realized_source_sha256,
        "resolver_name": RESOLVER_NAME,
        "resolver_version": RESOLVER_VERSION,
        "finality_audit_status": "PASS_EXACT_MATCH",
        "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT",
        "mapped_player_count": len(player_ids),
        "missing_player_count": 0,
        "unexpected_player_count": 0,
        "mapping_inferred_from_marginals": False,
    }

    if len(matches) != 1:
        status = "FAIL_NO_EXACT_STATE_MATCH" if not matches else "FAIL_AMBIGUOUS_STATE_MATCH"
        evidence = {**base, "mapping_status": status, "matching_state_ids": sorted(matches)}
        return {
            **evidence,
            "mapping_source_sha256": canonical_json_sha256(evidence),
            "observed_state_id": None,
            "catalogue_state_count": len(catalogue_ids),
            "decision_weight": 0.0,
            "production_eligible": False,
        }

    evidence = {
        **base,
        "mapping_status": "PASS_EXACT_OBSERVED_STATE_RESOLUTION",
        "observed_state_id": matches[0],
    }
    return {
        **evidence,
        "mapping_source_sha256": canonical_json_sha256(evidence),
        "catalogue_state_count": len(catalogue_ids),
        "decision_weight": 0.0,
        "production_eligible": False,
        "limitations": [
            "The observed state is matched exactly against the supplied catalogue; the resolver does not prove the catalogue is exhaustive.",
            "A no-match result indicates realized-state support failure and must not be repaired by choosing the nearest scenario.",
            "The retrospective official event-live audit does not establish point-in-time availability.",
            "This resolver does not generate probabilities or validate their calibration.",
        ],
    }
