#!/usr/bin/env python3
"""Validate season-scoped provider-to-FPL identity mappings without fuzzy matching."""
from __future__ import annotations
import argparse, csv, json, re, unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from audit_11footy_fpl_identity_candidates import normalize_team as _normalize_team_name, normalize_text as _normalize_player_name

FIELDS = [
    "season", "competition_id", "competition_name", "provider_player_id",
    "provider_player_name", "fpl_element_id", "fpl_player_code",
    "fpl_player_name", "provider_team_id", "provider_team_name",
    "fpl_team_id", "fpl_team_code", "fpl_team_name", "verification_status", "match_method",
    "evidence_source", "evidence_url", "verified_by", "verified_at",
    "provider_birth_date", "fpl_birth_date", "source_release",
    "provider_source_sha256", "fpl_source_sha256", "confidence_level", "review_notes",
    "corroborating_provider", "corroborating_provider_player_id", "corroborating_provider_name",
    "corroborating_provider_team_id", "corroborating_provider_team_name",
    "corroborating_provider_fpl_team_code", "corroborating_provider_source_commit",
    "corroborating_provider_source_sha256",
]
REQUIRED = [
    "season", "competition_id", "provider_player_id", "provider_player_name",
    "fpl_element_id", "fpl_player_code", "fpl_player_name",
    "provider_team_id", "provider_team_name", "fpl_team_id", "fpl_team_name",
    "match_method", "evidence_source", "evidence_url", "verified_by", "verified_at",
]
STATUSES = {"verified", "pending", "ambiguous", "rejected"}
METHODS = {"provider_id_crosswalk", "official_alias", "club_roster_crosscheck", "manual_source_verified", "exact_name_team_birth_date", "exact_name_team_opta_numeric_fpl_code_and_team"}

def validate_rows(rows, provider):
    errors, accepted, statuses = [], [], Counter()
    for line, row in enumerate(rows, start=2):
        status = (row.get("verification_status") or "").strip().lower()
        statuses[status or "blank"] += 1
        if status not in STATUSES:
            errors.append({"line": line, "error": "invalid_verification_status", "value": status})
            continue
        if status != "verified":
            continue
        required = REQUIRED + (["fpl_team_code"] if provider == "opta_pulselive" else [])
        missing = [field for field in required if not (row.get(field) or "").strip()]
        if missing:
            errors.append({"line": line, "error": "missing_verified_fields", "fields": missing})
            continue
        method = (row.get("match_method") or "").strip()
        if method not in METHODS:
            errors.append({"line": line, "error": "unapproved_match_method", "value": method})
            continue
        if provider == "opta_pulselive" and (row.get("provider_team_id") or "").strip() != (row.get("fpl_team_code") or "").strip():
            errors.append({"line": line, "error": "provider_team_id_does_not_match_fpl_team_code"})
            continue
        if provider == "11footy":
            numeric_fields = ("provider_player_id", "fpl_element_id", "provider_team_id", "fpl_team_id", "competition_id")
            invalid_numeric = [field for field in numeric_fields if not (row.get(field) or "").strip().isdigit()]
            if invalid_numeric:
                errors.append({"line": line, "error": "11footy_identity_and_team_ids_must_be_numeric", "fields": invalid_numeric})
                continue
            if _normalize_team_name(row.get("provider_team_name")) != _normalize_team_name(row.get("fpl_team_name")):
                errors.append({"line": line, "error": "11footy_provider_and_fpl_team_names_do_not_match"})
                continue
        if method == "exact_name_team_opta_numeric_fpl_code_and_team":
            if provider != "11footy":
                errors.append({"line": line, "error": "opta_numeric_bridge_method_is_11footy_only"})
                continue
            required_bridge = (
                "corroborating_provider", "corroborating_provider_player_id",
                "corroborating_provider_name", "corroborating_provider_team_id",
                "corroborating_provider_team_name", "corroborating_provider_fpl_team_code",
                "corroborating_provider_source_commit", "corroborating_provider_source_sha256",
            )
            missing_bridge = [field for field in required_bridge if not (row.get(field) or "").strip()]
            if missing_bridge:
                errors.append({"line": line, "error": "missing_opta_corroboration_fields", "fields": missing_bridge})
                continue
            if row.get("corroborating_provider") != "opta_pulselive":
                errors.append({"line": line, "error": "wrong_corroborating_provider"})
                continue
            if (row.get("corroborating_provider_player_id") or "").strip() != (row.get("fpl_player_code") or "").strip():
                errors.append({"line": line, "error": "opta_numeric_player_id_does_not_equal_fpl_code"})
                continue
            if (row.get("corroborating_provider_team_id") or "").strip() != (row.get("corroborating_provider_fpl_team_code") or "").strip():
                errors.append({"line": line, "error": "opta_team_id_does_not_equal_fpl_team_code"})
                continue
            if _normalize_player_name(row.get("corroborating_provider_name")) != _normalize_player_name(row.get("provider_player_name")):
                errors.append({"line": line, "error": "opta_and_11footy_full_names_do_not_match"})
                continue
            if _normalize_team_name(row.get("corroborating_provider_team_name")) != _normalize_team_name(row.get("provider_team_name")):
                errors.append({"line": line, "error": "opta_and_11footy_team_names_do_not_match"})
                continue
            provider_dob = (row.get("provider_birth_date") or "").strip()
            fpl_dob = (row.get("fpl_birth_date") or "").strip()
            if provider_dob:
                try:
                    date.fromisoformat(provider_dob[:10])
                    date.fromisoformat(fpl_dob[:10])
                except ValueError:
                    errors.append({"line": line, "error": "invalid_dob_in_opta_bridge_row"})
                    continue
                if provider_dob[:10] != fpl_dob[:10]:
                    errors.append({"line": line, "error": "dob_conflict_in_opta_bridge_row"})
                    continue
            opta_hash = (row.get("corroborating_provider_source_sha256") or "").strip().lower()
            if not re.fullmatch(r"[0-9a-f]{64}", opta_hash):
                errors.append({"line": line, "error": "invalid_opta_source_sha256"})
                continue
        if method == "exact_name_team_birth_date":
            if provider != "11footy":
                errors.append({"line": line, "error": "exact_name_team_birth_date_method_is_11footy_only"})
                continue
            provider_dob = (row.get("provider_birth_date") or "").strip()
            fpl_dob = (row.get("fpl_birth_date") or "").strip()
            try:
                date.fromisoformat(provider_dob[:10])
                date.fromisoformat(fpl_dob[:10])
            except ValueError:
                errors.append({"line": line, "error": "exact_name_team_birth_date_requires_valid_iso_dates"})
                continue
            if provider_dob[:10] != fpl_dob[:10]:
                errors.append({"line": line, "error": "exact_name_team_birth_date_mismatch"})
                continue
            if not (row.get("source_release") or "").strip():
                errors.append({"line": line, "error": "exact_name_team_birth_date_requires_source_release"})
                continue
            invalid_hash = False
            for hash_field in ("provider_source_sha256", "fpl_source_sha256"):
                digest = (row.get(hash_field) or "").strip().lower()
                if not re.fullmatch(r"[0-9a-f]{64}", digest):
                    errors.append({"line": line, "error": "exact_name_team_birth_date_requires_sha256_provenance", "field": hash_field})
                    invalid_hash = True
                    break
            if invalid_hash:
                continue
            if _normalize_player_name(row.get("provider_player_name")) != _normalize_player_name(row.get("fpl_player_name")):
                errors.append({"line": line, "error": "exact_name_team_birth_date_full_names_do_not_match"})
                continue
        if not (row.get("evidence_url") or "").strip().startswith(("https://", "http://")):
            errors.append({"line": line, "error": "evidence_url_must_be_http"})
            continue
        accepted.append({field: (row.get(field) or "").strip() for field in FIELDS})

    provider_keys, fpl_keys = defaultdict(set), defaultdict(set)
    for row in accepted:
        provider_keys[(row["season"], row["provider_player_id"])].add(row["fpl_element_id"])
        fpl_keys[(row["season"], row["fpl_element_id"])].add(row["provider_player_id"])
    for key, values in provider_keys.items():
        if len(values) > 1:
            errors.append({"error": "provider_identity_maps_to_multiple_fpl_elements", "key": key})
    for key, values in fpl_keys.items():
        if len(values) > 1:
            errors.append({"error": "fpl_element_maps_to_multiple_provider_identities", "key": key})

    if errors:
        status = "BLOCKED"
    elif not accepted and not rows:
        status = "EMPTY_NOT_READY"
    elif not accepted:
        status = "NO_VERIFIED_MAPPINGS"
    else:
        status = "PASS"
    report = {
        "provider": provider, "input_rows": len(rows),
        "verified_rows_accepted": len(accepted) if not errors else 0,
        "non_verified_rows_excluded": sum(n for s, n in statuses.items() if s in {"pending", "ambiguous", "rejected"}),
        "status_counts": dict(statuses), "errors": errors, "status": status,
        "join_ready": status == "PASS",
        "join_policy": "Season-scoped provider IDs only; evidence required; no fuzzy name matching",
    }
    return (accepted if not errors else []), report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("11footy", "wyscout", "opta_pulselive"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with args.input.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    accepted, report = validate_rows(rows, args.provider)
    with (args.out_dir / "verified_provider_fpl_crosswalk.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(accepted)
    (args.out_dir / "crosswalk_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 2 if report["status"] == "BLOCKED" else 0

if __name__ == "__main__":
    raise SystemExit(main())
