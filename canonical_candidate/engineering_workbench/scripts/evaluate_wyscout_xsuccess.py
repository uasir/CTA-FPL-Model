#!/usr/bin/env python3
"""Experimental xSuccess: contextual pass-completion probability.

Uses only Wyscout pre-action geometry and explicit accurate/inaccurate tags.
Unknown outcomes are excluded, not converted to failures. Research only.
"""
from __future__ import annotations

import argparse
import json
import math
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np


def _features(event):
    positions = event.get("positions") or []
    if len(positions) < 2:
        return None
    try:
        sx, sy = float(positions[0]["x"]), float(positions[0]["y"])
        ex, ey = float(positions[1]["x"]), float(positions[1]["y"])
    except (KeyError, TypeError, ValueError):
        return None
    values = (sx, sy, ex, ey)
    if not all(math.isfinite(v) and 0 <= v <= 100 for v in values):
        return None
    dx, dy = ex - sx, ey - sy
    distance = math.hypot(dx, dy)
    return [
        sx / 100.0, sy / 100.0, ex / 100.0, ey / 100.0,
        dx / 100.0, dy / 100.0, distance / math.sqrt(20000.0),
        max(dx, 0.0) / 100.0, float(ex >= 66.667),
        float(ex >= 80.0 and 20.0 <= ey <= 80.0),
    ]


def build_pass_samples(events, match_dates):
    samples = []
    for event in events:
        if str(event.get("eventName", "")).casefold() != "pass":
            continue
        tags = {int(tag["id"]) for tag in (event.get("tags") or [])
                if isinstance(tag, dict) and tag.get("id") is not None}
        if 1801 in tags:
            label = 1
        elif 1802 in tags:
            label = 0
        else:
            continue
        match_id = str(event.get("matchId", ""))
        if match_id not in match_dates:
            continue
        features = _features(event)
        if features is None:
            continue
        samples.append({
            "match_id": match_id,
            "match_date": match_dates[match_id],
            "features": features,
            "completed": label,
        })
    return samples


def _sigmoid(value):
    value = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def _standardize(train, other=None):
    train_array = np.asarray(train, dtype=float)
    means = train_array.mean(axis=0)
    scales = train_array.std(axis=0)
    scales = np.where(scales > 1e-10, scales, 1.0)
    train_scaled = (train_array - means) / scales
    other_scaled = None
    if other is not None:
        other_scaled = (np.asarray(other, dtype=float) - means) / scales
    return train_scaled, other_scaled, means, scales


def _fit_logistic(matrix, labels, l2=0.05, iterations=1000, learning_rate=0.08):
    matrix = np.asarray(matrix, dtype=float)
    labels = np.asarray(labels, dtype=float)
    weights = np.zeros(matrix.shape[1], dtype=float)
    intercept = 0.0
    count = len(labels)
    for step in range(iterations):
        logits = np.clip(intercept + matrix @ weights, -30.0, 30.0)
        probabilities = 1.0 / (1.0 + np.exp(-logits))
        errors = probabilities - labels
        rate = learning_rate / math.sqrt(1.0 + step / 250.0)
        intercept -= rate * float(errors.mean())
        weights -= rate * (matrix.T @ errors / count + l2 * weights)
    return intercept, weights

def _auc(labels, scores):
    positives, negatives = sum(labels), len(labels) - sum(labels)
    if not positives or not negatives:
        return None
    ranked = sorted(zip(scores, labels), key=lambda x: x[0])
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        end = i + 1
        while end < len(ranked) and ranked[end][0] == ranked[i][0]:
            end += 1
        rank_sum += ((i + 1 + end) / 2.0) * sum(y for _, y in ranked[i:end])
        i = end
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def _brier(labels, scores):
    return sum((y - p) ** 2 for y, p in zip(labels, scores)) / len(labels)


def evaluate(samples, train_fraction=0.7):
    dates = sorted({s["match_date"] for s in samples})
    if len(dates) < 5:
        raise ValueError("At least five dated matches are required")
    split = max(1, min(len(dates) - 1, int(len(dates) * train_fraction)))
    cutoff = dates[split]
    train = [s for s in samples if s["match_date"] < cutoff]
    test = [s for s in samples if s["match_date"] >= cutoff]
    if len(train) < 100 or len(test) < 30:
        raise ValueError("xSuccess needs at least 100 training and 30 test labelled passes")
    x_train, x_test, means, scales = _standardize(
        [s["features"] for s in train], [s["features"] for s in test]
    )
    y_train = [s["completed"] for s in train]
    y_test = [s["completed"] for s in test]
    weights = _fit_logistic(x_train, y_train)
    intercept, coefficients = weights
    logits = np.clip(intercept + x_test @ coefficients, -30.0, 30.0)
    predictions = (1.0 / (1.0 + np.exp(-logits))).tolist()
    base_rate = float(sum(y_train) / len(y_train))
    baseline = [base_rate] * len(y_test)
    bins = []
    for lower in (0.0, 0.2, 0.4, 0.6, 0.8):
        members = [(p, y) for p, y in zip(predictions, y_test)
                   if lower <= p < lower + 0.2 or (lower == 0.8 and p == 1.0)]
        bins.append({
            "probability_band": f"{lower:.1f}-{lower + 0.2:.1f}",
            "count": len(members),
            "mean_predicted": sum(p for p, _ in members) / len(members) if members else None,
            "observed_completion_rate": sum(y for _, y in members) / len(members) if members else None,
        })
    return {
        "status": "PASS_XSUCCESS_EXPERIMENT",
        "model": "regularized_logistic_pass_completion",
        "model_version": "0.1.0",
        "train_matches": len({s["match_id"] for s in train}),
        "test_matches": len({s["match_id"] for s in test}),
        "train_labelled_passes": len(train),
        "test_labelled_passes": len(test),
        "training_completion_rate": base_rate,
        "chronological_cutoff_match_date": cutoff,
        "test_metrics": {
            "brier": _brier(y_test, predictions),
            "base_rate_brier": _brier(y_test, baseline),
            "auc": _auc(y_test, predictions),
            "mean_predicted_completion": sum(predictions) / len(predictions),
            "observed_completion_rate": sum(y_test) / len(y_test),
            "calibration_bins": bins,
        },
        "features": ["start_x", "start_y", "end_x", "end_y", "delta_x", "delta_y",
                     "distance", "forward_progress", "final_third_destination",
                     "central_danger_zone_destination"],
        "fit_policy": "Feature scaling and model fitting use training matches only.",
        "unknown_outcome_policy": "Only explicit Wyscout accurate (1801) and inaccurate (1802) pass tags are labelled.",
        "decision_use_status": "RESEARCH_ONLY_NOT_IN_BASELINE",
        "cta_decision_weight_applied": False,
        "limitations": [
            "Pass completion is not equivalent to tactical success or value created.",
            "No receiver identity, pressure, defensive shape or tracking data is available.",
            "Calibration is assessed on one chronological holdout and requires multi-season replication.",
            "The model does not yet combine completion probability with temporal xT reward and failure cost."
        ],
    }


def _match_dates(path):
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if Path(n).name.lower().startswith("matches_england")]
        if len(names) != 1:
            raise ValueError(f"Expected exactly one matches_England JSON; found {names[:5]}")
        matches = json.load(archive.open(names[0]))
    result = {}
    for match in matches:
        match_id = str(match.get("wyId"))
        date = str(match.get("dateutc") or match.get("date") or "")[:10]
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            continue
        result[match_id] = date
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events-zip", type=Path, required=True)
    parser.add_argument("--matches-zip", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with zipfile.ZipFile(args.events_zip) as archive:
        names = [n for n in archive.namelist() if Path(n).name.lower().startswith("events_england")]
        if len(names) != 1:
            raise ValueError(f"Expected exactly one events_England JSON; found {names[:5]}")
        events = json.load(archive.open(names[0]))
    samples = build_pass_samples(events, _match_dates(args.matches_zip))
    report = evaluate(samples)
    report["labelled_pass_samples"] = len(samples)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
