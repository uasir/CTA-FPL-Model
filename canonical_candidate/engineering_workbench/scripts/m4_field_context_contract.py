#!/usr/bin/env python3
"""Validate and bind a pre-deadline field-EO snapshot to a frozen M3 decision.

This module validates provenance and compatibility only. It never estimates EO,
changes provider xP, converts EO into points, or computes CoVar.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime
from typing import Any, Mapping


class FieldContextContractError(ValueError):
    pass


CONTRACT_VERSION = "1.0.0"
OPTIONAL_EO_FIELDS = ("owned_by_pct", "effective_ownership_pct", "starting_pct",
                     "captain_pct", "triple_captain_pct", "scoring_exposure_pct",
                     "effective_ownership_pct_ci95_low", "effective_ownership_pct_ci95_high")


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise FieldContextContractError(f"{label} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FieldContextContractError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FieldContextContractError(f"{label} must include a timezone")
    return parsed


def _finite_nonnegative(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise FieldContextContractError(f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FieldContextContractError(f"{label} must be numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise FieldContextContractError(f"{label} must be finite and non-negative")
    return number


def validate_field_context(snapshot: Mapping[str, Any], rows: list[Mapping[str, Any]],
                           candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Return a normalized, provenance-bound M4 field-context envelope."""
    if not isinstance(snapshot, Mapping) or not isinstance(candidate, Mapping):
        raise FieldContextContractError("snapshot and candidate must be objects")
    required = ("snapshot_id", "season", "target_gameweek", "deadline_utc",
                "captured_at_utc", "cohort", "sample", "coverage", "source")
    missing = [key for key in required if key not in snapshot]
    if missing:
        raise FieldContextContractError("snapshot missing: " + ", ".join(missing))
    if not isinstance(rows, list) or not rows:
        raise FieldContextContractError("field EO rows must be a non-empty list")

    gw = int(snapshot["target_gameweek"])
    if gw < 1 or not str(snapshot["season"]).strip() or not str(snapshot["snapshot_id"]).strip():
        raise FieldContextContractError("snapshot identity is invalid")
    deadline = _time(snapshot["deadline_utc"], "deadline_utc")
    captured = _time(snapshot["captured_at_utc"], "captured_at_utc")
    as_of = _time(candidate.get("as_of_utc"), "candidate.as_of_utc")
    if captured >= deadline or as_of >= deadline:
        raise FieldContextContractError("pre-deadline comparison requires capture and decision before deadline")
    if captured >= as_of:
        raise FieldContextContractError("field snapshot must be captured strictly before the frozen M3 decision")
    if candidate.get("season") != snapshot["season"]:
        raise FieldContextContractError("candidate season does not match field snapshot")
    if int(candidate.get("target_gameweek", -1)) != gw:
        raise FieldContextContractError("candidate Gameweek does not match field snapshot")
    candidate_deadline = _time(candidate.get("deadline_utc"), "candidate.deadline_utc")
    if candidate_deadline != deadline:
        raise FieldContextContractError("candidate deadline does not match field snapshot")

    cohort = snapshot["cohort"]
    sample = snapshot["sample"]
    coverage = snapshot["coverage"]
    source = snapshot["source"]
    if not all(isinstance(value, Mapping) for value in (cohort, sample, coverage, source)):
        raise FieldContextContractError("cohort, sample, coverage and source must be objects")
    if not str(cohort.get("name", "")).strip():
        raise FieldContextContractError("cohort.name is required")
    rank_min, rank_max = cohort.get("rank_min"), cohort.get("rank_max")
    if rank_min is not None and (int(rank_min) < 1 or int(rank_max) < int(rank_min)):
        raise FieldContextContractError("cohort rank range is invalid")
    manager_count = int(sample.get("manager_count", 0))
    effective_n = _finite_nonnegative(sample.get("effective_sample_size"), "effective_sample_size")
    if manager_count < 1 or effective_n <= 0:
        raise FieldContextContractError("sample manager_count and effective sample size must be positive")
    if not str(sample.get("weighting", "")).strip():
        raise FieldContextContractError("sample.weighting is required")
    digest = str(source.get("artifact_sha256", "")).lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise FieldContextContractError("source.artifact_sha256 must be a SHA-256 hex digest")
    if not str(source.get("source_url", "")).strip():
        raise FieldContextContractError("source.source_url is required")

    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or str(row.get("gameweek")) != str(gw):
            raise FieldContextContractError("every EO row must belong to the target Gameweek")
        player_id = str(row.get("fpl_element_id", "")).strip()
        if not player_id or player_id in by_id:
            raise FieldContextContractError("EO rows contain a missing or duplicate player ID")
        normalized = dict(row)
        for field in OPTIONAL_EO_FIELDS:
            if field not in row:
                raise FieldContextContractError(f"{player_id}.{field} key is required; use null when unavailable")
            if row[field] not in (None, ""):
                _finite_nonnegative(row[field], f"{player_id}.{field}")
            else:
                normalized[field] = None
        by_id[player_id] = normalized

    if not isinstance(coverage.get("covered_player_ids"), list) or not isinstance(coverage.get("missing_player_ids"), list):
        raise FieldContextContractError("coverage must explicitly list covered_player_ids and missing_player_ids")
    covered_ids = set(str(value) for value in coverage["covered_player_ids"])
    missing_ids = set(str(value) for value in coverage["missing_player_ids"])
    if covered_ids != set(by_id):
        raise FieldContextContractError("coverage covered_player_ids do not match EO rows")
    if covered_ids & missing_ids:
        raise FieldContextContractError("a player cannot be both covered and missing")
    decision = candidate.get("frozen_decision")
    if not isinstance(decision, Mapping):
        raise FieldContextContractError("candidate.frozen_decision is required")
    manager_state = candidate.get("manager_state")
    if not isinstance(manager_state, Mapping):
        raise FieldContextContractError("candidate.manager_state is required")
    # Canonical capture bundles store the validated state under manager_state.
    state = manager_state.get("manager_state", manager_state)
    if not isinstance(state, Mapping):
        raise FieldContextContractError("candidate manager state must be an object")
    squad = state.get("squad_15")
    if not isinstance(squad, list) or len(squad) != 15 or len(set(map(str, squad))) != 15:
        raise FieldContextContractError("candidate must contain its original 15 unique squad IDs")
    starting_xi = state.get("starting_xi")
    bench_order = state.get("bench_order")
    reserve_goalkeeper_id = state.get("reserve_goalkeeper_id")
    captain_id = state.get("captain_id")
    if (not isinstance(starting_xi, list) or len(starting_xi) != 11
            or not isinstance(bench_order, list) or len(bench_order) != 3
            or reserve_goalkeeper_id is None or captain_id is None
            or set(map(str, starting_xi + bench_order + [reserve_goalkeeper_id])) != set(map(str, squad))):
        raise FieldContextContractError("candidate lineup must partition the 15-player squad")
    owned_ids = set(map(str, squad))
    transfer_in = decision.get("transfer_in_id")
    transfer_out = decision.get("transfer_out_id")
    if decision.get("action") == "TRANSFER":
        if not transfer_in or not transfer_out or str(transfer_out) not in owned_ids:
            raise FieldContextContractError("TRANSFER candidate must identify an owned outgoing and incoming player")
        if str(transfer_in) in owned_ids - {str(transfer_out)}:
            raise FieldContextContractError("incoming player already exists in candidate squad")
        if str(transfer_out) == str(captain_id):
            raise FieldContextContractError("candidate transfer removes captain without a replacement captain decision")
        owned_ids.remove(str(transfer_out))
        owned_ids.add(str(transfer_in))
    elif decision.get("action") != "HOLD":
        raise FieldContextContractError("candidate action must be HOLD or TRANSFER")
    missing_owned = sorted(owned_ids - set(by_id), key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value))
    if missing_owned:
        raise FieldContextContractError("field EO snapshot lacks candidate squad players: " + ", ".join(missing_owned))

    binding = {
        "contract_version": CONTRACT_VERSION,
        "snapshot_id": str(snapshot["snapshot_id"]),
        "season": str(snapshot["season"]),
        "target_gameweek": gw,
        "deadline_utc": deadline.isoformat(),
        "captured_at_utc": captured.isoformat(),
        "cohort": dict(cohort),
        "sample": dict(sample),
        "coverage": {
            "covered_player_count": len(by_id),
            "missing_player_ids": sorted(missing_ids),
            "candidate_squad_covered": True,
        },
        "source": {"source_url": source["source_url"], "artifact_sha256": digest},
        "candidate": {
            "manager_team_id": candidate.get("manager_team_id"),
            "decision_sha256": decision.get("decision_sha256"),
            "action": decision["action"],
            "transfer_out_id": transfer_out,
            "transfer_in_id": transfer_in,
            "squad_15": list(map(str, squad)),
            "starting_xi": list(map(str, starting_xi)),
            "bench_order": list(map(str, bench_order)),
            "reserve_goalkeeper_id": str(reserve_goalkeeper_id),
            "captain_id": str(captain_id),
            "vice_captain_id": str(state.get("vice_captain_id")),
            "formation": state.get("formation"),
        },
        "field_eo_rows": [by_id[key] for key in sorted(by_id, key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value))],
        "units_policy": {
            "expected_points": "points",
            "effective_ownership": "percentage_points",
            "combination": "PROHIBITED",
            "covar": "DISABLED",
        },
        "field_scope": "sample_estimate_not_global_census",
        "release_eligible": False,
    }
    return binding
