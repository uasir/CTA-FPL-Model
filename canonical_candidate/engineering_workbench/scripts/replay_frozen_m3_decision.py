#!/usr/bin/env python3
"""Deterministically replay a frozen M3 recommendation from its captured bundle.

This replay verifies the canonical captured inputs and the exact checked-out
M3 commit. Raw-source-to-normalized-input reconstruction remains a separate
provenance check performed by the capture/audit pipeline.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from run_predeadline_m3_decision import run_predeadline_m3_decision


class DecisionReplayError(ValueError):
    """Raised when a frozen M3 decision cannot be reproduced exactly."""


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise DecisionReplayError("decision payload is not canonical JSON") from exc


def _verify_archives(manifest: Mapping[str, Any]) -> None:
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise DecisionReplayError("capture manifest sources must be a list")
    required = {"provider_forecast", "player_metadata", "manager_deadline_state"}
    seen = set()
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise DecisionReplayError(f"sources[{index}] must be an object")
        kind = source.get("source_type")
        if kind not in required or kind in seen:
            raise DecisionReplayError(f"unsupported or duplicate source type: {kind}")
        seen.add(kind)
        try:
            raw = base64.b64decode(source["raw_payload_base64"], validate=True)
        except (KeyError, ValueError, TypeError) as exc:
            raise DecisionReplayError(f"{kind} raw archive is invalid base64") from exc
        digest = hashlib.sha256(raw).hexdigest()
        if digest != source.get("raw_sha256"):
            raise DecisionReplayError(f"{kind} raw archive SHA-256 mismatch")
        if not source.get("raw_snapshot_id") or not source.get("source_url"):
            raise DecisionReplayError(f"{kind} archive provenance is incomplete")
    if seen != required:
        raise DecisionReplayError("provider, player metadata and manager-state archives are all required")

    provider = manifest.get("provider_snapshot")
    metadata_provenance = manifest.get("player_metadata_provenance")
    if not isinstance(provider, Mapping) or not isinstance(metadata_provenance, Mapping):
        raise DecisionReplayError("canonical provider or metadata provenance is missing")
    by_type = {row["source_type"]: row for row in sources}
    if provider.get("source", {}).get("raw_sha256") != by_type["provider_forecast"]["raw_sha256"]:
        raise DecisionReplayError("canonical provider snapshot is detached from its raw archive")
    if metadata_provenance.get("raw_sha256") != by_type["player_metadata"]["raw_sha256"]:
        raise DecisionReplayError("canonical metadata is detached from its raw archive")


def replay_frozen_decision(
    evidence_bundle: Mapping[str, Any],
    frozen_output: Mapping[str, Any],
    *,
    software_commit: str,
) -> dict[str, Any]:
    if not isinstance(frozen_output, Mapping):
        raise DecisionReplayError("frozen recommendation must be an object")
    candidate = frozen_output.get("evaluation_candidate")
    if not isinstance(candidate, Mapping) or candidate.get("software_commit") != software_commit:
        raise DecisionReplayError("replay software commit does not match the frozen decision commit")
    if frozen_output.get("manager_team_id") != candidate.get("manager_team_id"):
        raise DecisionReplayError("frozen manager identity mismatch")
    if frozen_output.get("target_gameweek") != candidate.get("target_gameweek"):
        raise DecisionReplayError("frozen Gameweek mismatch")
    if not isinstance(evidence_bundle, Mapping) or len(evidence_bundle) != 1:
        raise DecisionReplayError("evidence bundle must contain exactly one Gameweek manifest")
    key, manifest = next(iter(evidence_bundle.items()))
    if not isinstance(manifest, Mapping):
        raise DecisionReplayError("Gameweek manifest must be an object")
    if str(candidate.get("target_gameweek")) != str(key):
        raise DecisionReplayError("capture manifest and frozen decision Gameweek differ")
    if manifest.get("manager_team_id") != candidate.get("manager_team_id"):
        raise DecisionReplayError("capture manifest and frozen decision manager differ")
    _verify_archives(manifest)

    replayed = run_predeadline_m3_decision(
        evidence_bundle, software_commit=software_commit
    )
    expected_decision = frozen_output.get("frozen_decision")
    actual_decision = replayed.get("frozen_decision")
    if _canonical(actual_decision) != _canonical(expected_decision):
        raise DecisionReplayError("replayed frozen decision differs from the archived decision")
    if _canonical(replayed.get("recommendation")) != _canonical(frozen_output.get("recommendation")):
        raise DecisionReplayError("replayed recommendation differs from the archived recommendation")

    decision_hash = hashlib.sha256(_canonical(actual_decision).encode("utf-8")).hexdigest()
    return {
        "status": "PASSED",
        "replay_type": "DETERMINISTIC_CANONICAL_INPUT_REEXECUTION",
        "manager_team_id": candidate["manager_team_id"],
        "target_gameweek": candidate["target_gameweek"],
        "software_commit": software_commit,
        "decision_sha256": actual_decision["decision_sha256"],
        "replayed_payload_sha256": decision_hash,
        "recommendation_match": True,
        "frozen_decision_match": True,
        "raw_archive_hashes_verified": True,
        "release_eligible": False,
        "limitations": [
            "Replay uses the canonical normalized inputs stored in the capture manifest.",
            "Raw-source-to-normalized-input reconstruction is not established by this replay alone.",
            "A successful replay proves deterministic reproduction, not forecast accuracy or decision value.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_bundle", type=Path)
    parser.add_argument("frozen_recommendation", type=Path)
    parser.add_argument("--software-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bundle = json.loads(args.evidence_bundle.read_text(encoding="utf-8"))
    frozen = json.loads(args.frozen_recommendation.read_text(encoding="utf-8"))
    result = replay_frozen_decision(bundle, frozen, software_commit=args.software_commit)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
