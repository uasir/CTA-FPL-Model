#!/usr/bin/env python3
"""Compare frozen HOLD and TRANSFER squad exposure against one field EO snapshot.

This is a percentage-point exposure comparison, not a points/rank forecast.
It does not estimate EO, alter provider xP, or compute CoVar.
"""
from __future__ import annotations

from typing import Any, Mapping


class CandidateFieldComparisonError(ValueError):
    pass


def _pct(row: Mapping[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    number = float(value)
    if number < 0:
        raise CandidateFieldComparisonError(f"{key} must be non-negative")
    return number


def compare_frozen_candidate_to_field(binding: Mapping[str, Any]) -> dict[str, Any]:
    """Produce HOLD and frozen-decision exposure views from a validated M4 binding."""
    if binding.get("contract_version") != "1.0.0":
        raise CandidateFieldComparisonError("unsupported field-context contract version")
    if binding.get("release_eligible") is not False:
        raise CandidateFieldComparisonError("field comparison must remain non-release-eligible")
    if binding.get("units_policy", {}).get("covar") != "DISABLED":
        raise CandidateFieldComparisonError("CoVar must remain disabled in this comparison")

    candidate = binding.get("candidate")
    if not isinstance(candidate, Mapping):
        raise CandidateFieldComparisonError("validated candidate metadata is required")
    squad = [str(value) for value in candidate.get("squad_15", [])]
    starting = [str(value) for value in candidate.get("starting_xi", [])]
    bench = [str(value) for value in candidate.get("bench_order", [])]
    reserve_gk = str(candidate.get("reserve_goalkeeper_id", ""))
    captain = str(candidate.get("captain_id", ""))
    if len(squad) != 15 or len(set(squad)) != 15 or len(starting) != 11:
        raise CandidateFieldComparisonError("candidate squad or starting XI is malformed")
    if set(starting) & set(bench) or set(starting) | set(bench) | {reserve_gk} != set(squad):
        raise CandidateFieldComparisonError("candidate lineup does not partition the squad")
    if captain not in starting:
        raise CandidateFieldComparisonError("captain must be in the starting XI")

    decision = candidate.get("action")
    proposed_squad = list(squad)
    proposed_starting = list(starting)
    proposed_bench = list(bench)
    transfer_out = candidate.get("transfer_out_id")
    transfer_in = candidate.get("transfer_in_id")
    if decision == "TRANSFER":
        outgoing, incoming = str(transfer_out), str(transfer_in)
        if outgoing not in squad or incoming in squad or not incoming:
            raise CandidateFieldComparisonError("frozen transfer identity is inconsistent")
        if outgoing == reserve_gk:
            raise CandidateFieldComparisonError("reserve goalkeeper replacement is outside this product")
        if outgoing == captain:
            raise CandidateFieldComparisonError("captain replacement requires an explicit captain decision")
        proposed_squad[proposed_squad.index(outgoing)] = incoming
        if outgoing in proposed_starting:
            proposed_starting[proposed_starting.index(outgoing)] = incoming
        elif outgoing in proposed_bench:
            proposed_bench[proposed_bench.index(outgoing)] = incoming
        else:
            raise CandidateFieldComparisonError("outgoing player has no recognized squad slot")
    elif decision != "HOLD":
        raise CandidateFieldComparisonError("action must be HOLD or TRANSFER")

    field_rows = binding.get("field_eo_rows")
    if not isinstance(field_rows, list) or not field_rows:
        raise CandidateFieldComparisonError("field EO rows are required")
    field_by_id = {}
    for row in field_rows:
        player_id = str(row.get("fpl_element_id", ""))
        if not player_id or player_id in field_by_id:
            raise CandidateFieldComparisonError("field EO rows contain missing or duplicate player IDs")
        field_by_id[player_id] = row

    if not set(squad) | set(proposed_squad) <= set(field_by_id):
        missing = sorted((set(squad) | set(proposed_squad)) - set(field_by_id))
        raise CandidateFieldComparisonError("field EO missing candidate players: " + ", ".join(missing))

    def scenario(name: str, owned: list[str], xi: list[str], bench_ids: list[str]) -> dict[str, Any]:
        rows = []
        for player_id in sorted(set(owned) | set(field_by_id), key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x)):
            field = field_by_id[player_id]
            is_owned = player_id in owned
            personal_eo = (100.0 if is_owned else 0.0) + (100.0 if is_owned and player_id == captain else 0.0)
            personal_starting = 100.0 if player_id in xi else 0.0
            field_eo = _pct(field, "effective_ownership_pct")
            field_starting = _pct(field, "starting_pct")
            rows.append({
                "fpl_element_id": player_id,
                "in_squad": is_owned,
                "in_starting_xi": player_id in xi,
                "in_outfield_bench": player_id in bench_ids,
                "is_captain": is_owned and player_id == captain,
                "personal_effective_ownership_pct": personal_eo,
                "field_effective_ownership_pct": field_eo,
                "effective_ownership_delta_pct": round(personal_eo - field_eo, 8) if field_eo is not None else None,
                "personal_starting_exposure_pct": personal_starting,
                "field_starting_pct": field_starting,
                "starting_exposure_delta_pct": round(personal_starting - field_starting, 8) if field_starting is not None else None,
            })
        owned_rows = [row for row in rows if row["in_squad"]]
        eo_gaps = [row["effective_ownership_delta_pct"] for row in owned_rows if row["effective_ownership_delta_pct"] is not None]
        starting_gaps = [row["starting_exposure_delta_pct"] for row in owned_rows if row["starting_exposure_delta_pct"] is not None]
        return {
            "scenario": name,
            "squad_player_count": len(owned),
            "starting_xi_count": len(xi),
            "captain_id": captain,
            "portfolio_eo_gap_sum_pct_points": round(sum(eo_gaps), 8) if len(eo_gaps) == len(owned_rows) else None,
            "starting_exposure_gap_sum_pct_points": round(sum(starting_gaps), 8) if len(starting_gaps) == len(owned_rows) else None,
            "players": rows,
        }

    hold = scenario("HOLD", squad, starting, bench)
    proposed = scenario(decision, proposed_squad, proposed_starting, proposed_bench)
    hold_by_id = {row["fpl_element_id"]: row for row in hold["players"]}
    proposed_by_id = {row["fpl_element_id"]: row for row in proposed["players"]}
    changes = []
    for player_id in sorted(set(hold_by_id) | set(proposed_by_id), key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x)):
        before = hold_by_id.get(player_id)
        after = proposed_by_id.get(player_id)
        before_eo = before["personal_effective_ownership_pct"] if before else 0.0
        after_eo = after["personal_effective_ownership_pct"] if after else 0.0
        before_start = before["personal_starting_exposure_pct"] if before else 0.0
        after_start = after["personal_starting_exposure_pct"] if after else 0.0
        if before_eo != after_eo or before_start != after_start:
            changes.append({
                "fpl_element_id": player_id,
                "personal_eo_change_pct_points": after_eo - before_eo,
                "personal_starting_exposure_change_pct_points": after_start - before_start,
                "field_effective_ownership_pct": (after or before)["field_effective_ownership_pct"],
            })

    return {
        "status": "PASS_FROZEN_CANDIDATE_FIELD_EXPOSURE_COMPARISON",
        "contract_version": binding["contract_version"],
        "snapshot_id": binding["snapshot_id"],
        "season": binding["season"],
        "target_gameweek": binding["target_gameweek"],
        "manager_team_id": candidate.get("manager_team_id"),
        "decision_sha256": candidate.get("decision_sha256"),
        "field_cohort": binding["cohort"],
        "field_sample": binding["sample"],
        "field_scope": binding["field_scope"],
        "hold": hold,
        "frozen_candidate": proposed,
        "decision_exposure_changes": changes,
        "interpretation": (
            "Portfolio gaps are sums of player-level percentage-point exposure differences within the named squad; "
            "they are not points, rank predictions, or utility. Review player-level rows and cohort/sample context."
        ),
        "expected_points": "NOT_COMBINED_WITH_EO",
        "covar": "DISABLED",
        "release_eligible": False,
    }
