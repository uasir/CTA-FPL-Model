#!/usr/bin/env python3
"""Normalize captured Sideline Quant fixture rows without losing native detail.

Sideline Quant publishes one row per player-fixture. This adapter preserves
that grain in the canonical contract and offers a separately named, explicit
sum-xP Gameweek aggregation for decision-engine consumption.
"""
from __future__ import annotations

import argparse
import base64
from collections import defaultdict
import json
from pathlib import Path
from typing import Any, Mapping

from canonical_provider_forecast_contract import normalize_provider_snapshot


class SidelineQuantParseError(ValueError):
    pass


def _number(value: Any, field: str, *, minimum: float | None = None,
            maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SidelineQuantParseError(f"{field} must be numeric")
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        raise SidelineQuantParseError(f"{field} must be finite")
    if minimum is not None and result < minimum:
        raise SidelineQuantParseError(f"{field} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise SidelineQuantParseError(f"{field} must be <= {maximum}")
    return result


def parse_sideline_quant_capture(capture: Mapping[str, Any]) -> dict[str, Any]:
    """Return canonical fixture-grain snapshot, native rows and explicit GW sum."""
    try:
        raw = base64.b64decode(
            capture["raw_archives"]["provider_response_base64"], validate=True
        )
        bootstrap_raw = base64.b64decode(
            capture["raw_archives"]["official_fpl_bootstrap_base64"], validate=True
        )
        provider = json.loads(raw)
        bootstrap = json.loads(bootstrap_raw)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SidelineQuantParseError("capture is missing valid archived provider/bootstrap JSON") from exc

    if not isinstance(provider, dict) or not isinstance(provider.get("rows"), list):
        raise SidelineQuantParseError("Sideline Quant payload must contain a rows array")
    if not isinstance(bootstrap, dict) or not isinstance(bootstrap.get("elements"), list):
        raise SidelineQuantParseError("archived FPL bootstrap must contain an elements array")

    gameweek = capture.get("target_gameweek")
    if provider.get("gameweek") != gameweek:
        raise SidelineQuantParseError("provider payload Gameweek differs from capture metadata")
    rows = provider["rows"]
    if len(rows) != provider.get("n_rows") or len(rows) != capture["coverage"]["declared_row_count"]:
        raise SidelineQuantParseError("actual row count does not match provider-declared coverage")
    allowed_ids = {
        item.get("id") for item in bootstrap["elements"]
        if isinstance(item, dict) and isinstance(item.get("id"), int)
    }
    if not allowed_ids:
        raise SidelineQuantParseError("official FPL bootstrap has no usable element IDs")

    seen: set[tuple[int, int]] = set()
    normalized_rows = []
    native_rows = []
    gw_totals: dict[int, float] = defaultdict(float)
    fixture_counts: dict[int, int] = defaultdict(int)
    gw_distribution: dict[int, dict[str, float]] = {}

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise SidelineQuantParseError(f"rows[{index}] must be an object")
        player_id = row.get("player_id")
        fixture_id = row.get("fixture_id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id not in allowed_ids:
            raise SidelineQuantParseError(f"rows[{index}].player_id is not a valid FPL element ID")
        if isinstance(fixture_id, bool) or not isinstance(fixture_id, int) or fixture_id < 1:
            raise SidelineQuantParseError(f"rows[{index}].fixture_id must be a positive integer")
        if row.get("gameweek") != gameweek:
            raise SidelineQuantParseError(f"rows[{index}].gameweek differs from capture Gameweek")
        key = (player_id, fixture_id)
        if key in seen:
            raise SidelineQuantParseError(f"duplicate player-fixture key: {key}")
        seen.add(key)

        xp = _number(row.get("xP"), f"rows[{index}].xP")
        e_mins = _number(row.get("e_mins"), f"rows[{index}].e_mins", minimum=0)
        p_start = _number(row.get("p_start"), f"rows[{index}].p_start", minimum=0, maximum=1)
        normalized_rows.append({
            "fpl_element_id": player_id,
            "fixture_id": fixture_id,
            "expected_points": xp,
            "expected_minutes": e_mins,
        })
        native_rows.append(dict(row))
        gw_totals[player_id] += xp
        fixture_counts[player_id] += 1

        # Sideline Quant publishes gameweek-level distribution statistics on
        # its fixture rows. They describe the player's total GW outcome, so
        # retain one consistent copy rather than summing them across fixtures.
        distribution_fields = {"gw_sigma": "gw_sigma", "gw_p10": "q10", "gw_p90": "q90"}
        current = gw_distribution.setdefault(player_id, {})
        for source_field, target_field in distribution_fields.items():
            raw_value = row.get(source_field)
            if raw_value is None:
                continue
            value = _number(
                raw_value,
                f"rows[{index}].{source_field}",
                minimum=0 if source_field == "gw_sigma" else None,
            )
            if target_field in current and current[target_field] != value:
                raise SidelineQuantParseError(
                    f"inconsistent {source_field} across fixture rows for player {player_id}"
                )
            current[target_field] = value

    if len(gw_totals) != provider.get("n_players"):
        raise SidelineQuantParseError("distinct player count does not match provider-declared n_players")

    snapshot = {
        "snapshot_id": capture["capture_id"],
        "season": capture["season"],
        "target_gameweek": gameweek,
        "provider": {
            "name": "Sideline Quant",
            "product": "public next-Gameweek projections",
            "variant": "fixture-grain JSON feed",
            "version": provider.get("schema_version"),
        },
        "timing": {
            "generated_at_utc": capture["timing"]["generated_at_utc"],
            "captured_at_utc": capture["timing"]["captured_at_utc"],
            "deadline_utc": capture["timing"]["deadline_utc"],
        },
        "source": {
            "url": capture["source"]["url"],
            "raw_snapshot_id": capture["source"]["raw_snapshot_id"],
            "raw_sha256": capture["source"]["raw_sha256"],
        },
        "grain": "player_fixture",
        "records": normalized_rows,
        "coverage": {
            "row_count": len(normalized_rows),
            "expected_player_universe": len(allowed_ids),
            "identity_mapped_count": len(normalized_rows),
            "distinct_provider_players": len(gw_totals),
            "provider_declared_players": provider["n_players"],
        },
    }
    canonical = normalize_provider_snapshot(snapshot)

    # The publisher explicitly defines player-GW xP as the sum of fixture xP.
    # This is an explicit derived view; native fixture rows remain authoritative.
    gameweek_rows = [
        {
            "fpl_element_id": player_id,
            "expected_points": total_xp,
            "fixture_count": fixture_counts[player_id],
            "aggregation": "SUM_OF_PROVIDER_FIXTURE_XP",
            "source_grain": "player_fixture",
            "source_snapshot_id": capture["capture_id"],
            **(
                {"points_variance": gw_distribution[player_id]["gw_sigma"] ** 2}
                if "gw_sigma" in gw_distribution.get(player_id, {}) else {}
            ),
            **(
                {"q10": gw_distribution[player_id]["q10"]}
                if "q10" in gw_distribution.get(player_id, {}) else {}
            ),
            **(
                {"q90": gw_distribution[player_id]["q90"]}
                if "q90" in gw_distribution.get(player_id, {}) else {}
            ),
        }
        for player_id, total_xp in sorted(gw_totals.items())
    ]
    return {
        "canonical_snapshot": canonical,
        "provider_native_rows": native_rows,
        "player_gameweek_sum_xp": gameweek_rows,
        "aggregation_provenance": {
            "method": "SUM(xP) grouped by player_id within target Gameweek",
            "source_grain": "player_fixture",
            "target_grain": "player_gameweek",
            "publisher_documented": True,
            "native_fixture_rows_preserved": True,
            "probability_fields_aggregated": False,
            "gameweek_distribution_fields": {
                "gw_sigma": "squared to points_variance",
                "gw_p10": "mapped to q10",
                "gw_p90": "mapped to q90",
                "consistency_checked_across_fixture_rows": True,
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    capture = json.loads(args.input.read_text(encoding="utf-8"))
    result = parse_sideline_quant_capture(capture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "provider": "Sideline Quant",
        "gameweek": result["canonical_snapshot"]["target_gameweek"],
        "fixture_rows": len(result["canonical_snapshot"]["records"]),
        "gameweek_player_rows": len(result["player_gameweek_sum_xp"]),
        "decision_eligible": result["canonical_snapshot"]["decision_eligible"],
        "aggregation": result["aggregation_provenance"]["method"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
