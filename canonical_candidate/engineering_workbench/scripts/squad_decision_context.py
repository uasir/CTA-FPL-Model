"""Fail-closed attachment of field-relative and CoVar evidence to squad decisions.

This is an evidence adapter: it never changes the canonical EV recommendation.
Artifacts must bind to the exact provider snapshot, model, Gameweek and candidate set.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping


class SquadDecisionContextError(ValueError):
    """Evidence cannot be joined safely to the personal-squad decision."""


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise SquadDecisionContextError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SquadDecisionContextError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise SquadDecisionContextError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise SquadDecisionContextError(f"{field} must be a finite number")
    return float(value)


def _candidate_keys(recommendation: Mapping[str, Any]) -> list[tuple[str, int | None, int | None]]:
    transfer = recommendation.get("transfer_recommendation")
    if not isinstance(transfer, Mapping) or not isinstance(transfer.get("alternatives"), list):
        raise SquadDecisionContextError("recommendation has no canonical transfer alternatives")
    keys = [("HOLD", None, None)]
    for row in transfer["alternatives"]:
        if not isinstance(row, Mapping):
            raise SquadDecisionContextError("transfer alternatives must be objects")
        out_id, in_id = row.get("transfer_out_id"), row.get("transfer_in_id")
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in (out_id, in_id)):
            raise SquadDecisionContextError("transfer candidate IDs must be positive integers")
        keys.append(("TRANSFER", out_id, in_id))
    if len(set(keys)) != len(keys):
        raise SquadDecisionContextError("duplicate candidate identity in recommendation")
    return keys


def _validate_common(artifact: Mapping[str, Any], *, recommendation: Mapping[str, Any],
                     target_gameweek: int, as_of_utc: str, deadline_utc: str, label: str) -> None:
    if not isinstance(artifact, Mapping):
        raise SquadDecisionContextError(f"{label} artifact must be an object")
    for field, expected in (
        ("forecast_snapshot_id", recommendation.get("forecast_snapshot_id")),
        ("model_version", recommendation.get("model_version")),
        ("target_gameweek", target_gameweek),
    ):
        if artifact.get(field) != expected:
            raise SquadDecisionContextError(f"{label} {field} does not match decision")
    if not isinstance(artifact.get("artifact_id"), str) or not artifact["artifact_id"].strip():
        raise SquadDecisionContextError(f"{label} artifact_id is required")
    captured = _timestamp(artifact.get("captured_at_utc"), f"{label}.captured_at_utc")
    as_of = _timestamp(as_of_utc, "as_of_utc")
    deadline = _timestamp(deadline_utc, "deadline_utc")
    if captured > as_of:
        raise SquadDecisionContextError(f"{label} capture is later than decision as_of_utc")
    if captured >= deadline or as_of >= deadline:
        raise SquadDecisionContextError(f"{label} and decision must be strictly pre-deadline")


def _candidate_metrics(artifact: Mapping[str, Any], expected_keys: list[tuple[str, int | None, int | None]],
                       fields: tuple[str, ...], label: str) -> list[dict[str, Any]]:
    rows = artifact.get("candidate_metrics")
    if not isinstance(rows, list):
        raise SquadDecisionContextError(f"{label}.candidate_metrics must be a list")
    by_key = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise SquadDecisionContextError(f"{label} candidate metric must be an object")
        key = (row.get("candidate_type"), row.get("transfer_out_id"), row.get("transfer_in_id"))
        if key not in expected_keys:
            raise SquadDecisionContextError(f"{label} contains an unknown candidate {key}")
        if key in by_key:
            raise SquadDecisionContextError(f"{label} contains duplicate candidate {key}")
        metric = {"candidate_type": key[0], "transfer_out_id": key[1], "transfer_in_id": key[2]}
        for field in fields:
            metric[field] = _finite(row.get(field), f"{label}.{field}")
        by_key[key] = metric
    missing = set(expected_keys) - set(by_key)
    if missing:
        raise SquadDecisionContextError(f"{label} is missing {len(missing)} candidate metric(s)")
    return [by_key[key] for key in expected_keys]


def attach_squad_decision_context(*, recommendation: Mapping[str, Any],
                                  field_relative_context: Mapping[str, Any] | None,
                                  covar_context: Mapping[str, Any] | None,
                                  target_gameweek: int, as_of_utc: str,
                                  deadline_utc: str) -> dict[str, Any]:
    """Attach optional contextual evidence; preserve all decision fields exactly."""
    if not isinstance(recommendation, Mapping) or recommendation.get("system") != "personal_squad":
        raise SquadDecisionContextError("context attachment is restricted to personal_squad recommendations")
    keys = _candidate_keys(recommendation)
    result = dict(recommendation)

    if field_relative_context is not None:
        field = field_relative_context
        _validate_common(field, recommendation=recommendation, target_gameweek=target_gameweek,
                         as_of_utc=as_of_utc, deadline_utc=deadline_utc, label="field_relative")
        if field.get("source_type") not in {"OBSERVED_EO", "POLL_IMPLIED_ESTIMATE", "FIELD_SAMPLE"}:
            raise SquadDecisionContextError("field_relative source_type is not recognized")
        sample_size = field.get("sample_size")
        if isinstance(sample_size, bool) or not isinstance(sample_size, int) or sample_size < 1:
            raise SquadDecisionContextError("field_relative sample_size must be a positive integer")
        coverage = _finite(field.get("coverage_fraction"), "field_relative.coverage_fraction")
        if not 0 <= coverage <= 1:
            raise SquadDecisionContextError("field_relative coverage_fraction must be between 0 and 1")
        if field.get("missingness_reported") is not True:
            raise SquadDecisionContextError("field_relative missingness must be explicitly reported")
        metrics = _candidate_metrics(
            field, keys,
            ("field_relative_expected_points_delta", "field_relative_upside_delta"),
            "field_relative",
        )
        result["field_relative_context"] = {
            "status": "ATTACHED_CONTEXT_ONLY",
            "artifact_id": field["artifact_id"],
            "source_type": field["source_type"],
            "sample_size": sample_size,
            "coverage_fraction": coverage,
            "missingness_reported": True,
            "uncertainty_note": field.get("uncertainty_note"),
            "candidate_metrics": metrics,
        }

    if covar_context is not None:
        covar = covar_context
        _validate_common(covar, recommendation=recommendation, target_gameweek=target_gameweek,
                         as_of_utc=as_of_utc, deadline_utc=deadline_utc, label="covar")
        if covar.get("decision_weight") != 0 or covar.get("production_eligible") is not False:
            raise SquadDecisionContextError("CoVar must remain research-only with zero decision weight")
        if covar.get("marginal_eo_used_to_reconstruct_joint_portfolios") is not False:
            raise SquadDecisionContextError("marginal EO cannot reconstruct joint manager portfolios")
        if covar.get("method") not in {"HISTORICAL_PLAYER_COVARIANCE_PROXY", "SAMPLED_JOINT_MANAGER_SCENARIOS"}:
            raise SquadDecisionContextError("CoVar method is not recognized")
        metrics = _candidate_metrics(
            covar, keys,
            ("candidate_variance", "field_variance", "field_relative_upside_delta",
             "portfolio_covariance_delta"),
            "covar",
        )
        if any(row["candidate_variance"] < 0 or row["field_variance"] < 0 for row in metrics):
            raise SquadDecisionContextError("CoVar variance metrics must be non-negative")
        result["covar_research_context"] = {
            "status": "ATTACHED_RESEARCH_ONLY",
            "artifact_id": covar["artifact_id"],
            "method": covar["method"],
            "decision_weight": 0.0,
            "production_eligible": False,
            "ranking_changed": False,
            "transfer_action_changed": False,
            "starting_xi_changed": False,
            "captaincy_changed": False,
            "candidate_metrics": metrics,
        }
    return result
