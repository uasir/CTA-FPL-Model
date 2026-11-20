#!/usr/bin/env python3
"""Build anonymised CoVar field portfolios from the existing sampled manager picks.

Only explicit manager-pick rows are accepted. Manager entry IDs are used for
grouping and then discarded; they are never emitted in the artifact.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from typing import Any, Mapping, Sequence


class CovarFieldPortfolioError(ValueError):
    pass


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise CovarFieldPortfolioError(f"{label} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CovarFieldPortfolioError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CovarFieldPortfolioError(f"{label} must include a timezone")
    return parsed


def anonymize_manager_pick_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    gameweek: int,
    deadline_utc: str,
    captured_at_utc: str,
    evidence_role: str,
    cohort: str,
    rank_limit: int,
) -> dict[str, Any]:
    """Convert one row per manager-player pick into anonymised 15-player portfolios."""
    if evidence_role != "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE":
        raise CovarFieldPortfolioError("only pre-deadline provisional pick evidence is admitted")
    deadline = _time(deadline_utc, "deadline_utc")
    captured = _time(captured_at_utc, "captured_at_utc")
    if captured >= deadline:
        raise CovarFieldPortfolioError("manager picks must be captured before the deadline")
    if gameweek < 1 or rank_limit < 1 or not cohort.strip():
        raise CovarFieldPortfolioError("gameweek, rank_limit and cohort must be valid")

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        manager_id = str(row.get("entry_id", "")).strip()
        if not manager_id:
            raise CovarFieldPortfolioError("manager pick row is missing entry_id")
        if str(row.get("gameweek")) != str(gameweek):
            raise CovarFieldPortfolioError("manager pick rows must belong to one target Gameweek")
        grouped.setdefault(manager_id, []).append(row)
    if not grouped:
        raise CovarFieldPortfolioError("manager pick rows are empty")

    normalized = []
    for manager_id, picks in grouped.items():
        if len(picks) != 15:
            raise CovarFieldPortfolioError(f"manager sample must contain exactly 15 picks; got {len(picks)}")
        positions = [int(row["position"]) for row in picks]
        player_ids = [str(row["fpl_element_id"]) for row in picks]
        if sorted(positions) != list(range(1, 16)) or len(set(player_ids)) != 15:
            raise CovarFieldPortfolioError("each manager must have 15 unique players and positions 1..15")
        captains = [row for row in picks if row.get("is_captain") is True]
        if len(captains) != 1 or int(captains[0]["position"]) > 11:
            raise CovarFieldPortfolioError("each manager must have exactly one starting captain")
        weights = {float(row["sample_weight"]) for row in picks}
        ranks = {int(row["rank_before_deadline"]) for row in picks}
        chips = {str(row.get("active_chip") or "").strip().lower() for row in picks}
        if len(weights) != 1 or not math.isfinite(next(iter(weights))) or next(iter(weights)) <= 0:
            raise CovarFieldPortfolioError("each manager must have one positive finite sample weight")
        if len(ranks) != 1 or not 1 <= next(iter(ranks)) <= rank_limit:
            raise CovarFieldPortfolioError("each manager must have one rank within the sampled rank limit")
        if len(chips) != 1:
            raise CovarFieldPortfolioError("active_chip must be consistent within each manager")
        chip = next(iter(chips))
        if chip not in ("", "3xc", "bboost", "freehit", "wildcard"):
            raise CovarFieldPortfolioError("manager sample contains an unsupported active chip")
        picks_by_position = sorted(picks, key=lambda row: int(row["position"]))
        captain_id = str(captains[0]["fpl_element_id"])
        normalized.append({
            "_sort_rank": next(iter(ranks)),
            "_sort_key": manager_id,
            "weight": next(iter(weights)),
            "player_ids": [str(row["fpl_element_id"]) for row in picks_by_position],
            "captain_id": captain_id,
            "captain_multiplier": 3 if chip == "3xc" else 2,
            "rank_stratum": (next(iter(ranks)) - 1) // 50 + 1,
            "active_chip": chip or None,
        })

    normalized.sort(key=lambda row: (row["_sort_rank"], row["_sort_key"]))
    total_weight = sum(row["weight"] for row in normalized)
    portfolios = []
    for index, row in enumerate(normalized, start=1):
        portfolios.append({
            "portfolio_id": f"field_sample_{index:04d}",
            "player_ids": row["player_ids"],
            "captain_id": row["captain_id"],
            "captain_multiplier": row["captain_multiplier"],
            "field_weight": row["weight"] / total_weight,
            "rank_stratum": row["rank_stratum"],
            "active_chip": row["active_chip"],
            "portfolio_role": "FIELD",
        })

    return {
        "schema_version": "1.0.0",
        "data_status": "ANONYMIZED_MANAGER_PICK_SAMPLE",
        "metadata": {
            "gameweek": int(gameweek),
            "deadline_utc": deadline.isoformat(),
            "captured_at_utc": captured.isoformat(),
            "evidence_role": evidence_role,
            "picks_lock_verified": False,
            "provisional_picks": True,
            "cohort": cohort,
            "rank_limit": int(rank_limit),
            "manager_count": len(portfolios),
            "rank_strata_count_observed": len({row["rank_stratum"] for row in portfolios}),
            "field_weighting": "normalized_existing_rank_stratified_sample_weights",
            "manager_identifiers_retained": False,
            "global_census": False,
        },
        "portfolios": portfolios,
    }


def adapt_field_portfolios_for_scenario(
    artifact: Mapping[str, Any],
    modeled_player_ids: Sequence[str],
    *,
    expected_gameweek: int,
    deadline_utc: str,
    as_of_utc: str,
    rank_strata: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Project sampled full squads onto the modeled player universe, fail-closed."""
    if artifact.get("schema_version") != "1.0.0" or artifact.get("data_status") != "ANONYMIZED_MANAGER_PICK_SAMPLE":
        raise CovarFieldPortfolioError("unsupported anonymised field portfolio artifact")
    metadata = artifact.get("metadata")
    source_portfolios = artifact.get("portfolios")
    if not isinstance(metadata, Mapping) or not isinstance(source_portfolios, list) or not source_portfolios:
        raise CovarFieldPortfolioError("artifact metadata and portfolios are required")
    if metadata.get("evidence_role") != "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE":
        raise CovarFieldPortfolioError("only pre-deadline provisional evidence is admitted")
    if metadata.get("picks_lock_verified") is not False or metadata.get("provisional_picks") is not True:
        raise CovarFieldPortfolioError("field picks must be explicitly provisional and not lock-verified")
    if int(metadata.get("gameweek", -1)) != int(expected_gameweek):
        raise CovarFieldPortfolioError("field artifact Gameweek mismatch")
    source_deadline = _time(metadata.get("deadline_utc"), "artifact.deadline_utc")
    target_deadline = _time(deadline_utc, "deadline_utc")
    captured = _time(metadata.get("captured_at_utc"), "artifact.captured_at_utc")
    as_of = _time(as_of_utc, "as_of_utc")
    if source_deadline != target_deadline:
        raise CovarFieldPortfolioError("field artifact deadline mismatch")
    if not captured < as_of < target_deadline:
        raise CovarFieldPortfolioError("field capture must precede decision as_of, and both must precede deadline")
    modeled = {str(value) for value in modeled_player_ids}
    if not modeled:
        raise CovarFieldPortfolioError("modeled_player_ids must be non-empty")
    selected_strata = None if rank_strata is None else {int(value) for value in rank_strata}
    if selected_strata is not None and not selected_strata:
        raise CovarFieldPortfolioError("rank_strata selection cannot be empty")

    chosen = []
    for source in source_portfolios:
        if not isinstance(source, Mapping):
            raise CovarFieldPortfolioError("each source portfolio must be an object")
        stratum = int(source.get("rank_stratum", 0))
        if selected_strata is not None and stratum not in selected_strata:
            continue
        source_players = source.get("player_ids")
        if not isinstance(source_players, list) or len(source_players) != 15 or len(set(map(str, source_players))) != 15:
            raise CovarFieldPortfolioError("each anonymised source portfolio must contain 15 unique players")
        projected = [str(player_id) for player_id in source_players if str(player_id) in modeled]
        source_captain = source.get("captain_id")
        captain_in_scope = source_captain is not None and str(source_captain) in modeled
        chosen.append({
            "portfolio_id": str(source.get("portfolio_id")),
            "portfolio_role": "FIELD",
            "player_ids": projected,
            "captain_id": str(source_captain) if captain_in_scope else None,
            "captain_multiplier": int(source.get("captain_multiplier", 2)) if captain_in_scope else 1,
            "field_weight": float(source.get("field_weight")),
            "rank_stratum": stratum,
            "active_chip": source.get("active_chip"),
        })
    if not chosen:
        raise CovarFieldPortfolioError("no field portfolios remain in the requested rank cohort")
    total = sum(row["field_weight"] for row in chosen)
    if not math.isfinite(total) or total <= 0:
        raise CovarFieldPortfolioError("selected field portfolio weights must have a positive finite sum")
    for row in chosen:
        row["field_weight"] /= total

    projected_nonempty = sum(bool(row["player_ids"]) for row in chosen)
    captain_in_scope_count = sum(row["captain_id"] is not None for row in chosen)
    return {
        "schema_version": "1.0.0",
        "portfolios": chosen,
        "metadata": {
            "gameweek": int(expected_gameweek),
            "deadline_utc": target_deadline.isoformat(),
            "captured_at_utc": captured.isoformat(),
            "as_of_utc": as_of.isoformat(),
            "cohort": metadata.get("cohort"),
            "rank_strata": sorted({row["rank_stratum"] for row in chosen}),
            "source_manager_count": len(source_portfolios),
            "selected_manager_count": len(chosen),
            "modeled_player_count": len(modeled),
            "managers_with_modeled_players": projected_nonempty,
            "manager_projection_coverage": projected_nonempty / len(chosen),
            "managers_with_modeled_captain": captain_in_scope_count,
            "captain_projection_coverage": captain_in_scope_count / len(chosen),
            "manager_identifiers_retained": False,
            "evidence_role": metadata["evidence_role"],
            "field_scope": "ANONYMIZED_RANK_STRATIFIED_SAMPLE_NOT_GLOBAL_CENSUS",
            "production_eligible": False,
            "decision_weight": 0.0,
        },
    }


def canonical_artifact_sha256(artifact: Mapping[str, Any]) -> str:
    payload = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
