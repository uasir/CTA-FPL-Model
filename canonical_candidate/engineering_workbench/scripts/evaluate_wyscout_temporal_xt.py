#!/usr/bin/env python3
"""Experimental time-horizon xT for normalized Wyscout CTA events.

This is a research-only, event-based approximation of temporal xT. It estimates
shot/goal probability within fixed time horizons from action start zones. It
uses inferred possessions and must not be treated as validated possession truth.
"""
from __future__ import annotations

import argparse
import json
import math
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def _time_seconds(event):
    return int(event.get("minute", 0)) * 60.0 + float(event.get("second", 0.0))


def _zone(location, nx=12, ny=8):
    if not isinstance(location, list) or len(location) != 2:
        return None
    try:
        x, y = float(location[0]), float(location[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= 120 and 0 <= y <= 80):
        return None
    return min(nx - 1, int(x / 120 * nx)), min(ny - 1, int(y / 80 * ny))


def _goal(event):
    shot = event.get("shot") or {}
    outcome = (shot.get("outcome") or {}).get("name", "")
    return str(outcome).casefold() == "goal"


def _shot(event):
    return str((event.get("type") or {}).get("name", "")).casefold() == "shot"


def build_temporal_samples(events, match_dates, horizons=(5, 10, 15, 30)):
    """Create action-state labels using only later events in the same inferred possession."""
    grouped = defaultdict(list)
    for event in events:
        match_id = str(event.get("_match_id", event.get("_provider_match_id", "")))
        if match_id not in match_dates:
            continue
        try:
            possession = str(event["possession"])
            team = str((event.get("possession_team") or {}).get("name", ""))
            period = int(event["period"])
        except (KeyError, TypeError, ValueError):
            continue
        grouped[(match_id, period, possession, team)].append(event)

    samples = []
    action_types = {"pass", "carry", "duel"}
    for key, rows in grouped.items():
        rows.sort(key=lambda row: (_time_seconds(row), int(row.get("_event_index", 0))))
        for index, event in enumerate(rows):
            kind = str((event.get("type") or {}).get("name", "")).casefold()
            if kind not in action_types:
                continue
            zone = _zone(event.get("location"))
            if zone is None:
                continue
            now = _time_seconds(event)
            future = [
                (candidate, _time_seconds(candidate) - now)
                for candidate in rows[index + 1:]
                if _time_seconds(candidate) > now
            ]
            sample = {
                "match_id": key[0],
                "match_date": match_dates[key[0]],
                "zone": zone,
                "action_type": kind,
                "seconds_to_next_event": future[0][1] if future else None,
                "labels": {},
            }
            for horizon in horizons:
                within = [candidate for candidate, delta in future if delta <= horizon]
                sample["labels"][str(horizon)] = {
                    "shot": int(any(_shot(candidate) for candidate in within)),
                    "goal": int(any(_goal(candidate) for candidate in within)),
                }
            samples.append(sample)
    return samples


def _auc(labels, scores):
    positives = sum(labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return None
    pairs = sorted(zip(scores, labels), key=lambda item: item[0])
    rank_sum = 0.0
    index = 0
    while index < len(pairs):
        end = index + 1
        while end < len(pairs) and pairs[end][0] == pairs[index][0]:
            end += 1
        average_rank = ((index + 1) + end) / 2.0
        rank_sum += average_rank * sum(label for _, label in pairs[index:end])
        index = end
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def _brier(labels, scores):
    return sum((p - y) ** 2 for y, p in zip(labels, scores)) / len(labels) if labels else None


def evaluate(samples, train_fraction=0.7, horizons=(5, 10, 15, 30), nx=12, ny=8):
    dated = sorted({sample["match_date"] for sample in samples})
    if len(dated) < 5:
        raise ValueError("At least five dated matches are required for chronological evaluation")
    split = max(1, min(len(dated) - 1, int(len(dated) * train_fraction)))
    cutoff = dated[split]
    train = [s for s in samples if s["match_date"] < cutoff]
    test = [s for s in samples if s["match_date"] >= cutoff]
    if len(train) < 100 or len(test) < 30:
        raise ValueError("Temporal xT evaluation requires at least 100 train and 30 test action samples")

    report = {
        "status": "PASS_TEMPORAL_XT_EXPERIMENT",
        "model": "zone_smoothed_temporal_xt",
        "model_version": "0.1.0",
        "train_matches": len({s["match_id"] for s in train}),
        "test_matches": len({s["match_id"] for s in test}),
        "train_action_samples": len(train),
        "test_action_samples": len(test),
        "chronological_cutoff_match_date": cutoff,
        "horizons_seconds": list(horizons),
        "horizon_metrics": {},
        "fit_policy": "All zone rates and smoothing are fitted on training matches only.",
        "possession_quality": "INFERRED_NOT_MANUALLY_VALIDATED",
        "decision_use_status": "RESEARCH_ONLY_NOT_IN_BASELINE",
        "cta_decision_weight_applied": False,
    }
    for horizon in horizons:
        key = str(horizon)
        zone_counts = defaultdict(lambda: {"shot": 0, "goal": 0, "n": 0})
        global_counts = {"shot": 0, "goal": 0, "n": 0}
        for sample in train:
            labels = sample["labels"][key]
            cell = zone_counts[sample["zone"]]
            cell["n"] += 1
            global_counts["n"] += 1
            for target in ("shot", "goal"):
                cell[target] += labels[target]
                global_counts[target] += labels[target]
        # Beta(1, 19) smoothing stabilizes rare goal labels; shot rate uses Beta(1, 9).
        priors = {"shot": (1.0, 9.0), "goal": (1.0, 19.0)}
        zone_probs = {}
        for zone, counts in zone_counts.items():
            zone_probs[zone] = {
                target: (counts[target] + priors[target][0]) /
                        (counts["n"] + sum(priors[target]))
                for target in ("shot", "goal")
            }
        labels, scores, baseline_scores = [], [], []
        for sample in test:
            y = sample["labels"][key]["goal"]
            labels.append(y)
            scores.append(zone_probs.get(sample["zone"], {
                "goal": (global_counts["goal"] + 1.0) / (global_counts["n"] + 20.0)
            })["goal"])
            baseline_scores.append((global_counts["goal"] + 1.0) / (global_counts["n"] + 20.0))
        report["horizon_metrics"][key] = {
            "test_goal_rate": sum(labels) / len(labels),
            "temporal_xt_brier": _brier(labels, scores),
            "global_rate_baseline_brier": _brier(labels, baseline_scores),
            "temporal_xt_auc": _auc(labels, scores),
            "zone_count_train": len(zone_probs),
            "training_goal_events_within_horizon": global_counts["goal"],
            "training_shot_events_within_horizon": global_counts["shot"],
            "calibration_status": "EMPIRICAL_ZONE_RATE_ONLY_NOT_FULLY_CALIBRATED",
        }
    report["limitations"] = [
        "Possession IDs are inferred by the adapter and have not been manually validated against video.",
        "This event-only model has no tracking, pressure, receiver identity or xG.",
        "A zone-smoothed horizon model is an initial temporal benchmark, not a full semi-Markov transition/duration model.",
        "The held-out labels inherit the source's event tagging and possession segmentation limitations.",
        "This experiment is not a production FPL points forecast."
    ]
    return report


def _match_dates(matches_zip):
    with zipfile.ZipFile(matches_zip) as archive:
        candidates = [name for name in archive.namelist()
                      if Path(name).name.lower().startswith("matches_england")]
        if len(candidates) != 1:
            raise ValueError(f"Expected exactly one matches_England JSON; found {candidates[:5]}")
        matches = json.load(archive.open(candidates[0]))
    result = {}
    for match in matches:
        match_id = str(match.get("wyId"))
        raw = str(match.get("dateutc") or match.get("date") or "")[:10]
        try:
            datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            continue
        result[match_id] = raw
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--matches-zip", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    events = json.loads(args.events.read_text(encoding="utf-8"))
    samples = build_temporal_samples(events, _match_dates(args.matches_zip))
    report = evaluate(samples)
    report["normalized_event_rows"] = len(events)
    report["temporal_action_samples"] = len(samples)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
