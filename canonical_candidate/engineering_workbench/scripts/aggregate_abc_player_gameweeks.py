#!/usr/bin/env python3
"""Strict player-fixture to player-gameweek aggregation for the ABC research panel.

ABC features are pre-deadline rolling snapshots or rates, not fixture outcomes.
They are never summed or blindly averaged across a DGW. A feature is retained
only when every observed fixture row has the same non-null value. Conflicts and
partial coverage remain explicit and block that feature for the player-GW.
Model eligibility also requires the exact reference fixture-ID set from the pinned FPL
history export, preventing an incomplete or mismatched DGW from being accepted.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import hashlib
from collections import Counter, defaultdict
from pathlib import Path

from cta_four_layer_pipeline import LAYER_FEATURES

ABC_FEATURES = tuple(
    f"abc_{name}" for layer_features in LAYER_FEATURES.values()
    for name in layer_features
)
FPL_HISTORY_FEATURES = (
    "fpl_total_points_prior_3_avg",
    "fpl_total_points_prior_5_avg",
    "fpl_minutes_prior_3_avg",
    "fpl_minutes_prior_5_avg",
)
TOLERANCE = 1e-9


def number(value):
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def truth(value):
    return str(value).strip().lower() in {"true", "1", "yes"}


def _consensus(rows, field):
    values = [number(row.get(field)) for row in rows]
    observed = [value for value in values if value is not None]
    if not observed:
        return None, "MISSING"
    if len(observed) != len(values):
        return None, "PARTIAL"
    if max(observed) - min(observed) > TOLERANCE:
        return None, "CONFLICT"
    return observed[0], "CONSISTENT"


def _sum_target(rows, field):
    values = [number(row.get(field)) for row in rows]
    if any(value is None for value in values):
        return None, "INCOMPLETE_TARGET_LABEL"
    return sum(values), "COMPLETE"


def aggregate_player_gameweeks(rows, expected_fixture_ids=None, reference_invalid_keys=None):
    """Aggregate rows; expected_fixture_ids maps (season, element, GW) to reference fixture-ID sets."""
    expected_fixture_ids = expected_fixture_ids or {}
    reference_invalid_keys = reference_invalid_keys or set()
    grouped = defaultdict(list)
    for row in rows:
        season = str(row.get("season") or "")
        player = str(row.get("fpl_element_id") or "")
        gw_value = number(row.get("gameweek"))
        fixture = str(row.get("fixture_id") or "")
        if not season or not player or gw_value is None or not fixture:
            raise ValueError("Every ABC fixture row needs season, FPL element, gameweek and fixture ID")
        if not gw_value.is_integer():
            raise ValueError(f"Gameweek must be an integer: {gw_value}")
        grouped[(season, player, int(gw_value))].append(row)

    output = []
    for (season, player, gw), fixtures in sorted(grouped.items()):
        fixture_ids = [str(row["fixture_id"]) for row in fixtures]
        if len(fixture_ids) != len(set(fixture_ids)):
            raise ValueError("Duplicate player-fixture row")
        key = (season, player, gw)
        expected_ids = expected_fixture_ids.get(key)
        if expected_ids is not None:
            expected_ids = {str(value) for value in expected_ids}
            if not expected_ids:
                raise ValueError("Expected fixture ID set cannot be empty")

        reasons = []
        if expected_ids is None:
            reasons.append("REFERENCE_FIXTURE_IDS_NOT_SUPPLIED")
        elif set(fixture_ids) != expected_ids:
            reasons.append("FIXTURE_ID_SET_MISMATCH")
        if key in reference_invalid_keys:
            reasons.append("FPL_REFERENCE_TARGET_OR_FIXTURE_MISMATCH")

        if not all(truth(row.get("identity_verified")) for row in fixtures):
            reasons.append("IDENTITY_NOT_VERIFIED")
        if not all(truth(row.get("research_eligible_for_analysis")) for row in fixtures):
            reasons.append("SOURCE_ROW_NOT_RESEARCH_ELIGIBLE")

        points, points_status = _sum_target(fixtures, "target_fpl_total_points")
        minutes, minutes_status = _sum_target(fixtures, "target_fpl_minutes")
        if points_status != "COMPLETE":
            reasons.append(points_status)
        if minutes_status != "COMPLETE":
            reasons.append(minutes_status)

        record = {
            "season": season,
            "fpl_element_id": player,
            "gameweek": gw,
            "fixture_ids": sorted(fixture_ids),
            "fixture_count_observed": len(fixtures),
            "fixture_count_expected": len(expected_ids) if expected_ids is not None else None,
            "fixture_completeness_status": (
                "REFERENCE_INVALID" if key in reference_invalid_keys
                else "PASS" if expected_ids is not None and set(fixture_ids) == expected_ids
                else "NOT_CHECKED" if expected_ids is None else "MISMATCH"
            ),
            "target_fpl_total_points": points,
            "target_fpl_minutes": minutes,
            "research_eligible_for_model": not reasons,
            "exclusion_reasons": reasons,
            "abc_feature_aggregation_status": {},
            "abc_feature_coverage": {},
            "fpl_history_aggregation_status": {},
        }

        for field in ABC_FEATURES:
            value, status = _consensus(fixtures, field)
            record[field] = value
            record["abc_feature_aggregation_status"][field] = status
            record["abc_feature_coverage"][field] = (
                "OBSERVED" if status == "CONSISTENT" else status
            )

        for field in FPL_HISTORY_FEATURES:
            value, status = _consensus(fixtures, field)
            record[field] = value
            record["fpl_history_aggregation_status"][field] = status

        # Preserve deadline/provenance only when the fixture rows agree.
        for field in ("feature_cutoff_time_utc", "feature_cutoff_policy"):
            values = sorted({str(row.get(field) or "") for row in fixtures})
            record[field] = values[0] if len(values) == 1 else None
            if len(values) != 1:
                reasons.append("CONFLICTING_" + field.upper())
        record["source_provenance"] = sorted({
            str(row.get("abc_provenance") or "") for row in fixtures
            if row.get("abc_provenance")
        })
        record["research_eligible_for_model"] = not reasons
        record["exclusion_reasons"] = sorted(set(reasons))
        output.append(record)
    return output


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_expected_fixture_ids(path):
    expected = defaultdict(set)
    invalid_keys = set()
    for row in read_csv(path):
        key = (str(row["season"]), str(row["fpl_element_id"]), int(row["gameweek"]))
        fixture_id = str(row["fixture_id"])
        if not fixture_id:
            raise ValueError("Blank reference fixture ID")
        expected[key].add(fixture_id)
        if str(row.get("reference_status", "PASS")).upper() != "PASS":
            invalid_keys.add(key)
    return dict(expected), invalid_keys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--expected-fixtures", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report-out", type=Path, required=True)
    args = parser.parse_args()
    expected_fixture_ids, reference_invalid_keys = read_expected_fixture_ids(args.expected_fixtures)
    aggregated = aggregate_player_gameweeks(
        read_csv(args.input), expected_fixture_ids, reference_invalid_keys
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        fields = list(aggregated[0]) if aggregated else [
            "season", "fpl_element_id", "gameweek", "research_eligible_for_model"
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in aggregated:
            serializable = {
                key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
                for key, value in row.items()
            }
            writer.writerow(serializable)
    feature_status_counts = {
        field: dict(Counter(row["abc_feature_aggregation_status"][field] for row in aggregated))
        for field in ABC_FEATURES
    }
    exclusion_reason_counts = Counter(
        reason for row in aggregated for reason in row["exclusion_reasons"]
    )
    report = {
        "status": (
            "PASS_STRUCTURAL_WITH_EXCLUSIONS"
            if any(not row["research_eligible_for_model"] for row in aggregated)
            else "PASS_STRUCTURAL_ONLY"
        ),
        "player_gameweeks": len(aggregated),
        "eligible_player_gameweeks": sum(row["research_eligible_for_model"] for row in aggregated),
        "excluded_player_gameweeks": sum(not row["research_eligible_for_model"] for row in aggregated),
        "reference_invalid_player_gameweeks": len(reference_invalid_keys),
        "exclusion_reason_counts": dict(sorted(exclusion_reason_counts.items())),
        "feature_status_counts": feature_status_counts,
        "feature_aggregation_policy": "CONSENSUS_ONLY_NO_SUM_OR_BLIND_AVERAGE",
        "dgw_policy": "Require exact fixture-ID set from the pinned FPL history reference; each repeated pre-deadline snapshot must agree across fixture rows.",
        "input_panel_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "expected_fixture_reference_sha256": hashlib.sha256(args.expected_fixtures.read_bytes()).hexdigest(),
        "promotion_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
    }
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
