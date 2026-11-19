#!/usr/bin/env python3
"""Build a small, auditable Opta/PulseLive numeric-ID ↔ official FPL crosswalk."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from build_opta_lagged_team_features import (
    PLAYER_SOURCE_PATH,
    PROVIDER_COMMIT,
    PROVIDER_REPO,
    build_crosswalk,
)


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_identity_crosswalk(provider_players, bootstrap, provider_source_sha256, fpl_source_sha256):
    rows, report = build_crosswalk(
        bootstrap.get("elements", []),
        bootstrap.get("teams", []),
        provider_players,
        source_commit=PROVIDER_COMMIT,
    )
    report.update({
        "status": "PASS" if report.get("verified_id_and_team_matches", 0) > 0 and report.get("team_mismatches_or_duplicate_ids", 0) == 0 else "REVIEW_REQUIRED",
        "source_url": f"https://raw.githubusercontent.com/{PROVIDER_REPO}/{PROVIDER_COMMIT}/{PLAYER_SOURCE_PATH}",
        "source_sha256": provider_source_sha256,
        "fpl_bootstrap_sha256": fpl_source_sha256,
        "verification_scope": "Opta numeric playerId == official FPL code, with provider team_id == official FPL team code.",
        "prediction_validation": "NOT_EVALUATED",
        "publication_policy": "Player-level crosswalk remains runner-local; publish aggregate report only.",
    })
    return rows, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--opta-players", type=Path, required=True)
    parser.add_argument("--fpl-bootstrap", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    bootstrap = json.loads(args.fpl_bootstrap.read_text(encoding="utf-8"))
    rows, report = build_identity_crosswalk(
        read_csv(args.opta_players), bootstrap, sha256(args.opta_players), sha256(args.fpl_bootstrap)
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else [
        "season", "competition_id", "competition_name", "provider_player_id",
        "provider_player_name", "fpl_element_id", "fpl_player_code", "fpl_player_name",
        "provider_team_id", "provider_team_name", "fpl_team_id", "fpl_team_code",
        "fpl_team_name", "verification_status", "match_method", "evidence_source",
        "evidence_url", "verified_by", "verified_at",
    ]
    with (args.out_dir / "opta_pulselive_fpl_identity_crosswalk.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (args.out_dir / "opta_identity_report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
