#!/usr/bin/env python3
"""Compose private field portfolios, candidate lineups and outcomes into a full-GW document."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from m4_covar_full_gameweek_contract import validate_full_gameweek_document


class CovarFullGameweekBuildError(ValueError):
    """Raised when candidate, field and scenario inputs cannot be composed safely."""


_FORBIDDEN_FIELD_KEYS = {
    "entry_id", "manager_id", "manager_name", "manager_entry_id",
    "exact_rank", "overall_rank", "rank",
}


def _assert_no_manager_identifiers(value: Any, path: str = "field_portfolios") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in _FORBIDDEN_FIELD_KEYS:
                raise CovarFullGameweekBuildError(
                    f"field portfolio input contains restricted manager identifier field: {path}.{key}"
                )
            _assert_no_manager_identifiers(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _assert_no_manager_identifiers(nested, f"{path}[{index}]")


def build_full_gameweek_document(
    *,
    season: str,
    target_gameweek: int,
    deadline_utc: str,
    as_of_utc: str,
    scenarios: Sequence[Mapping[str, Any]],
    candidate_portfolios: Sequence[Mapping[str, Any]],
    field_adaptation: Mapping[str, Any] | None = None,
    mode: str = "REGULAR_GW",
    scenario_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose and validate one complete synthetic full-Gameweek input document.

    Field adaptation must be the private output of the existing manager-pick
    adapter. The builder never reads raw manager IDs or reconstructs portfolios
    from marginal EO.
    """
    if not season or isinstance(target_gameweek, bool) or int(target_gameweek) < 1:
        raise CovarFullGameweekBuildError("season and positive target_gameweek are required")
    if mode not in ("REGULAR_GW", "FREE_HIT"):
        raise CovarFullGameweekBuildError("mode must be REGULAR_GW or explicitly FREE_HIT")
    if not isinstance(candidate_portfolios, Sequence) or not candidate_portfolios:
        raise CovarFullGameweekBuildError("at least one candidate portfolio is required")
    if not isinstance(scenarios, Sequence) or not scenarios:
        raise CovarFullGameweekBuildError("at least one full-Gameweek scenario is required")

    data_status = "SYNTHETIC_FULL_GAMEWEEK_ONLY"
    research_metadata: dict[str, Any] = {}
    if scenario_provenance is not None:
        if not isinstance(scenario_provenance, Mapping):
            raise CovarFullGameweekBuildError("scenario_provenance must be an object")
        if scenario_provenance.get("dataset_type") != "M4_COVAR_PLAYER_GAMEWEEK_RESIDUAL_BOOTSTRAP_RESEARCH_ONLY":
            raise CovarFullGameweekBuildError("unsupported research scenario provenance")
        if scenario_provenance.get("season") != season or scenario_provenance.get("target_gameweek") != int(target_gameweek):
            raise CovarFullGameweekBuildError("residual scenario season or Gameweek differs from requested full-Gameweek document")
        if scenario_provenance.get("probability_calibrated") is not False:
            raise CovarFullGameweekBuildError("residual bootstrap probabilities must remain uncalibrated")
        if scenario_provenance.get("decision_weight") != 0.0 or scenario_provenance.get("production_eligible") is not False or scenario_provenance.get("covar_used") is not False:
            raise CovarFullGameweekBuildError("residual scenarios must remain research-only and disabled")
        provenance_scenarios = scenario_provenance.get("scenarios")
        if not isinstance(provenance_scenarios, list) or list(scenarios) != provenance_scenarios:
            raise CovarFullGameweekBuildError("scenarios must be the exact residual-bootstrap scenario rows")
        required = ("forecast_snapshot_id", "model_version", "training_cutoff_utc",
                    "scenario_probability_method", "complete_historical_gameweeks")
        if any(not scenario_provenance.get(key) for key in required):
            raise CovarFullGameweekBuildError("residual scenario provenance is incomplete")
        data_status = "RESEARCH_RESIDUAL_BLOCK_BOOTSTRAP_ONLY"
        research_metadata = {
            "forecast_snapshot_id": scenario_provenance["forecast_snapshot_id"],
            "model_version": scenario_provenance["model_version"],
            "training_cutoff_utc": scenario_provenance["training_cutoff_utc"],
            "scenario_probability_method": scenario_provenance["scenario_probability_method"],
            "complete_historical_gameweeks": scenario_provenance["complete_historical_gameweeks"],
            "probability_calibrated": False,
            "marginal_expected_points_preserved": scenario_provenance.get("marginal_expected_points_preserved"),
            "minutes_mean_preserved": scenario_provenance.get("minutes_mean_preserved"),
            "residual_bootstrap_payload_sha256": scenario_provenance.get("payload_sha256"),
        }

    portfolios: list[dict[str, Any]] = []
    for source in candidate_portfolios:
        if not isinstance(source, Mapping):
            raise CovarFullGameweekBuildError("each candidate portfolio must be an object")
        if source.get("portfolio_role", "CANDIDATE") != "CANDIDATE":
            raise CovarFullGameweekBuildError("candidate_portfolios may contain only CANDIDATE rows")
        row = dict(source)
        row["portfolio_role"] = "CANDIDATE"
        portfolios.append(row)

    field_metadata: Mapping[str, Any] | None = None
    if field_adaptation is not None:
        if not isinstance(field_adaptation, Mapping):
            raise CovarFullGameweekBuildError("field_adaptation must be an object")
        field_metadata = field_adaptation.get("metadata")
        field_rows = field_adaptation.get("portfolios")
        if not isinstance(field_metadata, Mapping) or not isinstance(field_rows, list) or not field_rows:
            raise CovarFullGameweekBuildError("field adaptation metadata and portfolios are required")
        if field_metadata.get("manager_entry_ids_retained") is not False:
            raise CovarFullGameweekBuildError("field adaptation must confirm manager entry IDs were discarded")
        if field_metadata.get("evidence_role") != "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE":
            raise CovarFullGameweekBuildError("field adaptation must be pre-deadline provisional evidence")
        if int(field_metadata.get("gameweek", -1)) != int(target_gameweek):
            raise CovarFullGameweekBuildError("field adaptation Gameweek mismatch")
        try:
            field_deadline = datetime.fromisoformat(str(field_metadata.get("deadline_utc", "")).replace("Z", "+00:00"))
            requested_deadline = datetime.fromisoformat(str(deadline_utc).replace("Z", "+00:00"))
        except ValueError as exc:
            raise CovarFullGameweekBuildError("deadline_utc values must be ISO-8601") from exc
        if field_deadline != requested_deadline:
            raise CovarFullGameweekBuildError("field adaptation deadline mismatch")
        if not str(field_metadata.get("as_of_utc", "")):
            raise CovarFullGameweekBuildError("field adaptation as_of_utc is required")
        if str(field_metadata["as_of_utc"]) != str(as_of_utc):
            raise CovarFullGameweekBuildError("field adaptation as_of_utc mismatch")
        _assert_no_manager_identifiers(field_rows)
        for source in field_rows:
            if not isinstance(source, Mapping) or source.get("portfolio_role") != "FIELD":
                raise CovarFullGameweekBuildError("adapted field rows must be labelled FIELD")
            row = dict(source)
            row.pop("rank_stratum", None)
            portfolios.append(row)

    players_by_id: dict[str, dict[str, Any]] = {}
    for portfolio in portfolios:
        positions = portfolio.get("player_positions")
        player_ids = portfolio.get("player_ids")
        if not isinstance(positions, Mapping) or not isinstance(player_ids, list):
            raise CovarFullGameweekBuildError("every portfolio requires player_ids and player_positions")
        for player_id in player_ids:
            pid = str(player_id)
            position = str(positions.get(pid, "")).upper()
            if not position:
                raise CovarFullGameweekBuildError(f"portfolio lacks position for player {pid}")
            existing = players_by_id.get(pid)
            if existing is not None and existing["position"] != position:
                raise CovarFullGameweekBuildError(f"conflicting position metadata for player {pid}")
            players_by_id[pid] = {"player_id": pid, "position": position}

    document = {
        "schema_version": "1.0.0",
        "data_status": data_status,
        "scenario_scope": "FULL_GAMEWEEK",
        "mode": mode,
        "metadata": {
            "season": season,
            "target_gameweek": int(target_gameweek),
            "deadline_utc": deadline_utc,
            "as_of_utc": as_of_utc,
            "field_evidence_role": (
                field_metadata.get("evidence_role") if field_metadata is not None else None
            ),
            "field_cohort": field_metadata.get("cohort") if field_metadata is not None else None,
            "field_manager_count": (
                field_metadata.get("selected_manager_count") if field_metadata is not None else 0
            ),
            "manager_entry_ids_retained": False,
            **research_metadata,
        },
        "players": list(players_by_id.values()),
        "scenarios": [dict(row) for row in scenarios],
        "portfolios": portfolios,
        "production_eligible": False,
        "decision_weight": 0.0,
        "covar_used": False,
    }
    try:
        validate_full_gameweek_document(document)
    except (TypeError, ValueError) as exc:
        raise CovarFullGameweekBuildError(f"composed full-Gameweek document failed validation: {exc}") from exc
    document["validation_status"] = validate_full_gameweek_document(document)["validation_status"]
    document["production_eligible"] = False
    document["decision_weight"] = 0.0
    document["covar_used"] = False
    return document
