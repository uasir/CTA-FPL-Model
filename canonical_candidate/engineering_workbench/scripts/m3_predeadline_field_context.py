#!/usr/bin/env python3
"""Build provisional field-exposure context for the M3 personal-squad output.

Consumes the private output of capture_predeadline_field_eo.py. It does not
estimate EO, reconstruct manager portfolios, alter EV, or make release decisions.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class PredeadlineFieldContextError(ValueError):
    pass


REQUIRED_COLUMNS = {
    "gameweek", "fpl_element_id", "sample_managers", "sample_weight",
    "owned_by_pct", "starting_pct", "captain_pct", "triple_captain_pct",
    "effective_ownership_pct", "scoring_exposure_pct",
    "effective_ownership_pct_ci95_low", "effective_ownership_pct_ci95_high",
}
METRICS = (
    "owned_by_pct", "effective_ownership_pct", "starting_pct",
    "captain_pct", "triple_captain_pct", "scoring_exposure_pct",
    "effective_ownership_pct_ci95_low", "effective_ownership_pct_ci95_high",
)


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise PredeadlineFieldContextError(f"{label} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PredeadlineFieldContextError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PredeadlineFieldContextError(f"{label} must include timezone")
    return parsed.astimezone(timezone.utc)


def _number(value: Any, label: str) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise PredeadlineFieldContextError(f"{label} must be numeric or blank")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PredeadlineFieldContextError(f"{label} must be numeric or blank") from exc
    if not math.isfinite(number) or number < 0:
        raise PredeadlineFieldContextError(f"{label} must be finite and non-negative")
    return number


def load_predeadline_field_csv(csv_path: str | Path, report_path: str | Path,
                               *, season: str, source_url: str) -> dict[str, Any]:
    """Load and verify the actual CSV/report pair emitted by the capture script."""
    csv_path, report_path = Path(csv_path), Path(report_path)
    raw = csv_path.read_bytes()
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PredeadlineFieldContextError("field capture report is missing or invalid") from exc
    if report.get("status") != "CAPTURED_PRE_DEADLINE_CURRENT_PICKS":
        raise PredeadlineFieldContextError("field artifact is not a successful pre-deadline capture")
    if report.get("evidence_role") != "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE":
        raise PredeadlineFieldContextError("field artifact has the wrong evidence role")
    if report.get("picks_lock_verified") is not False or report.get("provisional_picks") is not True:
        raise PredeadlineFieldContextError("field artifact must be explicitly provisional and not lock-verified")
    if not season.strip() or not source_url.strip():
        raise PredeadlineFieldContextError("season and source_url are required")
    deadline = _time(report.get("deadline_time_utc"), "deadline_time_utc")
    cohort_at = _time(report.get("rank_cohort_captured_at_utc"), "rank_cohort_captured_at_utc")
    captured_at = _time(report.get("picks_captured_at_utc"), "picks_captured_at_utc")
    started_at = _time(report.get("capture_started_at_utc"), "capture_started_at_utc")
    if not started_at <= cohort_at <= captured_at < deadline:
        raise PredeadlineFieldContextError("cohort and picks capture must be ordered and strictly pre-deadline")
    digest = hashlib.sha256(raw).hexdigest()
    if report.get("csv_sha256") != digest:
        raise PredeadlineFieldContextError("field CSV SHA-256 does not match capture report")
    manager_count = report.get("sample_managers")
    if isinstance(manager_count, bool) or not isinstance(manager_count, int) or manager_count < 1:
        raise PredeadlineFieldContextError("sample_managers must be a positive integer")
    if report.get("sample_size_captured") != manager_count:
        raise PredeadlineFieldContextError("captured manager count does not match report")
    effective_n = _number(report.get("effective_sample_size"), "effective_sample_size")
    if effective_n is None or not 0 < effective_n <= manager_count:
        raise PredeadlineFieldContextError("effective sample size must be positive and no greater than sample size")
    rank_limit, rank_min, rank_max = (report.get("rank_limit"), report.get("rank_min"), report.get("rank_max"))
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (rank_limit, rank_min, rank_max)):
        raise PredeadlineFieldContextError("rank limit and observed bounds must be integers")
    if not 1 <= rank_min <= rank_max <= rank_limit:
        raise PredeadlineFieldContextError("observed rank bounds are inconsistent")
    try:
        reader = csv.DictReader(raw.decode("utf-8").splitlines())
    except UnicodeDecodeError as exc:
        raise PredeadlineFieldContextError("field CSV must be UTF-8") from exc
    if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
        raise PredeadlineFieldContextError("field CSV headers do not match the EO estimator contract")
    rows, seen = [], set()
    for line, row in enumerate(reader, start=2):
        player_id = str(row.get("fpl_element_id", "")).strip()
        if not player_id or player_id in seen:
            raise PredeadlineFieldContextError(f"CSV row {line} has missing or duplicate player ID")
        if str(row.get("gameweek")) != str(report.get("gameweek")):
            raise PredeadlineFieldContextError(f"CSV row {line} belongs to another Gameweek")
        if str(row.get("sample_managers")) != str(manager_count):
            raise PredeadlineFieldContextError(f"CSV row {line} sample count differs from report")
        seen.add(player_id)
        normalized = {"fpl_element_id": player_id, "gameweek": int(report["gameweek"])}
        for field in METRICS:
            normalized[field] = _number(row.get(field), f"{player_id}.{field}")
            if normalized[field] is not None and normalized[field] > 100:
                raise PredeadlineFieldContextError(f"{player_id}.{field} must not exceed 100 percent")
        low, high = normalized["effective_ownership_pct_ci95_low"], normalized["effective_ownership_pct_ci95_high"]
        if (low is None) != (high is None) or (low is not None and high < low):
            raise PredeadlineFieldContextError(f"{player_id} has an invalid effective-ownership interval")
        rows.append(normalized)
    if not rows:
        raise PredeadlineFieldContextError("field CSV contains no player rows")
    return {
        "snapshot_id": f"predeadline-gw{report['gameweek']}-{digest[:16]}",
        "season": season,
        "target_gameweek": int(report["gameweek"]),
        "deadline_utc": deadline.isoformat(),
        "captured_at_utc": captured_at.isoformat(),
        "cohort": {
            "name": str(report.get("cohort") or "unspecified"),
            "rank_min": rank_min, "rank_max": rank_max, "rank_limit": rank_limit,
            "rank_strata_count": report.get("rank_strata_count"),
        },
        "sample": {
            "manager_count": manager_count, "effective_sample_size": effective_n,
            "weighting": "equal_weighted_rank_stratified_sample",
            "sample_weight": report.get("sample_weight"),
        },
        "coverage": {"covered_player_ids": sorted(seen), "row_count": len(rows)},
        "source": {
            "source_url": source_url, "artifact_sha256": digest,
            "capture_report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        },
        "field_eo_rows": rows,
        "evidence_role": "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
        "picks_lock_verified": False,
        "provisional_picks": True,
        "release_eligible": False,
    }


def build_m3_predeadline_field_context(recommendation: Mapping[str, Any],
                                       manager_context: Mapping[str, Any],
                                       artifact: Mapping[str, Any], *,
                                       season: str, target_gameweek: int,
                                       as_of_utc: str, deadline_utc: str) -> dict[str, Any]:
    """Attach HOLD and selected-transfer exposure views to one M3 squad recommendation."""
    if not isinstance(recommendation, Mapping) or recommendation.get("system") != "personal_squad":
        raise PredeadlineFieldContextError("field context is restricted to personal-squad recommendations")
    if not isinstance(manager_context, Mapping) or not isinstance(artifact, Mapping):
        raise PredeadlineFieldContextError("manager context and field artifact must be objects")
    snapshot = artifact
    if snapshot.get("evidence_role") != "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE" or snapshot.get("release_eligible") is not False:
        raise PredeadlineFieldContextError("field artifact must remain provisional and non-release-eligible")
    if snapshot.get("picks_lock_verified") is not False or snapshot.get("provisional_picks") is not True:
        raise PredeadlineFieldContextError("field artifact must be explicitly provisional")
    if snapshot.get("season") != season or int(snapshot.get("target_gameweek", -1)) != int(target_gameweek):
        raise PredeadlineFieldContextError("field artifact season or Gameweek does not match M3 run")
    deadline, captured, as_of = (_time(deadline_utc, "deadline_utc"),
                                 _time(snapshot.get("captured_at_utc"), "captured_at_utc"),
                                 _time(as_of_utc, "as_of_utc"))
    if _time(snapshot.get("deadline_utc"), "field deadline") != deadline:
        raise PredeadlineFieldContextError("field artifact deadline does not match provider snapshot")
    if not captured < as_of < deadline:
        raise PredeadlineFieldContextError("field capture must precede M3 decision, strictly before deadline")
    source = snapshot.get("source")
    sample = snapshot.get("sample")
    coverage = snapshot.get("coverage")
    if not isinstance(source, Mapping) or not isinstance(sample, Mapping) or not isinstance(coverage, Mapping):
        raise PredeadlineFieldContextError("field provenance, sample and coverage metadata are required")
    digest = source.get("artifact_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
        raise PredeadlineFieldContextError("field CSV artifact SHA-256 is invalid")
    rows = snapshot.get("field_eo_rows")
    if not isinstance(rows, list) or not rows:
        raise PredeadlineFieldContextError("field EO rows are required")
    by_id = {}
    for row in rows:
        pid = str(row.get("fpl_element_id", ""))
        if not pid or pid in by_id or str(row.get("gameweek")) != str(target_gameweek):
            raise PredeadlineFieldContextError("field rows contain invalid, duplicate or wrong-GW player IDs")
        by_id[pid] = row
    if set(map(str, coverage.get("covered_player_ids", []))) != set(by_id):
        raise PredeadlineFieldContextError("field coverage does not match captured rows")
    if coverage.get("row_count") != len(rows):
        raise PredeadlineFieldContextError("field coverage row count does not match captured rows")
    squad_rows = manager_context.get("squad_snapshot")
    if not isinstance(squad_rows, list) or len(squad_rows) != 15:
        raise PredeadlineFieldContextError("manager squad_snapshot must contain 15 players")
    squad = [str(row["fpl_element_id"]) for row in squad_rows]
    if len(set(squad)) != 15:
        raise PredeadlineFieldContextError("manager squad contains duplicate player IDs")
    current_plan = recommendation.get("current_squad_plan")
    proposed_plan = recommendation.get("squad_plan")
    transfer = recommendation.get("transfer_recommendation")
    if not all(isinstance(x, Mapping) for x in (current_plan, proposed_plan, transfer)):
        raise PredeadlineFieldContextError("M3 current/proposed squad plans and transfer recommendation are required")
    action = transfer.get("action")
    best = transfer.get("best_candidate")
    if action not in {"HOLD", "TRANSFER"}:
        raise PredeadlineFieldContextError("M3 transfer action must be HOLD or TRANSFER")
    proposed_squad = list(squad)
    proposed_xi = list(map(str, current_plan.get("starting_xi", [])))
    proposed_bench = list(map(str, current_plan.get("bench_order", [])))
    if action == "TRANSFER":
        if not isinstance(best, Mapping):
            raise PredeadlineFieldContextError("selected transfer candidate is missing")
        outgoing, incoming = str(best.get("transfer_out_id")), str(best.get("transfer_in_id"))
        if outgoing not in proposed_squad or incoming in proposed_squad:
            raise PredeadlineFieldContextError("selected transfer identities are inconsistent with squad")
        if outgoing not in proposed_xi and outgoing not in proposed_bench:
            raise PredeadlineFieldContextError("outgoing player has no squad slot")
        # Use the engine's actual post-transfer XI/bench, including a possible
        # bench-to-starter displacement, rather than reconstructing the lineup.
        proposed_xi = list(map(str, proposed_plan.get("starting_xi", [])))
        proposed_bench = list(map(str, proposed_plan.get("bench_order", [])))
        proposed_squad[proposed_squad.index(outgoing)] = incoming
    current_xi = list(map(str, current_plan.get("starting_xi", [])))
    current_bench = list(map(str, current_plan.get("bench_order", [])))
    reserve_gk = str(current_plan.get("reserve_goalkeeper"))
    captain = str(current_plan.get("captain"))
    vice = str(current_plan.get("vice_captain"))
    proposed_captain = str(proposed_plan.get("captain"))
    proposed_vice = str(proposed_plan.get("vice_captain"))
    if len(current_xi) != 11 or len(current_bench) != 3 or reserve_gk not in squad:
        raise PredeadlineFieldContextError("current squad plan does not partition a valid 15-player squad")
    if set(current_xi) | set(current_bench) | {reserve_gk} != set(squad):
        raise PredeadlineFieldContextError("current squad plan does not partition the original squad")
    if set(proposed_xi) | set(proposed_bench) | {reserve_gk} != set(proposed_squad):
        raise PredeadlineFieldContextError("proposed squad plan does not partition the post-transfer squad")
    if captain not in current_xi or proposed_captain not in proposed_xi or proposed_vice not in proposed_xi:
        raise PredeadlineFieldContextError("captain and vice-captain must remain in the starting XI")
    required_ids = set(squad) | set(proposed_squad)
    missing = sorted(required_ids - set(by_id), key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))
    if missing:
        raise PredeadlineFieldContextError("field snapshot lacks candidate squad players: " + ", ".join(missing))

    active_chip_status = manager_context.get("active_chip_status", "NOT_CAPTURED")
    active_chip = manager_context.get("active_chip")
    if active_chip_status == "VERIFIED_FROM_OFFICIAL_PICKS":
        captain_multiplier = 3 if active_chip == "3xc" else 2
        captain_multiplier_status = "VERIFIED"
    else:
        captain_multiplier = None
        captain_multiplier_status = "UNKNOWN_ACTIVE_CHIP_STATE"

    def scenario(name: str, owned: list[str], xi: list[str], bench: list[str], cap: str) -> dict[str, Any]:
        players = []
        for pid in sorted(required_ids, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x)):
            field = by_id[pid]
            is_owned, is_starting = pid in owned, pid in xi
            personal_eo = 100.0 if is_owned else 0.0
            if is_owned and pid == cap:
                personal_eo = (100.0 * captain_multiplier) if captain_multiplier is not None else None
            field_eo, field_start = field.get("effective_ownership_pct"), field.get("starting_pct")
            players.append({
                "fpl_element_id": pid, "in_squad": is_owned, "in_starting_xi": is_starting,
                "in_outfield_bench": pid in bench, "is_captain": is_owned and pid == cap,
                "personal_effective_ownership_pct": personal_eo,
                "field_effective_ownership_pct": field_eo,
                "effective_ownership_delta_pct_points": (
                    round(personal_eo - field_eo, 8) if field_eo is not None else None
                ),
                "personal_starting_exposure_pct": 100.0 if is_starting else 0.0,
                "field_starting_pct": field_start,
                "starting_exposure_delta_pct_points": (
                    round((100.0 if is_starting else 0.0) - field_start, 8) if field_start is not None else None
                ),
            })
        owned = [row for row in players if row["in_squad"]]
        gaps = [row["effective_ownership_delta_pct_points"] for row in owned]
        starts = [row["starting_exposure_delta_pct_points"] for row in owned]
        return {
            "scenario": name, "squad_player_count": len(owned), "starting_xi_count": len(xi),
            "captain_id": cap,
            "captain_multiplier": captain_multiplier,
            "captain_multiplier_status": captain_multiplier_status,
            "squad_effective_ownership_gap_pct_points": round(sum(gaps), 8) if all(x is not None for x in gaps) else None,
            "starting_xi_exposure_gap_pct_points": round(sum(starts), 8) if all(x is not None for x in starts) else None,
            "players": players,
        }

    return {
        "status": "ATTACHED_PROVISIONAL_FIELD_CONTEXT",
        "artifact_id": snapshot.get("snapshot_id"),
        "evidence_role": snapshot["evidence_role"],
        "picks_lock_verified": False,
        "provisional_picks": True,
        "season": season, "target_gameweek": int(target_gameweek),
        "captured_at_utc": snapshot["captured_at_utc"], "as_of_utc": as_of.isoformat(),
        "deadline_utc": deadline.isoformat(),
        "source": dict(source), "cohort": dict(snapshot.get("cohort") or {}),
        "sample": dict(sample),
        "personal_chip_context": {
            "active_chip": active_chip,
            "active_chip_status": active_chip_status,
            "captain_multiplier": captain_multiplier,
            "captain_multiplier_status": captain_multiplier_status,
        },
        "coverage": {
            "field_player_row_count": len(rows),
            "candidate_squad_covered": True,
            "candidate_squad_player_count": len(required_ids),
            "missing_candidate_player_ids": [],
        },
        "scenarios": [
            scenario("HOLD", squad, current_xi, current_bench, captain),
            scenario(action, proposed_squad, proposed_xi, proposed_bench, proposed_captain),
        ] if action == "TRANSFER" else [scenario("HOLD", squad, current_xi, current_bench, captain)],
        "interpretation_boundary": (
            "Descriptive provisional field exposure only. EO is not converted to points; "
            "marginal EO is not used to reconstruct joint manager portfolios; this is not locked EO."
        ),
        "expected_points_combination": "PROHIBITED",
        "covar": "SEPARATE_RESEARCH_ONLY_CONTEXT",
        "release_eligible": False,
    }
