#!/usr/bin/env python3
"""Rebuild the deterministic 3895320 test fixture from the verified pilot files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

WORKBENCH = Path(__file__).resolve().parents[2]
CANDIDATE = WORKBENCH.parent
FIXTURE = Path(__file__).resolve().parent / "3895320"
MATCH_ID = "3895320"
EVENT_RANGES = ((1, 40), (91, 139), (259, 274))
EXPECTED_BLOBS = {
    "events": "2f4cc3c3f8173e923485db7e0c814980080ecdb4",
    "three_sixty": "80cd519d37fcea4681e38a3806b69ae9f9af9fa0",
}


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    payload = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    return hashlib.sha1(payload).hexdigest()


def in_selected_range(index: int) -> bool:
    return any(start <= index <= end for start, end in EVENT_RANGES)


def is_receipt(event: dict) -> bool:
    return (event.get("type") or {}).get("name") in {"Ball Receipt*", "Ball Receipt"}


def main() -> None:
    event_path = CANDIDATE / "data" / "events" / f"{MATCH_ID}.json"
    frame_path = CANDIDATE / "data" / "three-sixty" / f"{MATCH_ID}.json"
    actual_blobs = {
        "events": git_blob_sha1(event_path),
        "three_sixty": git_blob_sha1(frame_path),
    }
    if actual_blobs != EXPECTED_BLOBS:
        raise SystemExit(f"Verified pilot source hashes do not match: {actual_blobs}")

    source_events = json.loads(event_path.read_text(encoding="utf-8"))
    source_frames = json.loads(frame_path.read_text(encoding="utf-8"))
    events = [
        event for event in source_events
        if isinstance(event, dict) and in_selected_range(int(event.get("index", -1)))
    ]
    event_ids = {event.get("id") for event in events}
    frames = [
        frame for frame in source_frames
        if isinstance(frame, dict) and frame.get("event_uuid") in event_ids
    ]
    missing_location_ids = [
        event["id"] for event in events
        if event.get("location") is None and event.get("id") is not None
    ]
    shot_ids = [
        event["id"] for event in events
        if (event.get("type") or {}).get("name") == "Shot" and event.get("id") is not None
    ]
    pressured_receipt_ids = [
        event["id"] for event in events
        if is_receipt(event) and event.get("under_pressure") and event.get("player", {}).get("name")
    ]
    out_of_bounds_samples = []
    for frame in frames:
        for player in frame.get("freeze_frame", []):
            location = player.get("location") if isinstance(player, dict) else None
            if (
                isinstance(location, list)
                and len(location) >= 2
                and isinstance(location[0], (int, float))
                and isinstance(location[1], (int, float))
                and (location[0] < 0 or location[0] > 120 or location[1] < 0 or location[1] > 80)
            ):
                out_of_bounds_samples.append({
                    "event_uuid": frame.get("event_uuid"),
                    "location": location,
                })
                if len(out_of_bounds_samples) == 3:
                    break
        if len(out_of_bounds_samples) == 3:
            break

    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "events").mkdir(parents=True, exist_ok=True)
    (FIXTURE / "three-sixty").mkdir(parents=True, exist_ok=True)
    (FIXTURE / "events" / f"{MATCH_ID}.json").write_text(
        json.dumps(events, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (FIXTURE / "three-sixty" / f"{MATCH_ID}.json").write_text(
        json.dumps(frames, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "fixture": "StatsBomb Open Data real-pilot subset; exact records copied from the verified source JSON after deterministic selection.",
        "match_id": MATCH_ID,
        "source_git_blob_sha1": actual_blobs,
        "selection": {
            "event_index_ranges_inclusive": [list(pair) for pair in EVENT_RANGES],
            "event_count": len(events),
            "frame_count": len(frames),
        },
        "edge_cases": {
            "missing_location_event_ids": missing_location_ids,
            "shot_event_ids": shot_ids,
            "pressured_receipt_event_ids": pressured_receipt_ids,
            "out_of_bounds_360_samples": out_of_bounds_samples,
        },
        "provenance_note": "These are actual event and 360 records from match 3895320, not generated or synthetic rows.",
    }
    (FIXTURE / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "events": len(events),
        "frames": len(frames),
        "pressured_receipts": len(pressured_receipt_ids),
        "source_git_blob_sha1": actual_blobs,
    }, indent=2))


if __name__ == "__main__":
    main()
