#!/usr/bin/env python3
"""Promote only exact, unique 11footy↔official-FPL identity matches.

A verified row requires exact normalized full name, exact normalized current
team, identical valid ISO birth date from independent source snapshots, and
a one-to-one provider-ID/FPL-element mapping. Name-only and missing-DOB
candidates remain pending and are never promoted.
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from audit_11footy_fpl_identity_candidates import normalize_team, normalize_text

CROSSWALK_FIELDS = [
    "season", "competition_id", "competition_name", "provider_player_id",
    "provider_player_name", "fpl_element_id", "fpl_player_code",
    "fpl_player_name", "provider_team_id", "provider_team_name",
    "fpl_team_id", "fpl_team_code", "fpl_team_name", "verification_status",
    "match_method", "evidence_source", "evidence_url", "verified_by",
    "verified_at", "provider_birth_date", "fpl_birth_date", "source_release",
    "provider_source_sha256", "fpl_source_sha256", "confidence_level", "review_notes",
    "corroborating_provider", "corroborating_provider_player_id", "corroborating_provider_name",
    "corroborating_provider_team_id", "corroborating_provider_team_name",
    "corroborating_provider_fpl_team_code", "corroborating_provider_source_commit",
    "corroborating_provider_source_sha256",
]

def _valid_iso_date(value):
    try:
        date.fromisoformat(str(value or "").strip()[:10])
        return bool(str(value or "").strip())
    except ValueError:
        return False

def _numeric(value):
    return str(value or "").strip().isdigit()

def build_verified_crosswalk(candidate_rows, verified_at=None, opta_crosswalk_rows=None, opta_report=None):
    verified_at = verified_at or datetime.now(timezone.utc).isoformat()
    exclusions = Counter()
    eligible = []
    for row in candidate_rows:
        if str(row.get("match_method") or "") != "exact_name_team_birth_date":
            exclusions["not_exact_name_team_birth_date_method"] += 1
            continue
        if str(row.get("confidence_level") or "").lower() != "high":
            exclusions["not_high_confidence"] += 1
            continue
        if str(row.get("verification_status") or "").lower() != "pending":
            exclusions["candidate_not_pending"] += 1
            continue
        provider_name = normalize_text(row.get("provider_player_name"))
        fpl_name = normalize_text(row.get("fpl_player_name"))
        if not provider_name or provider_name != fpl_name:
            exclusions["full_name_not_exact"] += 1
            continue
        provider_team = normalize_team(row.get("provider_team_name"))
        fpl_team = normalize_team(row.get("fpl_team_name"))
        if not provider_team or provider_team != fpl_team:
            exclusions["team_not_exact"] += 1
            continue
        provider_dob = str(row.get("provider_birth_date") or "").strip()
        fpl_dob = str(row.get("fpl_birth_date") or "").strip()
        if not _valid_iso_date(provider_dob) or not _valid_iso_date(fpl_dob):
            exclusions["birth_date_missing_or_invalid"] += 1
            continue
        if provider_dob[:10] != fpl_dob[:10]:
            exclusions["birth_date_conflict"] += 1
            continue
        numeric_fields = (
            "competition_id", "provider_player_id", "fpl_element_id",
            "provider_team_id", "fpl_team_id",
        )
        if any(not _numeric(row.get(field)) for field in numeric_fields):
            exclusions["missing_or_non_numeric_identity_id"] += 1
            continue
        if not str(row.get("fpl_player_code") or "").strip():
            exclusions["missing_fpl_player_code"] += 1
            continue
        if not str(row.get("provider_source_sha256") or "").strip():
            exclusions["missing_provider_source_hash"] += 1
            continue
        if not str(row.get("fpl_bootstrap_sha256") or "").strip():
            exclusions["missing_fpl_source_hash"] += 1
            continue
        if not str(row.get("provider_release_url") or "").startswith("https://"):
            exclusions["missing_provider_evidence_url"] += 1
            continue
        if not str(row.get("fpl_source_url") or "").startswith("https://"):
            exclusions["missing_fpl_evidence_url"] += 1
            continue
        eligible.append(row)

    by_provider = defaultdict(list)
    by_fpl = defaultdict(list)
    for index, row in enumerate(eligible):
        by_provider[(str(row["season"]), str(row["provider_player_id"]))].append(index)
        by_fpl[(str(row["season"]), str(row["fpl_element_id"]))].append(index)
    collisions = set()
    for indices in list(by_provider.values()) + list(by_fpl.values()):
        if len(indices) != 1:
            collisions.update(indices)
    if collisions:
        exclusions["one_to_one_collision_or_duplicate"] += len(collisions)

    output = []
    for index, row in enumerate(eligible):
        if index in collisions:
            continue
        output.append({
            "season": str(row["season"]),
            "competition_id": str(row["competition_id"]),
            "competition_name": str(row.get("competition_name") or "Premier League"),
            "provider_player_id": str(row["provider_player_id"]),
            "provider_player_name": str(row["provider_player_name"]),
            "fpl_element_id": str(row["fpl_element_id"]),
            "fpl_player_code": str(row["fpl_player_code"]),
            "fpl_player_name": str(row["fpl_player_name"]),
            "provider_team_id": str(row["provider_team_id"]),
            "provider_team_name": str(row["provider_team_name"]),
            "fpl_team_id": str(row["fpl_team_id"]),
            "fpl_team_code": "",
            "fpl_team_name": str(row["fpl_team_name"]),
            "verification_status": "verified",
            "match_method": "exact_name_team_birth_date",
            "evidence_source": (
                "11footy player catalogue and official FPL bootstrap-static; "
                "exact full name, team and birth-date cross-check"
            ),
            "evidence_url": (
                str(row["provider_release_url"]) + " | " + str(row["fpl_source_url"])
            ),
            "verified_by": "automated_exact_name_team_birth_date_crosscheck",
            "verified_at": verified_at,
            "provider_birth_date": str(row["provider_birth_date"])[:10],
            "fpl_birth_date": str(row["fpl_birth_date"])[:10],
            "source_release": str(row.get("source_release") or ""),
            "provider_source_sha256": str(row["provider_source_sha256"]),
            "fpl_source_sha256": str(row["fpl_bootstrap_sha256"]),
            "confidence_level": "very_high",
            "review_notes": (
                "Unique one-to-one match across independent source snapshots using exact "
                "normalized full name, exact normalized team and identical valid ISO birth date. "
                "No fuzzy matching. Identity verification only; CTA feature and prediction "
                "validation remain separate gates."
            ),
        })

    opta_bridge_rows = []
    opta_exclusions = Counter()
    if opta_crosswalk_rows is not None or opta_report is not None:
        if opta_crosswalk_rows is None or opta_report is None:
            raise ValueError("Opta crosswalk rows and report must be supplied together")
        if opta_report.get("status") != "PASS":
            raise ValueError("Opta numeric-ID crosswalk report is not validated")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", str(opta_report.get("source_sha256") or "")):
            raise ValueError("Opta source SHA-256 provenance is missing or invalid")
        opta_by_code = defaultdict(list)
        for opta_row in opta_crosswalk_rows:
            if (
                str(opta_row.get("verification_status") or "").lower() != "verified"
                or str(opta_row.get("match_method") or "") != "provider_id_crosswalk"
            ):
                continue
            code = str(opta_row.get("fpl_player_code") or "").strip()
            if code:
                opta_by_code[code].append(opta_row)
        existing_provider_ids = {str(row["provider_player_id"]) for row in output}
        existing_fpl_ids = {str(row["fpl_element_id"]) for row in output}
        for row in candidate_rows:
            if str(row.get("verification_status") or "").lower() != "pending":
                continue
            if str(row.get("confidence_level") or "").lower() != "review_required":
                continue
            if str(row.get("match_method") or "") != "exact_name_team_birth_date_missing":
                continue
            provider_dob = str(row.get("provider_birth_date") or "").strip()
            fpl_dob = str(row.get("fpl_birth_date") or "").strip()
            if _valid_iso_date(provider_dob) and _valid_iso_date(fpl_dob) and provider_dob[:10] != fpl_dob[:10]:
                opta_exclusions["birth_date_conflict"] += 1
                continue
            code = str(row.get("fpl_player_code") or "").strip()
            matches = opta_by_code.get(code, [])
            if len(matches) != 1:
                opta_exclusions["opta_numeric_code_missing_or_ambiguous"] += 1
                continue
            opta = matches[0]
            provider_id = str(row.get("provider_player_id") or "").strip()
            fpl_id = str(row.get("fpl_element_id") or "").strip()
            checks = (
                (provider_id not in existing_provider_ids, "provider_id_already_verified"),
                (fpl_id not in existing_fpl_ids, "fpl_element_already_verified"),
                (bool(code) and code == str(opta.get("provider_player_id") or "").strip(), "opta_player_id_not_equal_fpl_code"),
                (fpl_id == str(opta.get("fpl_element_id") or "").strip(), "fpl_element_id_disagreement"),
                (code == str(opta.get("fpl_player_code") or "").strip(), "fpl_code_disagreement"),
                (str(row.get("fpl_team_id") or "").strip() == str(opta.get("fpl_team_id") or "").strip(), "fpl_team_id_disagreement"),
                (normalize_text(row.get("provider_player_name")) == normalize_text(row.get("fpl_player_name")), "11footy_fpl_full_name_disagreement"),
                (normalize_text(row.get("provider_player_name")) == normalize_text(opta.get("provider_player_name")), "provider_full_name_disagreement"),
                (normalize_team(row.get("provider_team_name")) == normalize_team(opta.get("provider_team_name")), "provider_team_disagreement"),
                (normalize_text(row.get("fpl_player_name")) == normalize_text(opta.get("fpl_player_name")), "fpl_full_name_disagreement"),
                (normalize_team(row.get("fpl_team_name")) == normalize_team(opta.get("fpl_team_name")), "fpl_team_disagreement"),
                (str(opta.get("provider_team_id") or "").strip() == str(opta.get("fpl_team_code") or "").strip(), "opta_team_code_not_verified"),
            )
            failed = [reason for passed, reason in checks if not passed]
            if failed:
                opta_exclusions[";".join(failed)] += 1
                continue
            if not all(_numeric(row.get(field)) for field in (
                "competition_id", "provider_player_id", "fpl_element_id", "provider_team_id", "fpl_team_id"
            )):
                opta_exclusions["missing_or_non_numeric_identity_id"] += 1
                continue
            if not all(str(row.get(field) or "").strip() for field in (
                "source_release", "provider_source_sha256", "fpl_bootstrap_sha256",
                "provider_release_url", "fpl_source_url"
            )):
                opta_exclusions["missing_source_provenance"] += 1
                continue
            if not _valid_iso_date(fpl_dob):
                opta_exclusions["missing_or_invalid_fpl_birth_date"] += 1
                continue
            if not str(opta_report.get("source_sha256") or "").strip():
                opta_exclusions["missing_opta_source_hash"] += 1
                continue
            opta_bridge_rows.append({
                "season": str(row.get("season") or ""),
                "competition_id": str(row.get("competition_id") or ""),
                "competition_name": str(row.get("competition_name") or "Premier League"),
                "provider_player_id": provider_id,
                "provider_player_name": str(row.get("provider_player_name") or ""),
                "fpl_element_id": fpl_id,
                "fpl_player_code": code,
                "fpl_player_name": str(row.get("fpl_player_name") or ""),
                "provider_team_id": str(row.get("provider_team_id") or ""),
                "provider_team_name": str(row.get("provider_team_name") or ""),
                "fpl_team_id": str(row.get("fpl_team_id") or ""),
                "fpl_team_code": str(opta.get("fpl_team_code") or ""),
                "fpl_team_name": str(row.get("fpl_team_name") or ""),
                "verification_status": "verified",
                "match_method": "exact_name_team_opta_numeric_fpl_code_and_team",
                "evidence_source": "11footy player catalogue + Opta/PulseLive numeric ID crosswalk + official FPL bootstrap",
                "evidence_url": (
                    str(row.get("provider_release_url") or "") + " | "
                    + str(opta.get("evidence_url") or "") + " | "
                    + str(row.get("fpl_source_url") or "")
                ),
                "verified_by": "automated_11footy_opta_fpl_numeric_code_team_crosscheck",
                "verified_at": verified_at,
                "provider_birth_date": provider_dob[:10] if _valid_iso_date(provider_dob) else "",
                "fpl_birth_date": fpl_dob[:10] if _valid_iso_date(fpl_dob) else "",
                "source_release": str(row.get("source_release") or ""),
                "provider_source_sha256": str(row.get("provider_source_sha256") or ""),
                "fpl_source_sha256": str(row.get("fpl_bootstrap_sha256") or ""),
                "confidence_level": "very_high_cross_provider",
                "review_notes": (
                    "Provider DOB unavailable; identity independently corroborated by exact normalized "
                    "full name and team against Opta/PulseLive, whose numeric playerId equals the official "
                    "FPL player code and whose team_id equals the official FPL team code. FPL element ID, "
                    "player name and team independently agree. No fuzzy matching."
                ),
                "corroborating_provider": "opta_pulselive",
                "corroborating_provider_player_id": str(opta.get("provider_player_id") or ""),
                "corroborating_provider_name": str(opta.get("provider_player_name") or ""),
                "corroborating_provider_team_id": str(opta.get("provider_team_id") or ""),
                "corroborating_provider_team_name": str(opta.get("provider_team_name") or ""),
                "corroborating_provider_fpl_team_code": str(opta.get("fpl_team_code") or ""),
                "corroborating_provider_source_commit": str(opta_report.get("source_commit") or ""),
                "corroborating_provider_source_sha256": str(opta_report.get("source_sha256") or ""),
            })
            existing_provider_ids.add(provider_id)
            existing_fpl_ids.add(fpl_id)

        output.extend(opta_bridge_rows)

    report = {
        "status": "PASS" if output else "NO_VERIFIED_MAPPINGS",
        "season": str(candidate_rows[0].get("season") or "") if candidate_rows else "",
        "input_candidate_rows": len(candidate_rows),
        "exact_cross_source_candidates": len(eligible),
        "verified_crosswalk_rows": len(output),
        "verified_dob_rows": len(output) - len(opta_bridge_rows),
        "verified_opta_bridge_rows": len(opta_bridge_rows),
        "opta_bridge_exclusions_by_reason": dict(sorted(opta_exclusions.items())),
        "opta_source_commit": opta_report.get("source_commit") if opta_report else None,
        "opta_source_sha256": opta_report.get("source_sha256") if opta_report else None,
        "excluded_rows_by_reason": dict(sorted(exclusions.items())),
        "one_to_one_mapping": True,
        "verification_method": (
            "Exact normalized full name + exact normalized team + identical valid ISO birth date "
            "across 11footy and FPL; or, where provider DOB is unavailable, exact name/team agreement "
            "with the verified Opta numeric playerId=FPL code and team_id=FPL team code crosswalk. "
            "One-to-one within season."
        ),
        "fuzzy_matching_used": False,
        "identity_verification_only": True,
        "cta_feature_validation": "NOT_EVALUATED",
        "prediction_training_eligible": False,
        "production_eligible": False,
        "publication_policy": (
            "Keep player-level verified crosswalk local to the workflow runner; publish aggregate "
            "counts and source hashes only."
        ),
        "verified_at": verified_at,
    }
    return output, report

def main():
    parser = argparse.ArgumentParser(description="Verify strict 11footy-to-FPL identity crosswalk")
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--opta-crosswalk", type=Path)
    parser.add_argument("--opta-report", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    with args.candidates.open(newline="", encoding="utf-8-sig") as handle:
        candidates = list(csv.DictReader(handle))
    if bool(args.opta_crosswalk) != bool(args.opta_report):
        parser.error("--opta-crosswalk and --opta-report must be supplied together")
    opta_rows = None
    opta_report = None
    if args.opta_crosswalk:
        with args.opta_crosswalk.open(newline="", encoding="utf-8-sig") as handle:
            opta_rows = list(csv.DictReader(handle))
        opta_report = json.loads(args.opta_report.read_text(encoding="utf-8"))
    rows, report = build_verified_crosswalk(candidates, opta_crosswalk_rows=opta_rows, opta_report=opta_report)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "verified_11footy_fpl_identity_crosswalk.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=CROSSWALK_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (args.out_dir / "verified_identity_summary.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
