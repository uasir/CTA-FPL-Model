"""Assemble the M4 CoVar research-validation evidence without overstating it.

This is a report assembler only. It does not estimate probabilities, create
joint scenarios, fit dependence, or certify historical calibration.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


class CovarResearchValidationReportError(ValueError):
    """Evidence inputs cannot support a coherent CoVar research report."""


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CovarResearchValidationReportError(f"{field} must be an object")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CovarResearchValidationReportError(f"{field} must be a non-negative integer")
    return value


def build_covar_research_validation_report(
    *,
    anchor_acceptance: Mapping[str, Any],
    scenario_alignment: Mapping[str, Any],
    realized_dataset_report: Mapping[str, Any],
    finality_audits: Sequence[Mapping[str, Any]],
    joint_calibration_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Join independently generated evidence reports and expose readiness limits.

    The realized dataset must be structurally accepted and every finished
    Gameweek in it must have an exact official event-live finality audit.
    Historical joint calibration is reported as supplied; this assembler
    does not validate the forecast archives or observed state construction.
    """
    anchor = _require_mapping(anchor_acceptance, "anchor_acceptance")
    alignment = _require_mapping(scenario_alignment, "scenario_alignment")
    realized = _require_mapping(realized_dataset_report, "realized_dataset_report")
    calibration = _require_mapping(joint_calibration_report, "joint_calibration_report")

    if anchor.get("acceptance_status") != "ACCEPTED_PLAYER_LEVEL_FORECAST_ANCHOR_ONLY":
        raise CovarResearchValidationReportError("M3 player-level forecast anchor has not been accepted")
    if anchor.get("joint_distribution_available") is not False or anchor.get("joint_probabilities_inferred") is not False:
        raise CovarResearchValidationReportError("M3 anchor must not be represented as a joint distribution")
    if alignment.get("alignment_status") != "PASS_EXPLICIT_SCENARIO_MARGINAL_ALIGNMENT_COMPUTED":
        raise CovarResearchValidationReportError("explicit joint-scenario marginal alignment is not complete")
    if alignment.get("calibration_established") is not False:
        raise CovarResearchValidationReportError("marginal alignment cannot claim calibration")
    if alignment.get("joint_distribution_was_inferred") is not False:
        raise CovarResearchValidationReportError("joint distribution inference is not permitted")
    if alignment.get("fixture_independence_assumed") is not False:
        raise CovarResearchValidationReportError("fixture independence assumption is not permitted")

    season = anchor.get("season")
    gameweek = anchor.get("target_gameweek")
    if not isinstance(season, str) or not season.strip():
        raise CovarResearchValidationReportError("anchor season is required")
    _nonnegative_int(gameweek, "anchor target_gameweek")
    if gameweek < 1:
        raise CovarResearchValidationReportError("anchor target_gameweek must be positive")
    for label, report in (("scenario alignment", alignment),):
        if report.get("season") != season or report.get("target_gameweek") != gameweek:
            raise CovarResearchValidationReportError(f"{label} does not match the M3 anchor season/Gameweek")
    if alignment.get("forecast_snapshot_id") != anchor.get("forecast_snapshot_id"):
        raise CovarResearchValidationReportError("scenario alignment forecast snapshot does not match M3 anchor")

    if realized.get("status") != "PASS_STRUCTURAL_ONLY" or realized.get("season") != season:
        raise CovarResearchValidationReportError("realized dataset must be structurally accepted for the same season")
    if realized.get("point_in_time_status") != "NOT_VERIFIED_RETROSPECTIVE_OFFICIAL_API_HISTORY":
        raise CovarResearchValidationReportError("realized dataset temporal status is not the declared retrospective status")
    finished_gws = realized.get("finished_gameweeks")
    if not isinstance(finished_gws, list) or not finished_gws:
        raise CovarResearchValidationReportError("realized dataset finished_gameweeks must be a non-empty list")
    normalized_gws = set()
    for value in finished_gws:
        gw = _nonnegative_int(value, "finished_gameweeks entry")
        if gw < 1 or gw in normalized_gws:
            raise CovarResearchValidationReportError("finished_gameweeks must contain unique positive integers")
        normalized_gws.add(gw)

    if not isinstance(finality_audits, Sequence) or isinstance(finality_audits, (str, bytes)) or not finality_audits:
        raise CovarResearchValidationReportError("finality_audits must be a non-empty list")
    audited_gws = set()
    for audit in finality_audits:
        audit = _require_mapping(audit, "finality audit")
        if audit.get("season") != season:
            raise CovarResearchValidationReportError("finality audit season mismatch")
        if audit.get("status") != "PASS_EXACT_MATCH" or audit.get("finality_reconciled") is not True:
            raise CovarResearchValidationReportError("every supplied finality audit must pass exact reconciliation")
        event_id = audit.get("event_id")
        _nonnegative_int(event_id, "finality audit event_id")
        if event_id < 1 or event_id in audited_gws:
            raise CovarResearchValidationReportError("finality audits must have unique positive event IDs")
        if audit.get("point_in_time_status") != "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT":
            raise CovarResearchValidationReportError("finality audit must retain its retrospective temporal limitation")
        audited_gws.add(event_id)
    missing_finality = sorted(normalized_gws - audited_gws)
    if missing_finality:
        raise CovarResearchValidationReportError(
            f"realized dataset Gameweeks lack exact finality audits: {missing_finality}"
        )

    if calibration.get("evaluation_status") != "HISTORICAL_BACKTEST_ONLY":
        raise CovarResearchValidationReportError("joint calibration report must be a historical backtest")
    forecast_count = _nonnegative_int(calibration.get("forecast_count"), "calibration forecast_count")
    calibration_gws = _nonnegative_int(calibration.get("gameweek_count"), "calibration gameweek_count")
    if forecast_count < 1 or calibration_gws < 1 or calibration_gws > len(normalized_gws):
        raise CovarResearchValidationReportError("calibration report counts are invalid or exceed realized Gameweek coverage")
    calibration_by_gw = calibration.get("by_gameweek")
    if not isinstance(calibration_by_gw, Mapping) or len(calibration_by_gw) != calibration_gws:
        raise CovarResearchValidationReportError("calibration by_gameweek rows do not match gameweek_count")
    for gw_key, row in calibration_by_gw.items():
        try:
            gw = int(str(gw_key))
        except ValueError as exc:
            raise CovarResearchValidationReportError("calibration Gameweek keys must be integers") from exc
        if gw not in normalized_gws or not isinstance(row, Mapping):
            raise CovarResearchValidationReportError("calibration includes a Gameweek outside the reconciled realized dataset")
        if _nonnegative_int(row.get("forecast_count"), f"calibration GW{gw} forecast_count") < 1:
            raise CovarResearchValidationReportError(f"calibration GW{gw} has no forecast rows")

    independent_clusters = calibration_gws
    cluster_summary = calibration.get("gameweek_cluster_confidence_intervals")
    if isinstance(cluster_summary, Mapping):
        independent_clusters = _nonnegative_int(
            cluster_summary.get("independent_clusters", calibration_gws),
            "independent Gameweek clusters",
        )
    readiness = (
        "LIMITED_HISTORICAL_EVIDENCE_FEW_INDEPENDENT_GAMEWEEKS"
        if independent_clusters < 20
        else "HISTORICAL_BACKTEST_EVIDENCE_ASSEMBLED_REQUIRES_MODEL_REVIEW"
    )
    return {
        "schema_version": "1.0.0",
        "report_type": "M4_COVAR_UNIFIED_RESEARCH_VALIDATION",
        "report_status": "EVIDENCE_ASSEMBLED_WITH_EXPLICIT_LIMITATIONS",
        "season": season,
        "m3_anchor": {
            "forecast_snapshot_id": anchor.get("forecast_snapshot_id"),
            "target_gameweek": gameweek,
            "acceptance_status": anchor["acceptance_status"],
            "player_forecast_count": _nonnegative_int(anchor.get("player_forecast_count"), "anchor player_forecast_count"),
            "joint_distribution_available": False,
        },
        "scenario_alignment": {
            "status": alignment["alignment_status"],
            "scenario_source_id": alignment.get("scenario_source_id"),
            "scenario_count": _nonnegative_int(alignment.get("scenario_count"), "alignment scenario_count"),
            "player_count": _nonnegative_int(alignment.get("player_count"), "alignment player_count"),
            "mae": alignment.get("mean_absolute_error"),
            "rmse": alignment.get("root_mean_squared_error"),
            "mean_bias": alignment.get("mean_bias_scenario_minus_m3"),
            "maximum_absolute_error": alignment.get("maximum_absolute_error"),
            "interpretation": "MARGINAL_MEAN_CONSISTENCY_ONLY_NOT_JOINT_CALIBRATION",
        },
        "realized_outcomes": {
            "dataset_status": realized["status"],
            "point_in_time_status": realized["point_in_time_status"],
            "finished_gameweeks": sorted(normalized_gws),
            "player_fixture_rows": _nonnegative_int(realized.get("fixture_rows"), "realized fixture_rows"),
            "player_gameweek_rows": _nonnegative_int(realized.get("player_gameweek_rows"), "realized player_gameweek_rows"),
            "missing_player_fixture_rows_zero_filled": _nonnegative_int(
                realized.get("missing_player_fixture_rows_zero_filled"),
                "missing_player_fixture_rows_zero_filled",
            ),
            "finality_audited_gameweeks": sorted(audited_gws),
            "finality_audit_count": len(finality_audits),
            "temporal_interpretation": "RETROSPECTIVE_OFFICIAL_SCORING_RECONCILIATION_NOT_POINT_IN_TIME_FORECAST_FEATURES",
        },
        "joint_probability_calibration": {
            "evaluation_status": calibration["evaluation_status"],
            "forecast_count": forecast_count,
            "gameweek_count": calibration_gws,
            "independent_gameweek_clusters": independent_clusters,
            "mean_model_brier_score": calibration.get("mean_model_brier_score"),
            "mean_reference_brier_score": calibration.get("mean_reference_brier_score"),
            "brier_skill_score_vs_reference": calibration.get("brier_skill_score_vs_reference"),
            "mean_model_log_loss": calibration.get("mean_model_log_loss"),
            "confidence_intervals": cluster_summary.get("intervals") if isinstance(cluster_summary, Mapping) else None,
            "readiness": readiness,
        },
        "statistical_boundaries": {
            "m3_expected_points_used_as_joint_probabilities": False,
            "joint_probabilities_inferred_from_marginals": False,
            "fixture_independence_assumed": False,
            "marginal_alignment_claims_joint_calibration": False,
            "retrospective_outcomes_claimed_as_point_in_time_features": False,
            "predictive_validity_established": False,
        },
        "decision_weight": 0.0,
        "production_eligible": False,
        "recommendations_changed": False,
        "transfers_changed": False,
        "starting_xi_changed": False,
        "captaincy_changed": False,
        "limitations": [
            "M3 is a conventional player-level expected-points anchor, not a joint Gameweek probability distribution.",
            "Scenario marginal alignment is a consistency diagnostic only and does not validate dependence, tails, or portfolio outcomes.",
            "Retrospective official event-live reconciliation validates supplied realized rows against captured scoring responses, not original point-in-time availability.",
            "Historical calibration quality is only as trustworthy as the separately archived joint forecasts, state catalogue, observed-state mapping, and reference forecast provenance.",
            "Fewer than 20 independent Gameweek clusters are flagged as limited evidence; this is a caution threshold, not a universal sample-size sufficiency rule.",
        ],
    }
