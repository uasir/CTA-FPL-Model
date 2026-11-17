#!/usr/bin/env python3
"""Validate per-match event processing and StatsBomb 360 event linkage."""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def audit_quality(manifest: dict, python_root: Path) -> dict:
    matches = manifest.get("matches") or []
    expected_ids = [str(item["match_id"]) for item in matches]
    if len(expected_ids) != len(set(expected_ids)):
        raise ValueError("Manifest contains duplicate match IDs")
    actual_ids = sorted(path.name for path in python_root.iterdir() if path.is_dir()) if python_root.exists() else []
    missing = sorted(set(expected_ids) - set(actual_ids))
    extra = sorted(set(actual_ids) - set(expected_ids))
    results = {}
    failures = []
    for item in matches:
        match_id = str(item["match_id"])
        audit_path = python_root / match_id / "audit.json"
        if not audit_path.exists():
            results[match_id] = {"status": "FAIL", "reason": "missing Python audit.json"}
            failures.append(match_id)
            continue
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        events_processed = int(audit.get("events_processed") or 0)
        link = audit.get("statsbomb_360_audit") or {}
        frames = int(link.get("frames") or 0)
        frame_uuids = int(link.get("frames_with_event_uuid") or 0)
        matched = int(link.get("matched_frame_uuids") or 0)
        unmatched = int(link.get("unmatched_frame_uuids") or 0)
        duplicates = int(link.get("duplicate_frame_event_uuids") or 0)
        join_rate = link.get("frame_to_event_join_rate")
        has_360 = bool(item.get("has_360"))
        has_source = bool(item.get("has_360_source", has_360))
        base_reasons = [] if events_processed > 0 else ["no events processed"]
        if has_360:
            reasons = list(base_reasons)
            if frames <= 0: reasons.append("usable 360 source produced no frames")
            if frame_uuids != frames: reasons.append("one or more frames lack event_uuid")
            if matched != frame_uuids: reasons.append("not all frame UUIDs match this match's events")
            if unmatched != 0: reasons.append("unmatched frame UUIDs are present")
            if duplicates != 0: reasons.append("duplicate frame UUIDs are present")
            if join_rate != 1.0: reasons.append("frame-to-event join rate is not 1.0")
            status = "FAIL" if reasons else "PASS"
            row = {"status": status, "source_status": "usable", "events_processed": events_processed,
                   "frames": frames, "matched": matched, "unmatched": unmatched,
                   "duplicate_frame_uuids": duplicates, "frame_to_event_join_rate": join_rate,
                   "reasons": reasons}
        elif has_source:
            reason = str(item.get("three_sixty_exclusion_reason", "")).strip()
            reasons = list(base_reasons)
            if not reason: reasons.append("excluded source has no documented reason")
            if frames != 0: reasons.append("excluded source was unexpectedly processed")
            status = "FAIL" if reasons else "EXCLUDED_INVALID_SOURCE"
            row = {"status": status, "source_status": "present_but_excluded",
                   "events_processed": events_processed, "frames": frames, "matched": matched,
                   "unmatched": unmatched, "duplicate_frame_uuids": duplicates,
                   "frame_to_event_join_rate": join_rate, "exclusion_reason": reason, "reasons": reasons}
        else:
            reasons = list(base_reasons)
            if frames != 0: reasons.append("360 frames processed although no source is available")
            status = "FAIL" if reasons else "NOT_AVAILABLE"
            row = {"status": status, "source_status": "not_available", "events_processed": events_processed,
                   "frames": frames, "matched": matched, "unmatched": unmatched,
                   "duplicate_frame_uuids": duplicates, "frame_to_event_join_rate": join_rate,
                   "reasons": reasons}
        results[match_id] = row
        if status == "FAIL": failures.append(match_id)
    if missing or extra:
        failures.extend(missing)
        failures.extend(extra)
    counts = {key: sum(row.get("status") == key for row in results.values())
              for key in ("PASS", "EXCLUDED_INVALID_SOURCE", "NOT_AVAILABLE", "FAIL")}
    return {
        "status": "FAIL" if failures else "PASS_WITH_EXPLICIT_EXCLUSIONS" if counts["EXCLUDED_INVALID_SOURCE"] else "PASS",
        "source_commit": (manifest.get("source") or {}).get("commit_sha"),
        "matches_expected": len(expected_ids),
        "matches_processed": len(actual_ids),
        "missing_match_audits": missing,
        "unexpected_match_audits": extra,
        "counts": counts,
        "failures": sorted(set(failures)),
        "matches": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--python-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = audit_quality(manifest, args.python_root)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "data_quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# CTA multi-match source and 360 data-quality audit",
        "",
        f"**Status: {report['status']}**",
        "",
        f"- Matches: {report['matches_processed']}/{report['matches_expected']}",
        f"- Usable 360 sources passed: {report['counts']['PASS']}",
        f"- Present but explicitly excluded 360 sources: {report['counts']['EXCLUDED_INVALID_SOURCE']}",
        f"- 360 source unavailable: {report['counts']['NOT_AVAILABLE']}",
        f"- Data-quality failures: {report['counts']['FAIL']}",
        "",
    ]
    for match_id, row in report["matches"].items():
        detail = row.get("exclusion_reason") or "; ".join(row.get("reasons", [])) or f"{row.get('frames', 0)} frames"
        lines.append(f"- {match_id}: {row['status']} — {detail}")
    (args.out / "data_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "matches_expected", "matches_processed", "counts", "failures")}, indent=2))
    return 0 if report["status"] != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
