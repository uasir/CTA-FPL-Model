#!/usr/bin/env python3
"""Enrich the historical ABC player-Gameweek panel with 11footy-first evidence.

11footy is the primary player-feature source. Existing Wyscout ABC features are
retained as per-feature fallbacks where 11footy does not provide an equivalent.
Only verified 11footy player/fixture rows are used; all 11footy features are
lagged by complete FPL Gameweeks, so no same-Gameweek fixture can leak.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from cta_four_layer_pipeline import LAYER_FEATURES

WYS_FEATURES = tuple(f"abc_{name}" for names in LAYER_FEATURES.values() for name in names)


def number(value):
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _mean(rows, field):
    values = [number(row.get(field)) for row in rows]
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def _sum(rows, field):
    values = [number(row.get(field)) for row in rows]
    values = [value for value in values if value is not None]
    return sum(values) if values else None


def _per90(rows, field):
    total = _sum(rows, field)
    minutes = _sum(rows, "minutes_played")
    # Require one full-match equivalent of exposure across the prior three
    # verified player matches. Do not clip unstable rates; mark them missing.
    if total is None or minutes is None or minutes < 90:
        return None
    return total * 90.0 / minutes


def _difference(a, b):
    return a - b if a is not None and b is not None else None


def _features(prior_rows):
    last3, last5 = prior_rows[-3:], prior_rows[-5:]
    kp3, kp5 = _mean(last3, "key_passes"), _mean(last5, "key_passes")
    xg3, xg5 = _mean(last3, "tracked_xg_sum"), _mean(last5, "tracked_xg_sum")
    goals3 = _sum(last3, "goals")
    xg_sum3 = _sum(last3, "tracked_xg_sum")
    shots3 = _sum(last3, "shots")
    box3 = _sum(last3, "attempts_inside_box")
    minutes3 = _mean(last3, "minutes_played")
    minutes5 = _mean(last5, "minutes_played")
    key_rate = _per90(last3, "key_passes")
    xg_rate = _per90(last3, "tracked_xg_sum")
    shot_rate = _per90(last3, "shots")
    recent_minutes = _sum(last3, "minutes_played")
    return {
        "_11footy_per90_exposure_sufficient": recent_minutes is not None and recent_minutes >= 90,
        # A — 11footy directly observed player actions and tracked xG.
        "player_key_pass_rate": key_rate,
        "player_tracked_xg_rate": xg_rate,
        "recent_key_pass_trend": _difference(kp3, kp5),
        "recent_xg_trend": _difference(xg3, xg5),
        # B — only the directly observed 11footy foul statistic is mapped here.
        "player_fouls_committed_rate": _per90(last3, "fouls_committed"),
        # C — lagged player involvement, threat and minutes evidence.
        "minutes_trend": _difference(minutes3, minutes5),
        "attacking_involvement": (
            _mean(last3, "key_passes") + _mean(last3, "shots")
            if _mean(last3, "key_passes") is not None and _mean(last3, "shots") is not None
            else None
        ),
        "threat_creation_rate": key_rate,
        # 11footy attempts inside the box are shots, not receiver-level receptions.
        # Do not relabel them as reception evidence.
        "threat_reception_rate": None,
        "threat_realisation_rate": (
            goals3 / xg_sum3 if goals3 is not None and xg_sum3 is not None and xg_sum3 > 0 else None
        ),
        "attacking_involvement_rate": (
            key_rate + shot_rate if key_rate is not None and shot_rate is not None else None
        ),
    }


def _verified_rows(rows):
    result = defaultdict(list)
    seen = set()
    for row in rows:
        # Input contract: verified_player_match_panel.csv from
        # build_11footy_player_match_features.py. That builder emits only rows
        # backed by the strict cross-provider verified crosswalk and fixture checks.
        player = str(row.get("fpl_element_id") or "").strip()
        fixture = str(row.get("fpl_fixture_id") or "").strip()
        gw = number(row.get("gameweek"))
        if not player or not fixture or gw is None:
            continue
        key = (player, fixture)
        if key in seen:
            raise ValueError(f"Duplicate verified 11footy player-fixture row: {key}")
        seen.add(key)
        result[player].append((int(gw), row))
    for player in result:
        result[player].sort(key=lambda item: (item[0], str(item[1].get("match_kickoff_utc") or "")))
    return result


def enrich_panel(wyscout_rows, footy_rows):
    history = _verified_rows(footy_rows)
    output = []
    source_counts = defaultdict(int)
    fallback_counts = defaultdict(int)
    missing_counts = defaultdict(int)
    eligible = 0
    for base in wyscout_rows:
        player = str(base.get("fpl_element_id") or "").strip()
        gw_value = number(base.get("gameweek"))
        if not player or gw_value is None:
            continue
        gw = int(gw_value)
        # Whole-GW lag: all fixtures in the target GW share identical prior data.
        prior = [row for prior_gw, row in history.get(player, []) if prior_gw < gw]
        derived = _features(prior[-5:]) if prior else {}
        record = dict(base)
        feature_sources = {}
        for names in LAYER_FEATURES.values():
            for name in names:
                column = f"abc_{name}"
                footy_value = number(derived.get(name))
                wys_value = number(base.get(column))
                exposure_gated_rate = name in {
                    "player_key_pass_rate", "player_tracked_xg_rate",
                    "player_fouls_committed_rate", "threat_creation_rate",
                    "attacking_involvement_rate",
                }
                low_11footy_exposure = (
                    derived.get("_11footy_per90_exposure_sufficient") is False
                )
                if footy_value is not None:
                    record[column] = footy_value
                    feature_sources[name] = "11footy"
                    source_counts[name] += 1
                elif low_11footy_exposure and exposure_gated_rate:
                    # A low-exposure 11footy rate is not a provider-data gap;
                    # keep it missing instead of masking the weakness with fallback.
                    record[column] = ""
                    feature_sources[name] = "MISSING_LOW_11FOOTY_EXPOSURE"
                    missing_counts[name] += 1
                elif wys_value is not None:
                    record[column] = wys_value
                    feature_sources[name] = "wyscout"
                    fallback_counts[name] += 1
                else:
                    record[column] = ""
                    feature_sources[name] = "MISSING"
                    missing_counts[name] += 1
        # Keep all original Wyscout provenance and append feature-level source attribution.
        record["abc_feature_sources"] = json.dumps(feature_sources, sort_keys=True)
        record["abc_primary_feature_source"] = "11footy"
        record["abc_supplementary_feature_source"] = "Wyscout"
        record["abc_11footy_prior_match_count"] = len(prior)
        record["research_eligible_for_model"] = str(
            base.get("research_eligible_for_analysis", "")
        ).strip().lower() in {"true", "1", "yes"}
        eligible += int(record["research_eligible_for_model"])
        output.append(record)
    verified_rows = [row for player_rows in history.values() for _, row in player_rows]
    report = {
        "status": "PASS_FEATURE_ENRICHMENT" if output else "NO_ROWS",
        "rows": len(output),
        "research_eligible_for_model_rows": eligible,
        "verified_11footy_player_match_rows": len(verified_rows),
        "verified_11footy_unique_players": len(history),
        "verified_11footy_unique_fpl_fixtures": len({
            str(row.get("fpl_fixture_id") or "") for row in verified_rows
        }),
        "feature_values_from_11footy": dict(source_counts),
        "feature_values_fallback_to_wyscout": dict(fallback_counts),
        "feature_values_missing_after_fallback": dict(missing_counts),
        "primary_source": "11footy historical verified player-match features",
        "supplementary_source": "Wyscout historical player-match event features",
        "lag_policy": "Only verified 11footy matches from strictly earlier FPL Gameweeks; same-GW fixtures share pre-GW history.",
        "identity_policy": "Input must be the verified_player_match_panel.csv emitted by build_11footy_player_match_features.py; provisional research-only rows are not accepted.",
        "missingness_policy": "Missing values remain null; Wyscout is used only where the corresponding 11footy feature is unavailable.",
        "point_in_time_status": "RETROSPECTIVE_SOURCE_VINTAGES_NOT_VERIFIED",
        "promotion_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
    }
    return output, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wyscout-panel", type=Path, required=True)
    parser.add_argument("--11footy-panel", dest="footy_panel", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    rows, report = enrich_panel(read_csv(args.wyscout_panel), read_csv(args.footy_panel))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    panel_path = args.out_dir / "cta_abc_historical_integrated_player_fixture_panel.csv"
    write_csv(panel_path, rows)
    report["input_hashes"] = {
        "wyscout_abc_panel_sha256": sha256(args.wyscout_panel),
        "verified_11footy_player_match_panel_sha256": sha256(args.footy_panel),
    }
    report["integrated_panel_sha256"] = sha256(panel_path)
    (args.out_dir / "cta_abc_historical_integrated_report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS_FEATURE_ENRICHMENT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
