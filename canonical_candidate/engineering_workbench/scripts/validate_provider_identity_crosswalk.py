#!/usr/bin/env python3
"""Validate season-scoped provider-to-FPL identity mappings without fuzzy matching."""
from __future__ import annotations
import argparse, csv, json
from collections import Counter, defaultdict
from pathlib import Path

FIELDS = [
    "season", "competition_id", "competition_name", "provider_player_id",
    "provider_player_name", "fpl_element_id", "fpl_player_code",
    "fpl_player_name", "provider_team_id", "provider_team_name",
    "fpl_team_id", "fpl_team_name", "verification_status", "match_method",
    "evidence_source", "evidence_url", "verified_by", "verified_at",
]
REQUIRED = [
    "season", "competition_id", "provider_player_id", "provider_player_name",
    "fpl_element_id", "fpl_player_code", "fpl_player_name",
    "provider_team_id", "provider_team_name", "fpl_team_id", "fpl_team_name",
    "match_method", "evidence_source", "evidence_url", "verified_by", "verified_at",
]
STATUSES = {"verified", "pending", "ambiguous", "rejected"}
METHODS = {"provider_id_crosswalk", "official_alias", "club_roster_crosscheck", "manual_source_verified"}

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
        missing = [field for field in REQUIRED if not (row.get(field) or "").strip()]
        if missing:
            errors.append({"line": line, "error": "missing_verified_fields", "fields": missing})
            continue
        method = (row.get("match_method") or "").strip()
        if method not in METHODS:
            errors.append({"line": line, "error": "unapproved_match_method", "value": method})
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
    parser.add_argument("--provider", choices=("wyscout", "opta_pulselive"), required=True)
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
