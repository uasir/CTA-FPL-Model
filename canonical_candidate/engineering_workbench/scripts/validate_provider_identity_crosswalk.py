#!/usr/bin/env python3
"""Validate season-scoped provider-to-FPL identity mappings without fuzzy matching."""
from __future__ import annotations
import argparse, csv, json, re, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

FIELDS = [
    "season", "competition_id", "competition_name", "provider_player_id",
    "provider_player_name", "fpl_element_id", "fpl_player_code",
    "fpl_player_name", "provider_team_id", "provider_team_name",
    "fpl_team_id", "fpl_team_code", "fpl_team_name", "verification_status", "match_method",
    "evidence_source", "evidence_url", "verified_by", "verified_at",
    "provider_birth_date", "fpl_birth_date", "source_release",
    "provider_source_sha256", "fpl_source_sha256", "confidence_level", "review_notes",
]
REQUIRED = [
    "season", "competition_id", "provider_player_id", "provider_player_name",
    "fpl_element_id", "fpl_player_code", "fpl_player_name",
    "provider_team_id", "provider_team_name", "fpl_team_id", "fpl_team_name",
    "match_method", "evidence_source", "evidence_url", "verified_by", "verified_at",
]
STATUSES = {"verified", "pending", "ambiguous", "rejected"}
METHODS = {"provider_id_crosswalk", "official_alias", "club_roster_crosscheck", "manual_source_verified"}

def _normalize_team_name(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = " ".join(text.split())
    aliases = {
        "afc bournemouth": "bournemouth", "brighton": "brighton and hove albion",
        "brighton hove albion": "brighton and hove albion",
        "leeds": "leeds united", "man city": "manchester city",
        "man utd": "manchester united", "newcastle": "newcastle united",
        "nottm forest": "nottingham forest", "nott forest": "nottingham forest",
        "sheffield utd": "sheffield united", "spurs": "tottenham hotspur",
        "tottenham": "tottenham hotspur", "west ham": "west ham united",
        "wolves": "wolverhampton wanderers", "wolverhampton": "wolverhampton wanderers",
    }
    return aliases.get(text, text)


def validate_headers(headers, provider):
    """Reject malformed/empty templates before treating them as an unpopulated crosswalk."""
    if headers is None:
        return ["CSV header row is missing"]
    stripped = [name.strip() if isinstance(name, str) else "" for name in headers]
    duplicates = sorted({name for name in stripped if name and stripped.count(name) > 1})
    padded = sorted({raw for raw, clean in zip(headers, stripped) if raw != clean})
    required_headers = set(REQUIRED) | ({"fpl_team_code"} if provider == "opta_pulselive" else set())
    missing = sorted(required_headers - set(stripped))
    errors = []
    if duplicates:
        errors.append("duplicate CSV columns after whitespace normalization: " + ", ".join(duplicates))
    if padded:
        errors.append("CSV columns must not contain leading/trailing whitespace: " + ", ".join(padded))
    if missing:
        errors.append("missing required crosswalk columns: " + ", ".join(missing))
    return errors


def validate_rows(rows, provider):
    errors, accepted, statuses = [], [], Counter()
    for line, row in enumerate(rows, start=2):
        if not isinstance(row, Mapping) or any(value is None for value in row.values()):
            errors.append({"line": line, "error": "malformed_csv_row_width"})
            continue
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
        reader = csv.DictReader(handle)
        header_errors = validate_headers(reader.fieldnames, args.provider)
        rows = list(reader)
    accepted, report = validate_rows(rows, args.provider)
    if header_errors:
        report["errors"].extend({"error": "invalid_crosswalk_schema", "detail": item} for item in header_errors)
        report["status"] = "BLOCKED"
        report["join_ready"] = False
        accepted = []
    with (args.out_dir / "verified_provider_fpl_crosswalk.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(accepted)
    (args.out_dir / "crosswalk_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 2 if report["status"] == "BLOCKED" else 0

if __name__ == "__main__":
    raise SystemExit(main())
