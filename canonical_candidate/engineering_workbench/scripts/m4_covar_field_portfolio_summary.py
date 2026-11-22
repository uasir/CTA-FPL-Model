#!/usr/bin/env python3
"""Aggregate manager-level field portfolios without exporting individual squads.

The output describes sampled portfolio co-selection, captaincy and overlap.
Co-selection covariance is a binary portfolio-membership statistic, not player
outcome covariance and not a forecast of relative FPL scores.
"""
from __future__ import annotations

import math
from collections import Counter
from itertools import combinations
from typing import Any, Mapping, Sequence


class CovarFieldPortfolioSummaryError(ValueError):
    """Raised when a manager portfolio sample cannot be summarized safely."""


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise CovarFieldPortfolioSummaryError(f"{label} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CovarFieldPortfolioSummaryError(f"{label} must be finite") from exc
    if not math.isfinite(number):
        raise CovarFieldPortfolioSummaryError(f"{label} must be finite")
    return number


def _weighted_quantile(rows: Sequence[tuple[float, float]], q: float) -> float | None:
    if not rows:
        return None
    ordered = sorted(rows, key=lambda row: row[0])
    total = sum(weight for _, weight in ordered)
    if total <= 0:
        return None
    threshold = q * total
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def _pair_rows(
    joint_weights: Mapping[tuple[str, str], float],
    marginal: Mapping[str, float],
    *,
    limit: int,
    order: str,
) -> list[dict[str, Any]]:
    rows = []
    for (left, right), joint in joint_weights.items():
        p_left = marginal.get(left, 0.0)
        p_right = marginal.get(right, 0.0)
        covariance = joint - p_left * p_right
        denominator = math.sqrt(
            max(0.0, p_left * (1.0 - p_left) * p_right * (1.0 - p_right))
        )
        correlation = covariance / denominator if denominator > 0 else None
        if abs(covariance) <= 1e-12:
            continue
        rows.append({
            "player_id_a": left,
            "player_id_b": right,
            "joint_exposure": round(joint, 8),
            "co_selection_covariance": round(covariance, 8),
            "co_selection_correlation": None if correlation is None else round(correlation, 8),
        })
    rows.sort(
        key=lambda row: (
            -row["co_selection_covariance"] if order == "positive" else row["co_selection_covariance"],
            row["player_id_a"],
            row["player_id_b"],
        )
    )
    return rows[:limit]


def summarize_field_portfolio_sample(
    artifact: Mapping[str, Any],
    *,
    top_players: int = 25,
    top_pairs: int = 20,
) -> dict[str, Any]:
    """Return aggregate-only exposure, co-selection and portfolio-overlap metrics."""
    if not isinstance(artifact, Mapping) or artifact.get("schema_version") != "1.1.0":
        raise CovarFieldPortfolioSummaryError("a schema 1.1.0 field portfolio artifact is required")
    if artifact.get("data_status") != "MANAGER_ID_STRIPPED_MANAGER_PICK_SAMPLE":
        raise CovarFieldPortfolioSummaryError("unsupported field portfolio data status")
    metadata = artifact.get("metadata")
    portfolios = artifact.get("portfolios")
    if not isinstance(metadata, Mapping) or not isinstance(portfolios, list) or not portfolios:
        raise CovarFieldPortfolioSummaryError("artifact metadata and non-empty portfolios are required")
    if metadata.get("manager_entry_ids_retained") is not False:
        raise CovarFieldPortfolioSummaryError("manager entry IDs must be discarded before summarization")
    if metadata.get("evidence_role") != "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE":
        raise CovarFieldPortfolioSummaryError("only pre-deadline provisional field portfolios are admitted")
    if (
        isinstance(top_players, bool) or not isinstance(top_players, int) or top_players < 1
        or isinstance(top_pairs, bool) or not isinstance(top_pairs, int) or top_pairs < 1
    ):
        raise CovarFieldPortfolioSummaryError("top_players and top_pairs must be positive integers")
    if int(metadata.get("manager_count", -1)) != len(portfolios):
        raise CovarFieldPortfolioSummaryError("metadata manager_count does not match portfolio sample")

    normalized = []
    player_ids: set[str] = set()
    squad_exposure: dict[str, float] = {}
    xi_exposure: dict[str, float] = {}
    captain_exposure: dict[str, float] = {}
    triple_captain_exposure: dict[str, float] = {}
    squad_pairs: Counter[tuple[str, str]] = Counter()
    xi_pairs: Counter[tuple[str, str]] = Counter()

    for index, portfolio in enumerate(portfolios):
        if not isinstance(portfolio, Mapping):
            raise CovarFieldPortfolioSummaryError("each portfolio must be an object")
        squad = portfolio.get("player_ids")
        starting = portfolio.get("starting_player_ids")
        bench = portfolio.get("bench_order")
        reserve_goalkeeper = str(portfolio.get("reserve_goalkeeper_id") or "")
        starting_goalkeeper = str(portfolio.get("starting_goalkeeper_id") or "")
        if (
            not isinstance(squad, list) or len(squad) != 15
            or len(set(map(str, squad))) != 15
            or not isinstance(starting, list) or len(starting) != 11
            or not isinstance(bench, list) or len(bench) != 3
        ):
            raise CovarFieldPortfolioSummaryError(
                f"portfolio {index} must contain 15 unique players, 11 starters and 3 outfield bench players"
            )
        squad_ids = [str(pid) for pid in squad]
        starting_ids = [str(pid) for pid in starting]
        bench_ids = [reserve_goalkeeper, *[str(pid) for pid in bench]]
        if (
            not set(starting_ids).issubset(squad_ids)
            or not set(bench_ids).issubset(squad_ids)
            or not reserve_goalkeeper
            or not starting_goalkeeper
        ):
            raise CovarFieldPortfolioSummaryError(
                "starting XI, reserve goalkeeper and bench must be subsets of the squad"
            )
        if set(starting_ids).intersection(bench_ids) or set(starting_ids).union(bench_ids) != set(squad_ids):
            raise CovarFieldPortfolioSummaryError(
                "starting XI, reserve goalkeeper and bench must partition the 15-player squad"
            )
        player_positions = portfolio.get("player_positions")
        if not isinstance(player_positions, Mapping) or set(map(str, player_positions)) != set(squad_ids):
            raise CovarFieldPortfolioSummaryError("each portfolio must include positions for all 15 players")
        normalized_positions = {str(pid): str(role).upper() for pid, role in player_positions.items()}
        if any(role not in ("GK", "DEF", "MID", "FWD") for role in normalized_positions.values()):
            raise CovarFieldPortfolioSummaryError("player positions must be GK, DEF, MID or FWD")
        if (
            starting_goalkeeper not in starting_ids
            or str(player_positions.get(starting_goalkeeper, "")).upper() != "GK"
            or str(player_positions.get(reserve_goalkeeper, "")).upper() != "GK"
            or sum(normalized_positions[pid] == "GK" for pid in starting_ids) != 1
            or any(str(player_positions.get(pid, "")).upper() == "GK" for pid in bench)
        ):
            raise CovarFieldPortfolioSummaryError(
                "starting and reserve goalkeeper slots must be valid; outfield bench cannot contain a goalkeeper"
            )
        formation = {role: sum(normalized_positions[pid] == role for pid in starting_ids) for role in ("DEF", "MID", "FWD")}
        if formation["DEF"] < 3 or formation["MID"] < 2 or formation["FWD"] < 1:
            raise CovarFieldPortfolioSummaryError("starting XI does not satisfy legal FPL formation minimums")
        captain = str(portfolio.get("captain_id") or "")
        vice = str(portfolio.get("vice_captain_id") or "")
        if captain not in starting_ids or vice not in starting_ids or captain == vice:
            raise CovarFieldPortfolioSummaryError("captain and vice-captain must be distinct starting players")
        multiplier = portfolio.get("captain_multiplier")
        if multiplier not in (2, 3):
            raise CovarFieldPortfolioSummaryError("captain_multiplier must be 2 or 3")
        chip = portfolio.get("active_chip")
        if chip not in (None, "3xc", "bboost", "freehit", "wildcard"):
            raise CovarFieldPortfolioSummaryError("unsupported active chip")
        if (chip == "3xc" and multiplier != 3) or (chip != "3xc" and multiplier != 2):
            raise CovarFieldPortfolioSummaryError("captain multiplier must agree with active chip")
        weight = _finite(portfolio.get("field_weight"), f"portfolios[{index}].field_weight")
        if weight <= 0:
            raise CovarFieldPortfolioSummaryError("field weights must be positive")
        normalized.append((squad_ids, starting_ids, captain, multiplier, chip, weight))
        player_ids.update(squad_ids)
        for pid in squad_ids:
            squad_exposure[pid] = squad_exposure.get(pid, 0.0) + weight
        for pid in starting_ids:
            xi_exposure[pid] = xi_exposure.get(pid, 0.0) + weight
        captain_exposure[captain] = captain_exposure.get(captain, 0.0) + weight
        if chip == "3xc" or multiplier == 3:
            triple_captain_exposure[captain] = triple_captain_exposure.get(captain, 0.0) + weight
        for pair in combinations(sorted(squad_ids), 2):
            squad_pairs[pair] += weight
        for pair in combinations(sorted(starting_ids), 2):
            xi_pairs[pair] += weight

    total_weight = sum(row[5] for row in normalized)
    if not math.isclose(total_weight, 1.0, rel_tol=1e-8, abs_tol=1e-8):
        raise CovarFieldPortfolioSummaryError("field portfolio weights must be normalized to one")
    effective_sample_size = 1.0 / sum(row[5] ** 2 for row in normalized)

    player_rows = []
    for pid in player_ids:
        squad_share = squad_exposure.get(pid, 0.0)
        xi_share = xi_exposure.get(pid, 0.0)
        player_rows.append({
            "player_id": pid,
            "squad_exposure": round(squad_share, 8),
            "starting_xi_exposure": round(xi_share, 8),
            "bench_exposure": round(max(0.0, squad_share - xi_share), 8),
            "captain_exposure": round(captain_exposure.get(pid, 0.0), 8),
            "triple_captain_exposure": round(triple_captain_exposure.get(pid, 0.0), 8),
        })
    player_rows.sort(key=lambda row: (-row["squad_exposure"], -row["captain_exposure"], row["player_id"]))

    pairwise_squad_overlaps: list[tuple[float, float]] = []
    pairwise_xi_overlaps: list[tuple[float, float]] = []
    pairwise_squad_jaccards: list[tuple[float, float]] = []
    pair_weight_total = 0.0
    for left, right in combinations(normalized, 2):
        left_squad, left_xi, _, _, _, left_weight = left
        right_squad, right_xi, _, _, _, right_weight = right
        pair_weight = left_weight * right_weight
        pair_weight_total += pair_weight
        squad_intersection = len(set(left_squad).intersection(right_squad))
        xi_intersection = len(set(left_xi).intersection(right_xi))
        squad_union = len(set(left_squad).union(right_squad))
        pairwise_squad_overlaps.append((float(squad_intersection), pair_weight))
        pairwise_xi_overlaps.append((float(xi_intersection), pair_weight))
        pairwise_squad_jaccards.append((squad_intersection / squad_union, pair_weight))
    if pair_weight_total > 0:
        pairwise_squad_overlaps = [(value, weight / pair_weight_total) for value, weight in pairwise_squad_overlaps]
        pairwise_xi_overlaps = [(value, weight / pair_weight_total) for value, weight in pairwise_xi_overlaps]
        pairwise_squad_jaccards = [(value, weight / pair_weight_total) for value, weight in pairwise_squad_jaccards]

    def overlap_summary(values: Sequence[tuple[float, float]]) -> dict[str, Any]:
        if not values:
            return {"mean": None, "median": None, "p90": None}
        return {
            "mean": round(sum(value * weight for value, weight in values), 8),
            "median": round(_weighted_quantile(values, 0.5) or 0.0, 8),
            "p90": round(_weighted_quantile(values, 0.9) or 0.0, 8),
        }

    return {
        "schema_version": "1.0.0",
        "data_status": "AGGREGATE_ONLY_PRE_DEADLINE_PORTFOLIO_STRUCTURE",
        "metadata": {
            "gameweek": int(metadata["gameweek"]),
            "deadline_utc": metadata["deadline_utc"],
            "captured_at_utc": metadata["captured_at_utc"],
            "evidence_role": metadata["evidence_role"],
            "cohort": metadata["cohort"],
            "rank_limit": int(metadata["rank_limit"]),
            "manager_count": len(normalized),
            "rank_strata_count_observed": int(metadata.get("rank_strata_count_observed", 0)),
            "effective_sample_size": round(effective_sample_size, 6),
            "field_weighting": metadata.get("field_weighting"),
            "marginal_measure_role": "DESCRIPTIVE_SAMPLE_INCLUSION_NOT_OFFICIAL_EO",
            "official_eo_source": "EXISTING_RANK_STRATIFIED_EO_ESTIMATOR",
            "not_official_eo": True,
            "global_census": False,
            "picks_lock_verified": False,
            "provisional_picks": True,
            "manager_entry_ids_retained": False,
            "manager_names_retained": False,
            "exact_ranks_retained": False,
            "raw_manager_picks_retained": False,
            "privacy_note": "Only aggregate player exposure, co-selection and pairwise overlap metrics are emitted; individual portfolios and manager identifiers are not retained.",
            "interpretation_note": "Co-selection covariance/correlation describes binary player inclusion across sampled manager portfolios. It is not player outcome covariance, a joint match scenario, or a field-relative score forecast.",
        },
        "portfolio_overlap": {
            "squad_shared_players": overlap_summary(pairwise_squad_overlaps),
            "starting_xi_shared_players": overlap_summary(pairwise_xi_overlaps),
            "squad_jaccard_similarity": overlap_summary(pairwise_squad_jaccards),
        },
        "player_exposure_top": player_rows[:top_players],
        "positive_squad_co_selection": _pair_rows(squad_pairs, squad_exposure, limit=top_pairs, order="positive"),
        "negative_squad_co_selection": _pair_rows(squad_pairs, squad_exposure, limit=top_pairs, order="negative"),
        "positive_starting_xi_co_selection": _pair_rows(xi_pairs, xi_exposure, limit=top_pairs, order="positive"),
        "negative_starting_xi_co_selection": _pair_rows(xi_pairs, xi_exposure, limit=top_pairs, order="negative"),
        "decision_weight": 0.0,
        "production_eligible": False,
    }
