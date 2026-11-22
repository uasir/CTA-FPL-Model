#!/usr/bin/env python3
"""Capture public FPL manager records for an upcoming-GW state review.

This is read-only and deliberately does not infer the user's free-transfer
count, current bank, or upcoming lineup from stale previous-GW picks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen


BASE = "https://fantasy.premierleague.com/api"


def fetch_json(url: str, fetcher: Callable[[str], bytes] | None = None) -> tuple[bytes, Any]:
    if fetcher is None:
        request = Request(url, headers={"User-Agent": "CTA-FPL-Model/1.0 public manager review"})
        with urlopen(request, timeout=30) as response:
            raw = response.read()
    else:
        raw = fetcher(url)
    payload = json.loads(raw)
    return raw, payload


def capture_public_manager_snapshot(
    team_id: int,
    target_gameweek: int,
    *,
    fetcher: Callable[[str], bytes] | None = None,
    clock: Callable[[], str] | None = None,
) -> dict[str, Any]:
    if team_id < 1 or target_gameweek < 2:
        raise ValueError("team_id must be positive and target_gameweek must be at least 2")
    previous_gw = target_gameweek - 1
    base = f"{BASE}/entry/{team_id}"
    urls = {
        "previous_picks": f"{base}/event/{previous_gw}/picks/",
        "history": f"{base}/history/",
        "transfers": f"{base}/transfers/",
        "bootstrap": f"{BASE}/bootstrap-static/",
    }
    archives: dict[str, dict[str, Any]] = {}
    payloads: dict[str, Any] = {}
    for name, url in urls.items():
        raw, payload = fetch_json(url, fetcher)
        archives[name] = {
            "url": url,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "raw_json": raw.decode("utf-8"),
        }
        payloads[name] = payload

    picks_payload = payloads["previous_picks"]
    picks = picks_payload.get("picks") if isinstance(picks_payload, dict) else None
    entry_history = picks_payload.get("entry_history") if isinstance(picks_payload, dict) else None
    if not isinstance(picks, list) or len(picks) != 15:
        raise ValueError(f"official GW{previous_gw} picks did not contain 15 players")
    if not isinstance(entry_history, dict) or entry_history.get("event") != previous_gw:
        raise ValueError("previous-gameweek picks payload has unexpected event identity")

    bootstrap = payloads["bootstrap"]
    elements = bootstrap.get("elements") if isinstance(bootstrap, dict) else None
    if not isinstance(elements, list):
        raise ValueError("official bootstrap metadata has no elements list")
    metadata = {row.get("id"): row for row in elements if isinstance(row, dict)}
    enriched = []
    for row in sorted(picks, key=lambda item: item.get("position", 99)):
        element_id = row.get("element")
        player = metadata.get(element_id, {})
        enriched.append({
            "fpl_element_id": element_id,
            "name": " ".join(str(player.get(key, "")) for key in ("first_name", "second_name")).strip(),
            "position": row.get("position"),
            "element_type": player.get("element_type"),
            "team_id": player.get("team"),
            "purchase_price": (row["purchase_price"] / 10 if isinstance(row.get("purchase_price"), int) else None),
            "is_captain": row.get("is_captain") is True,
            "is_vice_captain": row.get("is_vice_captain") is True,
        })

    transfers = payloads["transfers"]
    if not isinstance(transfers, list):
        raise ValueError("official transfer history is not a list")
    target_transfers = []
    for row in transfers:
        if isinstance(row, dict) and row.get("event") == target_gameweek:
            target_transfers.append({
                "time": row.get("time"),
                "element_in": row.get("element_in"),
                "element_out": row.get("element_out"),
                "element_in_cost": row.get("element_in_cost"),
                "element_out_cost": row.get("element_out_cost"),
            })
    target_transfers.sort(key=lambda row: str(row.get("time") or ""))

    target_squad = {row["fpl_element_id"] for row in enriched}
    for transfer in target_transfers:
        outgoing, incoming = transfer["element_out"], transfer["element_in"]
        if outgoing not in target_squad or incoming in target_squad:
            raise ValueError("GW target transfer history cannot be applied consistently to previous squad")
        target_squad.remove(outgoing)
        target_squad.add(incoming)

    history = payloads["history"]
    current_event = history.get("current") if isinstance(history, dict) else None
    if not isinstance(current_event, list):
        current_event = []
    history_row = next((row for row in current_event if row.get("event") == previous_gw), None)
    if history_row is None:
        history_row = entry_history

    captured_at = clock() if clock else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "1.0.0",
        "capture_type": "PUBLIC_FPL_MANAGER_STATE_REVIEW_NOT_DECISION_EVIDENCE",
        "manager_team_id": team_id,
        "target_gameweek": target_gameweek,
        "previous_gameweek": previous_gw,
        "captured_at_utc": captured_at,
        "previous_gameweek_state": {
            "players_in_official_pick_order": enriched,
            "squad_ids": [row["fpl_element_id"] for row in enriched],
            "starting_xi_ids": [row["fpl_element_id"] for row in enriched if isinstance(row["position"], int) and row["position"] <= 11],
            "outfield_bench_ids": [row["fpl_element_id"] for row in enriched if isinstance(row["position"], int) and row["position"] > 11 and row["element_type"] != 1],
            "reserve_goalkeeper_id": next((row["fpl_element_id"] for row in enriched if row["element_type"] == 1 and row["position"] > 11), None),
            "captain_id": next((row["fpl_element_id"] for row in enriched if row["is_captain"]), None),
            "vice_captain_id": next((row["fpl_element_id"] for row in enriched if row["is_vice_captain"]), None),
            "bank_at_previous_deadline": history_row.get("bank", entry_history.get("bank")) / 10,
            "transfers_made_by_previous_deadline": history_row.get("event_transfers"),
            "total_transfers_to_previous_deadline": history_row.get("total_transfers"),
        },
        "target_gameweek_transfer_activity": {
            "transfers_reported": len(target_transfers),
            "transfers": target_transfers,
            "squad_ids_after_reported_target_transfers": sorted(target_squad),
        },
        "not_inferred": [
            "current bank after target-gameweek transfers",
            "current free-transfer count",
            "upcoming-gameweek starting XI and bench order",
            "upcoming-gameweek captain and vice-captain",
            "chip intent",
        ],
        "source_archives": archives,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-id", type=int, required=True)
    parser.add_argument("--target-gameweek", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture_public_manager_snapshot(args.team_id, args.target_gameweek)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
    summary = {
        "manager_team_id": result["manager_team_id"],
        "target_gameweek": result["target_gameweek"],
        "previous_gameweek": result["previous_gameweek"],
        "squad_ids": result["previous_gameweek_state"]["squad_ids"],
        "target_transfers_reported": result["target_gameweek_transfer_activity"]["transfers_reported"],
        "not_inferred": result["not_inferred"],
        "output": str(args.output),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
