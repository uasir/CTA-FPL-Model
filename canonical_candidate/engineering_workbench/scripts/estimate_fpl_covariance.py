#!/usr/bin/env python3
"""Build an exploratory FPL player CoVar matrix from complete recent GW panels.

This is a descriptive risk layer, not a trained points model or a team optimizer.
Missing player-gameweek rows are not imputed: players without a complete window
are excluded so the sample covariance matrix is positive semidefinite by
construction. Zero-variance players are kept in the summary but excluded from
the covariance matrix. Off-diagonal covariance is shrunk toward zero for stability.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _sort_id(value: str) -> tuple[int, str]:
    return (0, f"{int(value):020d}") if value.isdigit() else (1, value)


def estimate_covariance(
    rows: list[dict[str, Any]],
    player_rows: list[dict[str, Any]],
    *,
    shrinkage: float = 0.5,
    window_size: int = 10,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Return pairwise estimates, player summaries, and a reproducible report."""
    if not 0.0 <= shrinkage <= 1.0:
        raise ValueError("shrinkage must be between 0 and 1")
    if window_size < 2:
        raise ValueError("window_size must be at least 2")
    if not rows:
        raise ValueError("input player-gameweek rows are empty")
    seasons = {str(row.get("season")) for row in rows if row.get("season")}
    if len(seasons) > 1:
        raise ValueError("input must contain exactly one FPL season")

    by_player: dict[str, dict[int, float]] = defaultdict(dict)
    all_gameweeks = sorted({int(row["gameweek"]) for row in rows})
    window = all_gameweeks[-window_size:]
    if len(window) < 2:
        raise ValueError("at least two gameweeks are required")

    seen: set[tuple[str, int]] = set()
    for row in rows:
        player_id = str(row["fpl_element_id"])
        gameweek = int(row["gameweek"])
        if gameweek not in window:
            continue
        key = (player_id, gameweek)
        if key in seen:
            raise ValueError(f"duplicate player-gameweek key: {player_id} GW{gameweek}")
        seen.add(key)
        points = number(row.get("target_total_points"))
        if points is None:
            raise ValueError(f"missing target_total_points for {player_id} GW{gameweek}")
        by_player[player_id][gameweek] = points

    all_player_ids = sorted(by_player, key=_sort_id)
    complete_ids = [
        player_id for player_id in all_player_ids
        if all(gw in by_player[player_id] for gw in window)
    ]
    excluded_ids = [player_id for player_id in all_player_ids if player_id not in set(complete_ids)]
    if len(complete_ids) < 2:
        raise ValueError("fewer than two players have a complete gameweek window")

    metadata = {str(row.get("fpl_element_id")): row for row in player_rows}
    values = {pid: [by_player[pid][gw] for gw in window] for pid in complete_ids}
    means = {pid: sum(values[pid]) / len(window) for pid in complete_ids}
    variances = {
        pid: sum((x - means[pid]) ** 2 for x in values[pid]) / (len(window) - 1)
        for pid in complete_ids
    }

    zero_variance = [pid for pid in complete_ids if variances[pid] == 0.0]
    covariance_ids = [pid for pid in complete_ids if variances[pid] > 0.0]
    if len(covariance_ids) < 2:
        raise ValueError("fewer than two complete-panel players have non-zero variance")

    player_summaries: list[dict[str, Any]] = []
    for pid in complete_ids:
        meta = metadata.get(pid, {})
        player_summaries.append({
            "fpl_element_id": pid,
            "web_name": meta.get("web_name", ""),
            "position": meta.get("position", ""),
            "gameweeks": len(window),
            "mean_points": round(means[pid], 8),
            "variance": round(variances[pid], 8),
            "standard_deviation": round(math.sqrt(max(0.0, variances[pid])), 8),
            "eligible_for_covariance": pid in set(covariance_ids),
        })

    pairs: list[dict[str, Any]] = []
    n = len(window)
    for i, player1 in enumerate(covariance_ids):
        x = values[player1]
        for player2 in covariance_ids[i:]:
            y = values[player2]
            cov = sum((a - means[player1]) * (b - means[player2]) for a, b in zip(x, y)) / (n - 1)
            denom = math.sqrt(max(0.0, variances[player1] * variances[player2]))
            corr = cov / denom if denom > 0 else None
            is_diagonal = player1 == player2
            shrunk_cov = cov if is_diagonal else cov * (1.0 - shrinkage)
            meta1 = metadata.get(player1, {})
            meta2 = metadata.get(player2, {})
            pairs.append({
                "player1_id": player1,
                "player1_name": meta1.get("web_name", ""),
                "player1_position": meta1.get("position", ""),
                "player2_id": player2,
                "player2_name": meta2.get("web_name", ""),
                "player2_position": meta2.get("position", ""),
                "n_gameweeks": n,
                "covariance": round(cov, 8),
                "correlation": round(corr, 8) if corr is not None else "",
                "shrunk_covariance": round(shrunk_cov, 8),
                "is_diagonal": is_diagonal,
            })

    off_diagonal_all = [row for row in pairs if not row["is_diagonal"]]
    off_diagonal_defined = [row for row in off_diagonal_all if row["correlation"] != ""]
    positive = sorted(off_diagonal_defined, key=lambda row: row["shrunk_covariance"], reverse=True)[:10]
    negative = sorted(off_diagonal_defined, key=lambda row: row["shrunk_covariance"])[:10]
    expected_cells = len(all_player_ids) * len(window)
    observed_cells = sum(len(by_player[pid]) for pid in all_player_ids)
    season = next((str(row.get("season")) for row in rows if row.get("season")), "")
    report = {
        "season": season,
        "status": "EXPLORATORY_ONLY",
        "model_trained": False,
        "point_in_time_status": "NOT_VERIFIED",
        "target": "historical FPL points covariance for portfolio CoVar analysis",
        "window_gameweeks": window,
        "window_size": n,
        "rows_in_window": observed_cells,
        "players_in_window": len(all_player_ids),
        "complete_panel_players": len(complete_ids),
        "covariance_players": len(covariance_ids),
        "excluded_zero_variance_players": len(zero_variance),
        "zero_variance_player_ids": zero_variance,
        "excluded_incomplete_players": len(excluded_ids),
        "excluded_player_ids": excluded_ids,
        "expected_player_gameweek_cells": expected_cells,
        "missing_player_gameweek_cells": expected_cells - observed_cells,
        "pairwise_estimates_including_diagonal": len(pairs),
        "off_diagonal_pairs_total": len(off_diagonal_all),
        "off_diagonal_pairs_with_defined_correlation": len(off_diagonal_defined),
        "method": "sample covariance across a complete-case player-gameweek panel",
        "shrinkage": {
            "type": "diagonal",
            "off_diagonal_multiplier": round(1.0 - shrinkage, 8),
            "parameter": shrinkage,
            "diagonal_unchanged": True,
            "positive_semidefinite_by_construction": True,
            "positive_definite_by_construction": bool(shrinkage > 0 and len(covariance_ids) >= 2),
        },
        "matrix_rank_upper_bound_before_shrinkage": max(0, n - 1),
        "matrix_rank_after_shrinkage": len(covariance_ids) if shrinkage > 0 else min(len(covariance_ids), max(0, n - 1)),
        "units": {
            "covariance": "FPL points squared",
            "correlation": "dimensionless",
        },
        "top_positive_covariance_pairs": positive,
        "top_negative_covariance_pairs": negative,
        "limitations": [
            f"Only {n} gameweeks are available in this rolling window; pairwise dependence estimates are noisy.",
            "The current official API snapshot may contain retrospective revisions to earlier gameweek statistics.",
            "Players missing any gameweek in the window are excluded; missing rows are not imputed as zero.",
            "Zero-variance players are excluded from the covariance matrix rather than treated as risk-free.",
            "This is a descriptive covariance layer, not an expected-points model, field-ownership model, or squad optimizer.",
            "Strict historical backtesting requires archived pre-deadline FPL snapshots.",
        ],
    }
    return pairs, player_summaries, report


def write_outputs(
    pairs: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    report: dict[str, Any],
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    pair_fields = [
        "player1_id", "player1_name", "player1_position",
        "player2_id", "player2_name", "player2_position",
        "n_gameweeks", "covariance", "correlation",
        "shrunk_covariance", "is_diagonal",
    ]
    with (out_dir / "fpl_covariance_pairs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=pair_fields)
        writer.writeheader()
        writer.writerows(pairs)

    summary_fields = [
        "fpl_element_id", "web_name", "position", "gameweeks",
        "mean_points", "variance", "standard_deviation", "eligible_for_covariance",
    ]
    with (out_dir / "fpl_player_variance_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows(summaries)

    ids = sorted(
        {pair["player1_id"] for pair in pairs} | {pair["player2_id"] for pair in pairs},
        key=_sort_id,
    )
    matrix = {pid: {} for pid in ids}
    for pair in pairs:
        p1, p2 = pair["player1_id"], pair["player2_id"]
        value = pair["shrunk_covariance"]
        matrix[p1][p2] = value
        matrix[p2][p1] = value
    with (out_dir / "fpl_covariance_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["fpl_element_id", *ids])
        writer.writeheader()
        for pid in ids:
            writer.writerow({"fpl_element_id": pid, **matrix[pid]})

    (out_dir / "fpl_covariance_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--players", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--shrinkage", type=float, default=0.5)
    parser.add_argument("--window-size", type=int, default=10)
    args = parser.parse_args()

    with args.input.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    with args.players.open(newline="", encoding="utf-8-sig") as handle:
        player_rows = list(csv.DictReader(handle))

    pairs, summaries, report = estimate_covariance(
        rows, player_rows, shrinkage=args.shrinkage, window_size=args.window_size
    )
    write_outputs(pairs, summaries, report, args.out_dir)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
