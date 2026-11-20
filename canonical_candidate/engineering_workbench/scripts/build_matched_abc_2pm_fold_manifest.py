#!/usr/bin/env python3
"""Build a fail-closed, shared ABC/2PM player-Gameweek fold manifest.

The script validates the eligible ABC player-GW panel against the conventional
FPL fixture panel before producing any folds. It does not train or score models.
Player-level keys are represented in the manifest by hashes only.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, re
from collections import defaultdict
from pathlib import Path

TOLERANCE = 1e-9
SAME_ACROSS_DGW_FEATURES = (
    "prior_gw_points", "prior3_gw_points_avg", "prior5_gw_points_avg",
    "prior_gw_minutes", "prior3_gw_minutes_avg", "prior5_gw_minutes_avg",
    "prior5_appearance_rate", "season_appearance_rate", "season_to_date_minutes",
    "season_to_date_points_per90", "prior3_gw_xg_avg", "prior3_gw_xa_avg",
)

def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))

def number(value):
    if value in (None, ""): return None
    try: parsed = float(value)
    except (TypeError, ValueError): return None
    return parsed if math.isfinite(parsed) else None

def truth(value):
    return str(value).strip().lower() in {"true", "1", "yes"}

def season_key(value):
    raw = str(value or "").strip()
    match = re.fullmatch(r"(\d{4})[/\-](\d{2,4})", raw)
    if not match: raise ValueError(f"Unsupported season label: {raw!r}")
    return f"{match.group(1)}-{match.group(2)[-2:]}"

def row_key(row):
    gw = number(row.get("gameweek"))
    player = str(row.get("fpl_element_id") or "").strip()
    if gw is None or not gw.is_integer() or not player:
        raise ValueError("Each row needs a valid integer Gameweek and FPL element ID")
    return season_key(row.get("season")), player, int(gw)

def parse_fixture_ids(value):
    if isinstance(value, list): values = value
    elif isinstance(value, str):
        try: values = json.loads(value)
        except json.JSONDecodeError as exc: raise ValueError("ABC fixture_ids must be a JSON array") from exc
    else: raise ValueError("ABC fixture_ids are missing")
    if not isinstance(values, list) or not values: raise ValueError("ABC fixture_ids must be a non-empty array")
    result = [str(x).strip() for x in values]
    if any(not x for x in result) or len(result) != len(set(result)):
        raise ValueError("ABC fixture_ids contain blank or duplicate values")
    return set(result)

def sha_keys(keys):
    payload = "\n".join("|".join(map(str, key)) for key in sorted(keys))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def aggregate_fpl(rows, selected_season):
    grouped, seen_fixture_keys = defaultdict(list), set()
    for row in rows:
        key = row_key(row)
        if key[0] != selected_season or key[2] <= 1: continue
        fixture = str(row.get("fixture_id") or "").strip()
        if not fixture: raise ValueError(f"FPL row has no fixture_id: {key}")
        pair = (key, fixture)
        if pair in seen_fixture_keys: raise ValueError(f"Duplicate FPL player-fixture row: {pair}")
        seen_fixture_keys.add(pair)
        grouped[key].append(row)
    result, exclusions = {}, defaultdict(int)
    for key, fixtures in grouped.items():
        fixture_ids = {str(row["fixture_id"]).strip() for row in fixtures}
        points = [number(row.get("target_total_points")) for row in fixtures]
        minutes = [number(row.get("target_minutes")) for row in fixtures]
        if any(x is None for x in points + minutes):
            exclusions["INCOMPLETE_FPL_TARGET_LABEL"] += 1
            continue
        for name in SAME_ACROSS_DGW_FEATURES:
            values = [number(row.get(name)) for row in fixtures]
            observed = [value for value in values if value is not None]
            if observed and (len(observed) != len(values) or max(observed) - min(observed) > TOLERANCE):
                raise ValueError(f"Conflicting lagged FPL history feature {name} across fixtures: {key}")
        prior_count = number(fixtures[0].get("prior_gameweeks_count"))
        if prior_count is None or prior_count < 1:
            exclusions["NO_PRIOR_GAMEWEEK_HISTORY"] += 1
            continue
        result[key] = {
            "fixture_ids": fixture_ids,
            "actual_points": sum(points),
            "actual_minutes": sum(minutes),
            "last5_baseline_points": number(fixtures[0].get("prior5_gw_points_avg")),
            "fixture_count": len(fixtures),
        }
    return result, dict(exclusions)

def build_manifest(abc_rows, fpl_rows, season="2017/18", min_train_gameweeks=18,
                   test_window=4, min_fit_rows=50, min_calibration_rows=10, min_test_rows=30):
    selected_season = season_key(season)
    fpl_by_key, fpl_exclusions = aggregate_fpl(fpl_rows, selected_season)
    abc_by_key, abc_exclusions, seen_abc_keys = {}, defaultdict(int), set()
    for row in abc_rows:
        key = row_key(row)
        if key[0] != selected_season: continue
        if key[2] <= 1:
            abc_exclusions["FIRST_GAMEWEEK_EXCLUDED_BY_2PM_EVALUATOR"] += 1
            continue
        if key in seen_abc_keys: raise ValueError(f"Duplicate ABC player-Gameweek row: {key}")
        seen_abc_keys.add(key)
        if not truth(row.get("research_eligible_for_model")):
            abc_exclusions["ABC_NOT_RESEARCH_ELIGIBLE"] += 1
            continue
        abc_points, abc_minutes = number(row.get("target_fpl_total_points")), number(row.get("target_fpl_minutes"))
        if abc_points is None or abc_minutes is None:
            abc_exclusions["ABC_INCOMPLETE_TARGET_LABEL"] += 1
            continue
        abc_by_key[key] = {
            "fixture_ids": parse_fixture_ids(row.get("fixture_ids")),
            "actual_points": abc_points, "actual_minutes": abc_minutes,
        }

    mismatches = []
    for key, abc in sorted(abc_by_key.items()):
        fpl = fpl_by_key.get(key)
        reasons = []
        if fpl is None: reasons.append("NO_ELIGIBLE_FPL_PLAYER_GAMEWEEK")
        else:
            if abc["fixture_ids"] != fpl["fixture_ids"]: reasons.append("FIXTURE_ID_SET_MISMATCH")
            if abs(abc["actual_points"] - fpl["actual_points"]) > TOLERANCE: reasons.append("ACTUAL_POINTS_MISMATCH")
            if abs(abc["actual_minutes"] - fpl["actual_minutes"]) > TOLERANCE: reasons.append("ACTUAL_MINUTES_MISMATCH")
        if reasons: mismatches.append({"key_hash": sha_keys([key]), "reasons": reasons})

    common_keys = sorted(set(abc_by_key) & set(fpl_by_key))
    if mismatches:
        return {
            "status": "FAIL_CLOSED_TARGET_OR_FIXTURE_PARITY", "season": selected_season,
            "eligible_abc_player_gameweeks": len(abc_by_key), "eligible_fpl_player_gameweeks": len(fpl_by_key),
            "exact_common_player_gameweeks": len(common_keys), "mismatch_count": len(mismatches),
            "mismatch_examples": mismatches[:25], "abc_exclusion_counts": dict(sorted(abc_exclusions.items())),
            "fpl_exclusion_counts": dict(sorted(fpl_exclusions.items())), "folds": [],
            "promotion_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
        }
    if len(common_keys) != len(abc_by_key): raise AssertionError("Parity gate passed despite an incomplete common cohort")
    gameweeks = sorted({key[2] for key in common_keys})
    if len(gameweeks) <= min_train_gameweeks: raise ValueError("Insufficient Gameweeks for requested expanding validation")
    first_test = max(min_train_gameweeks, len(gameweeks) // 2)
    remaining = gameweeks[first_test:]
    blocks = [remaining[i:i + test_window] for i in range(0, len(remaining), test_window)]
    folds, private_partition_keys = [], []
    for index, block in enumerate(blocks, 1):
        train_gws = gameweeks[:first_test + (index - 1) * test_window]
        calibration_count = max(1, math.ceil(len(train_gws) * 0.20))
        calibration_gws, fit_gws = train_gws[-calibration_count:], train_gws[:-calibration_count]
        fit_keys = [k for k in common_keys if k[2] in fit_gws]
        calibration_keys = [k for k in common_keys if k[2] in calibration_gws]
        test_keys = [k for k in common_keys if k[2] in block]
        test_without_last5 = [k for k in test_keys if fpl_by_key[k]["last5_baseline_points"] is None]
        for partition, keys in (("fit", fit_keys), ("calibration", calibration_keys), ("test", test_keys)):
            private_partition_keys.extend({
                "fold": index, "partition": partition, "season": key[0],
                "fpl_element_id": key[1], "gameweek": key[2],
            } for key in keys)
        reasons = []
        if len(fit_keys) < min_fit_rows: reasons.append("FIT_ROWS_BELOW_MINIMUM")
        if len(calibration_keys) < min_calibration_rows: reasons.append("CALIBRATION_ROWS_BELOW_MINIMUM")
        if len(test_keys) < min_test_rows: reasons.append("TEST_ROWS_BELOW_MINIMUM")
        if test_without_last5: reasons.append("TEST_KEYS_MISSING_2PM_LAST5_BASELINE")
        folds.append({
            "fold": index, "fit_gameweeks": fit_gws, "calibration_gameweeks": calibration_gws,
            "test_gameweeks": block, "fit_player_gameweeks": len(fit_keys),
            "calibration_player_gameweeks": len(calibration_keys), "test_player_gameweeks": len(test_keys),
            "fit_unique_players": len({k[1] for k in fit_keys}),
            "calibration_unique_players": len({k[1] for k in calibration_keys}),
            "test_unique_players": len({k[1] for k in test_keys}),
            "test_keys_missing_last5_baseline": len(test_without_last5),
            "fit_key_sha256": sha_keys(fit_keys), "calibration_key_sha256": sha_keys(calibration_keys),
            "test_key_sha256": sha_keys(test_keys), "status": "READY" if not reasons else "BLOCKED",
            "blocking_reasons": reasons,
        })
    all_ready = bool(folds) and all(f["status"] == "READY" for f in folds)
    return {
        "status": "PASS_MATCHED_FOLD_MANIFEST" if all_ready else "BLOCKED_FOLD_COVERAGE",
        "season": selected_season, "evaluation_unit": "player_gameweek_including_double_gameweeks",
        "eligible_abc_player_gameweeks": len(abc_by_key), "eligible_fpl_player_gameweeks": len(fpl_by_key),
        "exact_common_player_gameweeks": len(common_keys), "unique_players": len({k[1] for k in common_keys}),
        "gameweeks": gameweeks, "common_key_sha256": sha_keys(common_keys),
        "actual_points_and_minutes_parity": "PASS", "fixture_id_set_parity": "PASS",
        "fold_policy": {
            "type": "EXPANDING_WHOLE_GAMEWEEK", "minimum_initial_train_gameweeks": min_train_gameweeks,
            "first_test_index": first_test, "test_window_gameweeks": test_window,
            "calibration_fraction_of_pretest_train_gameweeks": 0.20, "fit_and_calibration_are_disjoint": True,
        },
        "folds": folds, "abc_exclusion_counts": dict(sorted(abc_exclusions.items())),
        "_private_partition_keys": private_partition_keys,
        "fpl_exclusion_counts": dict(sorted(fpl_exclusions.items())),
        "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_SOURCE_VINTAGES",
        "promotion_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--abc-player-gw", type=Path, required=True)
    parser.add_argument("--fpl-panel", type=Path, required=True)
    parser.add_argument("--season", default="2017/18")
    parser.add_argument("--min-train-gameweeks", type=int, default=18)
    parser.add_argument("--test-window", type=int, default=4)
    parser.add_argument("--min-fit-rows", type=int, default=50)
    parser.add_argument("--min-calibration-rows", type=int, default=10)
    parser.add_argument("--min-test-rows", type=int, default=30)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--keys-out", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(read_csv(args.abc_player_gw), read_csv(args.fpl_panel), args.season,
        args.min_train_gameweeks, args.test_window, args.min_fit_rows,
        args.min_calibration_rows, args.min_test_rows)
    private_keys = manifest.pop("_private_partition_keys", [])
    args.keys_out.parent.mkdir(parents=True, exist_ok=True)
    with args.keys_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["fold", "partition", "season", "fpl_element_id", "gameweek"])
        writer.writeheader()
        writer.writerows(private_keys)
    manifest["private_partition_keys_file"] = str(args.keys_out.name)
    manifest["input_sha256"] = {
        "abc_player_gameweek_panel": hashlib.sha256(args.abc_player_gw.read_bytes()).hexdigest(),
        "conventional_fpl_fixture_panel": hashlib.sha256(args.fpl_panel.read_bytes()).hexdigest(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, allow_nan=False))
    return 0 if manifest["status"] == "PASS_MATCHED_FOLD_MANIFEST" else 2

if __name__ == "__main__":
    raise SystemExit(main())
