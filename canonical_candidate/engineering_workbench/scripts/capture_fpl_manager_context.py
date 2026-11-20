#!/usr/bin/env python3
"""Capture a public FPL manager picks snapshot with purchase prices.

The output preserves the raw picks response and emits a normalized 15-player
squad snapshot. It does not infer free transfers; that remains explicit input.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


class CaptureError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "CTA-FPL-Model/1.0 (public manager snapshot)"})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise CaptureError(f"GET {url} returned HTTP {response.status}")
        return response.read()


def capture_manager_context(
    team_id: int,
    gameweek: int,
    *,
    expected_element_ids: set[int] | None = None,
    expected_bank: float | None = None,
) -> dict[str, Any]:
    if isinstance(free_transfers, bool) or not isinstance(free_transfers, int) or not 0 <= free_transfers <= 5:\n        raise CaptureError("free_transfers must be an integer from 0 to 5")\n    if personal_risk_profile not in {"conservative", "balanced", "aggressive"}:\n        raise CaptureError("personal_risk_profile must be conservative, balanced, or aggressive")\n    if formation not in {"3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1", "5-2-3", "5-3-2", "5-4-1"}:\n        raise CaptureError("formation is not a supported FPL formation")\n\n    url = f"https://fantasy.premierleague.com/api/entry/{team_id}/event/{gameweek}/picks/"
    raw = fetch(url)
    captured_at = utc_now()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CaptureError("FPL manager picks response is not valid JSON") from exc
    picks = payload.get("picks")
    history = payload.get("entry_history")
    if not isinstance(picks, list) or not isinstance(history, dict):
        raise CaptureError("FPL response is missing picks or entry_history")
    if len(picks) != 15:
        raise CaptureError(f"expected 15 squad picks, received {len(picks)}")

    squad = []
    seen: set[int] = set()
    for row in picks:
        element = row.get("element")
        purchase_price = row.get("purchase_price")
        if isinstance(element, bool) or not isinstance(element, int) or element < 1:
            raise CaptureError("pick contains invalid FPL element ID")
        if element in seen:
            raise CaptureError(f"duplicate FPL element ID {element}")
        seen.add(element)
        if isinstance(purchase_price, bool) or not isinstance(purchase_price, int) or purchase_price <= 0:
            raise CaptureError(f"player {element} has invalid purchase_price")
        squad.append({
            "fpl_element_id": element,
            "purchase_price": purchase_price / 10,
        })

    if expected_element_ids is not None and seen != expected_element_ids:
        missing = sorted(expected_element_ids - seen)
        unexpected = sorted(seen - expected_element_ids)
        raise CaptureError(f"squad identity mismatch; missing={missing}, unexpected={unexpected}")

    bank_raw = history.get("bank")
    if isinstance(bank_raw, bool) or not isinstance(bank_raw, int) or bank_raw < 0:
        raise CaptureError("entry_history.bank is missing or invalid")
    bank = bank_raw / 10
    if expected_bank is not None and abs(bank - expected_bank) > 0.0001:
        raise CaptureError(f"bank mismatch: supplied £{expected_bank:.1f}m, FPL reports £{bank:.1f}m")

    digest = hashlib.sha256(raw).hexdigest()
    return {
        "manager_context_capture": {
            "team_id": team_id,
            "gameweek": gameweek,
            "captured_at_utc": captured_at,
            "source_url": url,
            "raw_sha256": digest,
            "raw_response_base64": base64.b64encode(raw).decode("ascii"),
            "row_count": len(squad),
            "identity_verified": expected_element_ids is None or seen == expected_element_ids,
        },
        "manager_context": {
            "squad_snapshot": squad,
            "bank": bank,
            "entry_history": history,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-id", type=int, required=True)
    parser.add_argument("--gameweek", type=int, required=True)
    parser.add_argument("--expected-element-ids", default="")
    parser.add_argument("--expected-bank", type=float)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expected = {int(value) for value in args.expected_element_ids.split(",") if value.strip()}
    result = capture_manager_context(
        args.team_id,
        args.gameweek,
        expected_element_ids=expected or None,
        expected_bank=args.expected_bank,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "team_id": args.team_id,
        "gameweek": args.gameweek,
        "squad_rows": result["manager_context_capture"]["row_count"],
        "identity_verified": result["manager_context_capture"]["identity_verified"],
        "bank": result["manager_context"]["bank"],
        "raw_sha256": result["manager_context_capture"]["raw_sha256"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
