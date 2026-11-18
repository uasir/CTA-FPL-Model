#!/usr/bin/env python3
"""Build an exploratory FPL points covariance panel from Onside's CC BY 4.0 ledger.

Only realized actual_points are used. Provider forecasts are never used as model
features or targets. Incomplete gameweeks and incomplete player panels are not
zero-filled. This is a descriptive risk research artifact, not production CoVar.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from estimate_fpl_covariance import estimate_covariance, write_outputs

SOURCE_URL = "https://onsidearena.com/data/graded-predictions.csv"
SOURCE_LICENSE = "Provider-stated CC BY 4.0; attribute Onside Arena and link to https://onsidearena.com/data"


def prepare_covariance_inputs(
    rows: list[dict[str, Any]], *, window_size: int = 10
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if window_size < 2:
        raise ValueError("window_size must be at least 2")
    if not rows:
        raise ValueError("Onside ledger is empty")

    by_gw: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        try:
            gw = int(row["gw"])
            player_id = str(row["player_id"]).strip()
        except (KeyError, TypeError, ValueError):
            raise ValueError("every row requires integer gw and player_id")
        if not player_id:
            raise ValueError("player_id cannot be blank")
        by_gw[gw].append(row)

    completed: list[int] = []
    unfinished: list[int] = []
    partial: list[int] = []
    for gw, gw_rows in sorted(by_gw.items()):
        scored = [str(row.get("actual_points", "")).strip() != "" for row in gw_rows]
        if all(scored):
            completed.append(gw)
        elif not any(scored):
            unfinished.append(gw)
        else:
            partial.append(gw)

    if partial:
        # A partially graded gameweek is not a valid covariance observation panel.
        # Exclude the entire GW rather than mixing finalized and provisional scores.
        pass
    selected_gws = completed[-window_size:]
    if len(selected_gws) < 2:
        raise ValueError(
            f"need at least two fully graded gameweeks; found {len(selected_gws)}"
        )

    prepared: list[dict[str, Any]] = []
    players: dict[str, dict[str, Any]] = {}
    seen: set[tuple[str, int]] = set()
    for gw in selected_gws:
        for row in by_gw[gw]:
            player_id = str(row["player_id"]).strip()
            key = (player_id, gw)
            if key in seen:
                raise ValueError(f"duplicate player-gameweek key: {player_id} GW{gw}")
            seen.add(key)
            try:
                points = float(row["actual_points"])
            except (TypeError, ValueError):
                raise ValueError(f"invalid actual_points for {player_id} GW{gw}")
            prepared.append({
                "season": "2026-27",
                "fpl_element_id": player_id,
                "gameweek": str(gw),
                "target_total_points": points,
            })
            name = str(row.get("player_name") or "")
            if player_id not in players or not players[player_id].get("web_name"):
                players[player_id] = {
                    "fpl_element_id": player_id,
                    "web_name": name,
                    "position": "",
                }

    metadata = {
        "selected_completed_gameweeks": selected_gws,
        "completed_gameweeks_available": completed,
        "unfinished_gameweeks_excluded": unfinished,
        "partially_graded_gameweeks_excluded": partial,
        "rows_in_selected_gameweeks": len(prepared),
        "unique_players_in_selected_gameweeks": len(players),
        "identity_key": "Onside player_id, previously reconciled 608/608 against official FPL element IDs in audit run 44257909685",
        "target_field": "actual_points only",
        "provider_forecasts_used": False,
        "missingness_policy": "Exclude entire partially graded gameweeks and exclude players missing any selected gameweek; never fill missing points with zero.",
    }
    return prepared, list(players.values()), metadata



def rolling_correlation_stability(
    rows: list[dict[str, Any]], gameweeks: list[int]
) -> dict[str, Any]:
    """Compare pairwise player correlations across two adjacent time windows."""
    midpoint = len(gameweeks) // 2
    first_gws = gameweeks[:midpoint]
    second_gws = gameweeks[midpoint:]
    if len(first_gws) < 2 or len(second_gws) < 2:
        return {
            "status": "NOT_ENOUGH_GAMEWEEKS",
            "first_window": first_gws,
            "second_window": second_gws,
            "players": 0,
            "pairs": 0,
            "correlation_of_correlations": None,
            "median_absolute_correlation_change": None,
            "mean_absolute_correlation_change": None,
        }

    values: dict[str, dict[int, float]] = defaultdict(dict)
    for row in rows:
        values[str(row["fpl_element_id"])][int(row["gameweek"])] = float(row["target_total_points"])

    def corr(x: list[float], y: list[float]) -> float | None:
        if len(x) != len(y) or len(x) < 2:
            return None
        mx, my = sum(x) / len(x), sum(y) / len(y)
        dx = [v - mx for v in x]
        dy = [v - my for v in y]
        xx = sum(v * v for v in dx)
        yy = sum(v * v for v in dy)
        if xx <= 0 or yy <= 0:
            return None
        return sum(a * b for a, b in zip(dx, dy)) / (xx * yy) ** 0.5

    eligible = []
    for player_id, player_values in values.items():
        if not all(gw in player_values for gw in gameweeks):
            continue
        first = [player_values[gw] for gw in first_gws]
        second = [player_values[gw] for gw in second_gws]
        if corr(first, first) is not None and corr(second, second) is not None:
            eligible.append((player_id, first, second))

    first_correlations = []
    second_correlations = []
    absolute_changes = []
    for i, (_, first_x, second_x) in enumerate(eligible):
        for _, first_y, second_y in eligible[i + 1:]:
            r1 = corr(first_x, first_y)
            r2 = corr(second_x, second_y)
            if r1 is None or r2 is None:
                continue
            first_correlations.append(r1)
            second_correlations.append(r2)
            absolute_changes.append(abs(r1 - r2))

    corr_of_corr = corr(first_correlations, second_correlations)
    absolute_changes.sort()
    if absolute_changes:
        mid = len(absolute_changes) // 2
        median_change = (
            absolute_changes[mid] if len(absolute_changes) % 2
            else (absolute_changes[mid - 1] + absolute_changes[mid]) / 2
        )
        mean_change = sum(absolute_changes) / len(absolute_changes)
    else:
        median_change = mean_change = None

    return {
        "status": "EXPLORATORY_STABILITY_DIAGNOSTIC",
        "first_window": first_gws,
        "second_window": second_gws,
        "players": len(eligible),
        "pairs": len(absolute_changes),
        "correlation_of_correlations": round(corr_of_corr, 8) if corr_of_corr is not None else None,
        "median_absolute_correlation_change": round(median_change, 8) if median_change is not None else None,
        "mean_absolute_correlation_change": round(mean_change, 8) if mean_change is not None else None,
        "interpretation": "A short-window stability diagnostic only; each half-window has few observations and should not be treated as a formal stationarity test.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=SOURCE_URL)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--window-size", type=int, default=20)
    parser.add_argument("--shrinkage", type=float, default=0.5)
    args = parser.parse_args()

    request = urllib.request.Request(
        args.url,
        headers={"User-Agent": "CTA-FPL-Model Onside CC-BY-4.0 covariance research/1.0"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        raw = response.read()
    decoded = raw.decode("utf-8-sig")
    source_rows = list(csv.DictReader(io.StringIO(decoded)))
    prepared, players, source_meta = prepare_covariance_inputs(
        source_rows, window_size=args.window_size
    )
    selected_window_size = len(source_meta["selected_completed_gameweeks"])
    pairs, summaries, report = estimate_covariance(
        prepared, players, shrinkage=args.shrinkage, window_size=selected_window_size
    )
    stability = rolling_correlation_stability(
        prepared, source_meta["selected_completed_gameweeks"]
    )
    report.update({
        "rolling_correlation_stability": stability,
        "source_url": args.url,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_license_and_attribution": SOURCE_LICENSE,
        "source_panel": source_meta,
        "status": "EXPLORATORY_ONSIDE_ACTUALS_ONLY",
        "production_use": False,
        "guardrails": [
            "Only realized actual_points were used; Onside and FPL forecast columns were ignored.",
            "This does not train or validate CTA expected-points forecasts.",
            "The panel covers a limited subset of players and only the available completed gameweeks.",
            "Ten gameweeks provide a noisy dependence estimate; do not activate CoVar in personal_squad from this artifact alone.",
            "Use the covariance only as a research diagnostic until out-of-sample, time-ordered validation is completed.",
            "Attribution required: Onside Arena, https://onsidearena.com/data (provider-stated CC BY 4.0).",
        ],
    })
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_outputs(pairs, summaries, report, args.out_dir)
    (args.out_dir / "onside_covariance_source_audit.json").write_text(
        json.dumps(source_meta, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "source_sha256": report["source_sha256"],
        "selected_gameweeks": source_meta["selected_completed_gameweeks"],
        "players_in_window": report["players_in_window"],
        "complete_panel_players": report["complete_panel_players"],
        "covariance_players": report["covariance_players"],
        "rolling_correlation_stability": stability,
        "excluded_incomplete_players": report["excluded_incomplete_players"],
        "excluded_zero_variance_players": report["excluded_zero_variance_players"],
        "pairwise_estimates_including_diagonal": report["pairwise_estimates_including_diagonal"],
        "matrix_rank_upper_bound_before_shrinkage": report["matrix_rank_upper_bound_before_shrinkage"],
        "guardrails": report["guardrails"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
