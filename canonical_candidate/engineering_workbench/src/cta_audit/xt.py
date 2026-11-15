from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any
from .audit import load_rows, is_null, parse_number


def cell_index(x: float, y: float, pitch_length: float, pitch_width: float, nx: int, ny: int) -> tuple[int, int]:
    # Coordinates are attacking-direction normalized, with origin at the attacking team's own goal line.
    x = min(max(x, 0.0), pitch_length - 1e-12)
    y = min(max(y, 0.0), pitch_width - 1e-12)
    return int(x / pitch_length * nx), int(y / pitch_width * ny)


def train_xt(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    nx, ny = int(config["grid_x"]), int(config["grid_y"])
    length, width = float(config["pitch_length"]), float(config["pitch_width"])
    max_iter, tol = int(config.get("max_iterations", 10000)), float(config.get("convergence_tolerance", 1e-12))
    cells = nx * ny
    attempts = [0] * cells
    shots = [0] * cells
    goals = [0] * cells
    moves = [0] * cells
    transitions = [[0] * cells for _ in range(cells)]
    excluded = {"excluded_missing_coordinates": 0, "excluded_unknown_action": 0, "excluded_invalid_action": 0}
    action_field = config.get("action_type_field", "action_type")
    outcome_field = config.get("outcome_field", "outcome")
    start_x, start_y = config.get("start_x_field", "x"), config.get("start_y_field", "y")
    end_x, end_y = config.get("end_x_field", "end_x"), config.get("end_y_field", "end_y")
    shot_actions = set(config.get("shot_actions", ["shot"]))
    move_actions = set(config.get("move_actions", ["pass", "carry"]))
    success_values = set(config.get("success_values", ["complete", "successful", "success", "won"]))
    goal_values = set(config.get("goal_values", ["goal"]))
    for row in rows:
        action = str(row.get(action_field, "")).strip().lower()
        outcome = str(row.get(outcome_field, "")).strip().lower()
        if action not in shot_actions and action not in move_actions:
            excluded["excluded_unknown_action"] += 1
            continue
        if is_null(row.get(start_x)) or is_null(row.get(start_y)):
            excluded["excluded_missing_coordinates"] += 1
            continue
        try:
            sx, sy = parse_number(row[start_x]), parse_number(row[start_y])
            ix, iy = cell_index(sx, sy, length, width, nx, ny)
        except (ValueError, TypeError, OverflowError):
            excluded["excluded_invalid_action"] += 1
            continue
        source = iy * nx + ix
        attempts[source] += 1
        if action in shot_actions:
            shots[source] += 1
            if outcome in goal_values: goals[source] += 1
            continue
        if outcome not in success_values:
            continue
        if is_null(row.get(end_x)) or is_null(row.get(end_y)):
            excluded["excluded_missing_coordinates"] += 1
            continue
        try:
            ex, ey = parse_number(row[end_x]), parse_number(row[end_y])
            jx, jy = cell_index(ex, ey, length, width, nx, ny)
        except (ValueError, TypeError, OverflowError):
            excluded["excluded_invalid_action"] += 1
            continue
        target = jy * nx + jx
        moves[source] += 1
        transitions[source][target] += 1
    values = [0.0] * cells
    converged = False
    iteration = 0
    for iteration in range(1, max_iter + 1):
        updated = [0.0] * cells
        delta = 0.0
        for i in range(cells):
            if attempts[i] == 0:
                continue
            p_shot = shots[i] / attempts[i]
            p_move = moves[i] / attempts[i]
            shot_value = (goals[i] / shots[i]) if shots[i] else 0.0
            move_value = 0.0
            if moves[i]:
                move_value = sum(transitions[i][j] / moves[i] * values[j] for j in range(cells))
            updated[i] = p_shot * shot_value + p_move * move_value
            delta = max(delta, abs(updated[i] - values[i]))
        values = updated
        if delta < tol:
            converged = True
            break
    grid = [[values[y * nx + x] for x in range(nx)] for y in range(ny)]
    return {
        "model": "empirical_grid_xt_baseline",
        "model_version": "0.1.0",
        "assumptions": [
            "All coordinates are normalized to the attacking direction.",
            "Each canonical row represents one action attempt.",
            "Shots terminate the action; goals are identified by configured outcome labels.",
            "Only configured successful passes/carries contribute transitions.",
            "Unsuccessful moves and other action types contribute zero continuation value.",
            "Unobserved cells have value zero; no smoothing or prior is applied in this baseline."
        ],
        "config": {k: v for k, v in config.items() if k not in {"notes"}},
        "counts": {"actions": sum(attempts), "shots": sum(shots), "goals": sum(goals), "successful_moves": sum(moves), "observed_cells": sum(n > 0 for n in attempts)},
        "excluded": excluded,
        "solver": {"iterations": iteration, "converged": converged, "tolerance": tol},
        "grid": grid
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Train a transparent empirical grid-based xT baseline")
    ap.add_argument("--input", required=True, type=Path, help="Canonical action CSV/JSON/JSONL")
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("reports/xt"))
    args = ap.parse_args()
    rows = load_rows(args.input)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    result = train_xt(rows, config)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "xt_model.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"model": result["model"], "actions": result["counts"]["actions"], "converged": result["solver"]["converged"], "iterations": result["solver"]["iterations"]}))
    return 0 if result["solver"]["converged"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
