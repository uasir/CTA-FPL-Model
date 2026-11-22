#!/usr/bin/env python3
"""Run a captured FPL Cat snapshot through M3 routing and the M4 product adapter.

The manager squad is deliberately synthetic and assembled from the captured
official FPL metadata. This validates the full data-to-product path without
pretending to be the user's live squad or issuing a live recommendation.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from build_conventional_squad_product import build_personal_squad_product
from provider_forecast_router import route_provider_forecast
from run_external_benchmark_personal_squad import run_external_benchmark_personal_squad


POSITION_COUNTS = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}


class ReplayError(ValueError):
    pass


def build_synthetic_manager_context(player_metadata: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Create a legal, low-cost 15-player fixture; never represents a real manager."""
    selected: list[Mapping[str, Any]] = []
    team_counts: dict[int, int] = {}
    for position, required_count in POSITION_COUNTS.items():
        candidates = sorted(
            (row for row in player_metadata if row.get("position") == position),
            key=lambda row: (float(row.get("price", 999)), int(row.get("fpl_element_id", 0))),
        )
        for row in candidates:
            player_id = row.get("fpl_element_id")
            team_id = row.get("team_id")
            price = row.get("price")
            if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id < 1:
                continue
            if isinstance(team_id, bool) or not isinstance(team_id, int) or team_id < 1:
                continue
            if isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 0:
                continue
            if player_id in {item["fpl_element_id"] for item in selected}:
                continue
            if team_counts.get(team_id, 0) >= 3:
                continue
            if sum(1 for item in selected if item.get("position") == position) >= required_count:
                break
            selected.append({**dict(row), "position": position})
            team_counts[team_id] = team_counts.get(team_id, 0) + 1

    for position, required_count in POSITION_COUNTS.items():
        actual = sum(1 for row in selected if row["position"] == position)
        if actual != required_count:
            raise ReplayError(
                f"could not assemble synthetic legal squad: {position} {actual}/{required_count}"
            )
    if len(selected) != 15:
        raise ReplayError(f"synthetic squad must contain 15 players, received {len(selected)}")
    total_cost = round(sum(float(row["price"]) for row in selected), 1)
    if total_cost > 100.0:
        raise ReplayError(f"synthetic squad exceeds £100.0m budget: £{total_cost:.1f}m")

    return {
        "squad_snapshot": [
            {"fpl_element_id": row["fpl_element_id"], "purchase_price": float(row["price"])}
            for row in selected
        ],
        "bank": round(100.0 - total_cost, 1),
        "free_transfers": 1,
        "personal_risk_profile": "aggressive",
        "formation": "4-3-3",
        "chips": [],
        "fixture_status": "SYNTHETIC_PIPELINE_ONLY_NOT_USER_SQUAD",
        "fixture_method": "LOWEST_PRICE_LEGAL_15_PLAYER_SQUAD_FROM_CAPTURED_BOOTSTRAP",
    }


def build_fplcat_m3_m4_replay(
    capture: Mapping[str, Any],
    *,
    as_of_utc: str | None = None,
) -> dict[str, Any]:
    snapshot = capture.get("provider_snapshot")
    metadata = capture.get("player_metadata")
    provenance = capture.get("player_metadata_provenance")
    if not isinstance(snapshot, Mapping) or not isinstance(metadata, list) or not isinstance(provenance, Mapping):
        raise ReplayError("capture must contain provider_snapshot, player_metadata and provenance")
    if snapshot.get("provider", {}).get("name") != "FPL Cat":
        raise ReplayError("this replay accepts FPL Cat only")
    if snapshot.get("target_gameweek") != 12:
        raise ReplayError("expected the current GW12 FPL Cat capture")

    if as_of_utc is None:
        as_of_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    route = route_provider_forecast(
        snapshot,
        player_metadata=metadata,
        as_of_utc=as_of_utc,
        forecast_horizon_gameweeks=1,
    )
    if route.get("routing_status") != "RECOMMENDATION_PAYLOAD_READY" or route.get("decision_eligible") is not True:
        raise ReplayError(
            f"M3 did not produce a recommendation payload: {route.get('routing_status')} "
            f"({route.get('routing_reason')})"
        )

    manager_context = build_synthetic_manager_context(metadata)
    run_input = {
        "provider_snapshot": dict(snapshot),
        "player_metadata": metadata,
        "player_metadata_provenance": dict(provenance),
        "manager_context": manager_context,
        "as_of_utc": as_of_utc,
    }
    run = run_external_benchmark_personal_squad(run_input)
    product = build_personal_squad_product(run)

    if product.get("product_id") != "conventional_personal_squad":
        raise ReplayError("M4 did not emit the conventional personal-squad product")
    if product.get("decision", {}).get("basis") != "CONVENTIONAL_EXPECTED_POINTS_ONLY":
        raise ReplayError("M4 conventional decision basis is not expected-points-only")
    if product.get("release_eligible") is not False:
        raise ReplayError("M4 replay must remain non-release-eligible")

    return {
        "replay_contract_version": "1.0.0",
        "replay_status": "M3_TO_M4_SYNTHETIC_MANAGER_PIPELINE_PASSED",
        "manager_fixture_status": manager_context["fixture_status"],
        "manager_fixture_method": manager_context["fixture_method"],
        "m3": {
            "routing_status": route["routing_status"],
            "decision_eligible": route["decision_eligible"],
            "provider": route["provider"],
            "target_gameweek": route["target_gameweek"],
            "snapshot_id": route["snapshot_id"],
            "forecast_rows": len(snapshot["records"]),
            "metadata_rows": len(metadata),
        },
        "m4": product,
        "limitations": [
            "The manager squad is synthetic and is not the user's current squad.",
            "This is an end-to-end engineering replay, not a live transfer recommendation.",
            "M2 forecast validation and M4 outcome evaluation remain pending.",
            "The product remains exploratory and is not release-eligible.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of-utc")
    args = parser.parse_args()
    capture = json.loads(args.capture.read_text(encoding="utf-8"))
    result = build_fplcat_m3_m4_replay(capture, as_of_utc=args.as_of_utc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "replay_status": result["replay_status"],
        "provider": result["m3"]["provider"]["name"],
        "gameweek": result["m3"]["target_gameweek"],
        "forecast_rows": result["m3"]["forecast_rows"],
        "manager_fixture_status": result["manager_fixture_status"],
        "product_id": result["m4"]["product_id"],
        "decision_basis": result["m4"]["decision"]["basis"],
        "release_eligible": result["m4"]["release_eligible"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
