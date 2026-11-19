#!/usr/bin/env python3
"""Verify historical Wyscout→FPL identities through independent 11footy evidence.

The FPL archive has no DOB. This resolver only promotes a mapping when both
independent event providers identify the same person by exact normalized full
name and exact DOB, independently map that person to the same historical FPL
element, and both show strong P1 fixture/stat corroboration.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def normalize_text(value):
    return " ".join(
        "".join(ch.lower() if ch.isalnum() else " " for ch in str(value or "")).split()
    )


def normalize_dob(value):
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return ""


def as_bool(value):
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def as_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def is_p1(row, provider):
    priority = str(row.get("review_priority") or "")
    expected = (
        "P1_MULTI_MATCH_TEAM_CORROBORATION"
        if provider == "Wyscout"
        else "P1_MULTI_MATCH_TEAM_SIGNATURE"
    )
    return priority == expected


def build_cross_provider_crosswalk(wyscout_rows, footy_rows):
    wyscout_by_key = defaultdict(list)
    footy_by_key = defaultdict(list)
    for row in wyscout_rows:
        key = (normalize_text(row.get("provider_player_name")), normalize_dob(row.get("provider_birth_date")))
        if all(key):
            wyscout_by_key[key].append(row)
    for row in footy_rows:
        key = (normalize_text(row.get("provider_player_name")), normalize_dob(row.get("provider_birth_date")))
        if all(key):
            footy_by_key[key].append(row)

    review_rows = []
    candidate_pairs = []
    counters = Counter()
    all_keys = sorted(set(wyscout_by_key) | set(footy_by_key))
    for key in all_keys:
        wrows = wyscout_by_key.get(key, [])
        frows = footy_by_key.get(key, [])
        if not wrows or not frows:
            continue
        counters["exact_name_dob_key_matches"] += 1
        if len(wrows) != 1 or len(frows) != 1:
            reason = "AMBIGUOUS_PROVIDER_NAME_DOB_KEY"
            counters["ambiguous_name_dob_keys"] += 1
            review_rows.append({
                "provider_player_name": wrows[0].get("provider_player_name") if wrows else frows[0].get("provider_player_name"),
                "provider_birth_date": key[1],
                "wyscout_candidate_rows": len(wrows),
                "11footy_candidate_rows": len(frows),
                "verification_status": "NOT_VERIFIED",
                "review_reason": reason,
            })
            continue
        w, f = wrows[0], frows[0]
        reasons = []
        wid = str(w.get("candidate_fpl_element_id") or "").strip()
        fid = str(f.get("candidate_fpl_element_id") or "").strip()
        if not wid or not fid:
            reasons.append("MISSING_FPL_CANDIDATE")
        elif wid != fid:
            reasons.append("PROVIDERS_DISAGREE_ON_FPL_ELEMENT_ID")
        if normalize_text(w.get("candidate_fpl_player_name")) != normalize_text(f.get("candidate_fpl_player_name")):
            reasons.append("FPL_CANDIDATE_NAME_DISAGREEMENT")
        if normalize_text(w.get("candidate_fpl_team_name")) != normalize_text(f.get("candidate_fpl_team_name")):
            reasons.append("FPL_CANDIDATE_TEAM_DISAGREEMENT")
        for label, row in (("WYS", w), ("11F", f)):
            if str(row.get("candidate_status") or "") != "PENDING":
                reasons.append(f"{label}_CANDIDATE_NOT_UNIQUE_PENDING")
            if not is_p1(row, "Wyscout" if label == "WYS" else "11footy"):
                reasons.append(f"{label}_NOT_P1")
            if not as_bool(row.get("team_match_to_season_end_team")):
                reasons.append(f"{label}_TEAM_NOT_CORROBORATED")
            if as_bool(row.get("team_mismatch_to_season_end_team")):
                reasons.append(f"{label}_TEAM_MISMATCH")
            if (as_int(row.get("fpl_history_overlap_rows")) or 0) < 1:
                reasons.append(f"{label}_NO_FPL_HISTORY_OVERLAP")
            if (as_int(row.get("fpl_positive_minutes_rows")) or 0) < 1:
                reasons.append(f"{label}_NO_POSITIVE_FPL_MINUTES")
        if reasons:
            counters["cross_provider_pairs_not_verified"] += 1
            review_rows.append({
                "provider_player_name": w.get("provider_player_name", ""),
                "provider_birth_date": key[1],
                "wyscout_player_id": w.get("provider_player_id", ""),
                "11footy_player_id": f.get("provider_player_id", ""),
                "wyscout_fpl_element_id": wid,
                "11footy_fpl_element_id": fid,
                "verification_status": "NOT_VERIFIED",
                "review_reason": ";".join(sorted(set(reasons))),
            })
            continue

        candidate_pairs.append({
            "season": "2017/18",
            "competition": "English Premier League",
            "provider": "Wyscout",
            "provider_player_id": str(w.get("provider_player_id") or ""),
            "provider_player_name": w.get("provider_player_name", ""),
            "provider_birth_date": key[1],
            "corroborating_provider": "11footy",
            "corroborating_provider_player_id": str(f.get("provider_player_id") or ""),
            "corroborating_provider_player_name": f.get("provider_player_name", ""),
            "corroborating_provider_birth_date": normalize_dob(f.get("provider_birth_date")),
            "fpl_element_id": wid,
            "fpl_player_code": w.get("candidate_fpl_player_code") or f.get("candidate_fpl_player_code") or "",
            "fpl_player_name": w.get("candidate_fpl_player_name", ""),
            "fpl_team_id": w.get("candidate_fpl_team_id", ""),
            "fpl_team_name": w.get("candidate_fpl_team_name", ""),
            "wyscout_review_priority": w.get("review_priority", ""),
            "11footy_review_priority": f.get("review_priority", ""),
            "wyscout_fpl_history_overlap_rows": as_int(w.get("fpl_history_overlap_rows")) or 0,
            "11footy_fpl_history_overlap_rows": as_int(f.get("fpl_history_overlap_rows")) or 0,
            "wyscout_full_signature_exact_rows": as_int(w.get("goal_assist_signature_exact")) or 0,
            "11footy_full_signature_exact_rows": as_int(f.get("full_signature_exact_rows")) or 0,
            "verification_status": "VERIFIED_CROSS_PROVIDER_IDENTITY_AND_FPL_HISTORY",
            "verification_method": (
                "EXACT_NORMALIZED_NAME_AND_DOB_AGREEMENT_ACROSS_WYSCOUT_AND_11FOOTY;"
                "SAME_UNIQUE_HISTORICAL_FPL_ELEMENT_ID;"
                "BOTH_PROVIDERS_P1_TEAM_AND_MATCH_STAT_CORROBORATION"
            ),
            "candidate_source_status": "CANDIDATE_FILES_RETAINED_FOR_AUDIT",
        })
        counters["strict_cross_provider_pairs"] += 1

    # Enforce one-to-one provider and FPL IDs across the promoted set.
    by_wyscout = defaultdict(list)
    by_footy = defaultdict(list)
    by_fpl = defaultdict(list)
    for row in candidate_pairs:
        by_wyscout[row["provider_player_id"]].append(row)
        by_footy[row["corroborating_provider_player_id"]].append(row)
        by_fpl[row["fpl_element_id"]].append(row)
    collisions = {
        id_value
        for mapping in (by_wyscout, by_footy, by_fpl)
        for id_value, rows in mapping.items()
        if len(rows) > 1
    }
    verified = []
    for row in candidate_pairs:
        if (
            len(by_wyscout[row["provider_player_id"]]) == 1
            and len(by_footy[row["corroborating_provider_player_id"]]) == 1
            and len(by_fpl[row["fpl_element_id"]]) == 1
        ):
            verified.append(row)
        else:
            review_rows.append({
                "provider_player_name": row["provider_player_name"],
                "provider_birth_date": row["provider_birth_date"],
                "wyscout_player_id": row["provider_player_id"],
                "11footy_player_id": row["corroborating_provider_player_id"],
                "wyscout_fpl_element_id": row["fpl_element_id"],
                "11footy_fpl_element_id": row["fpl_element_id"],
                "verification_status": "NOT_VERIFIED",
                "review_reason": "ONE_TO_ONE_ID_COLLISION",
            })
    counters["one_to_one_collision_ids"] = len(collisions)
    counters["verified_crosswalk_rows"] = len(verified)
    report = {
        "status": "PASS_CROSS_PROVIDER_VERIFIED_IDENTITIES" if verified else "NO_VERIFIED_CROSS_PROVIDER_IDENTITIES",
        "wyscout_candidate_rows": len(wyscout_rows),
        "11footy_candidate_rows": len(footy_rows),
        "exact_name_dob_key_matches": counters["exact_name_dob_key_matches"],
        "ambiguous_name_dob_keys": counters["ambiguous_name_dob_keys"],
        "strict_cross_provider_pairs": counters["strict_cross_provider_pairs"],
        "cross_provider_pairs_not_verified": counters["cross_provider_pairs_not_verified"],
        "one_to_one_collision_ids": counters["one_to_one_collision_ids"],
        "verified_crosswalk_rows": counters["verified_crosswalk_rows"],
        "verified_unique_wyscout_players": len({row["provider_player_id"] for row in verified}),
        "verified_unique_11footy_players": len({row["corroborating_provider_player_id"] for row in verified}),
        "verified_unique_fpl_elements": len({row["fpl_element_id"] for row in verified}),
        "verification_policy": (
            "Promote only unique exact normalized full-name and exact DOB matches across Wyscout and "
            "11footy, where both independent candidate builders select the same historical FPL element, "
            "both are P1, both have team corroboration, no team mismatch, positive FPL minutes and "
            "fixture-history overlap. Enforce one-to-one Wyscout, 11footy and FPL IDs."
        ),
        "historical_fpl_dob_limitation": (
            "The historical FPL archive has no DOB. DOB is independently agreed between Wyscout and "
            "11footy; the FPL element link is supported by both providers' independent P1 fixture/stat "
            "corroboration, not by an FPL DOB field."
        ),
        "prediction_validation": "NOT_EVALUATED",
        "publication_policy": "Verified crosswalk and review rows remain inside the workflow runner; publish aggregate report only.",
        "attribution": (
            "Wyscout event data: Pappalardo and Massucco (2019), CC BY 4.0. "
            "11footy EPL data: CC BY-NC 4.0 (non-commercial use only). "
            "Historical FPL data remains property of Fantasy Premier League."
        ),
    }
    return verified, review_rows, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wyscout-candidates", type=Path, required=True)
    parser.add_argument("--11footy-candidates", dest="footy_candidates", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    verified, review, report = build_cross_provider_crosswalk(
        read_csv(args.wyscout_candidates), read_csv(args.footy_candidates)
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    verified_fields = list(verified[0]) if verified else [
        "season", "competition", "provider", "provider_player_id", "provider_player_name",
        "provider_birth_date", "corroborating_provider", "corroborating_provider_player_id",
        "fpl_element_id", "fpl_player_name", "fpl_team_name", "verification_status",
        "verification_method",
    ]
    review_fields = list(review[0]) if review else [
        "provider_player_name", "provider_birth_date", "wyscout_player_id", "11footy_player_id",
        "wyscout_fpl_element_id", "11footy_fpl_element_id", "verification_status", "review_reason",
    ]
    with (args.out_dir / "verified_wyscout_fpl_identity_crosswalk.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=verified_fields)
        writer.writeheader()
        writer.writerows(verified)
    with (args.out_dir / "cross_provider_identity_review_queue.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=review_fields)
        writer.writeheader()
        writer.writerows(review)
    (args.out_dir / "cross_provider_identity_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
