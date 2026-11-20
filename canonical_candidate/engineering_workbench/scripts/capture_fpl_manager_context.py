#!/usr/bin/env python3
"""Capture an FPL manager squad, reconstructing pre-deadline purchase prices."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
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


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CaptureError(f"{label} response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise CaptureError(f"{label} response must be a JSON object")
    return value


def _valid_price(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CaptureError(f"{label} is missing or invalid")
    return value


def reconstruct_purchase_prices(
    gw1_payload: dict[str, Any],
    transfers_payload: Any,
    history_payload: dict[str, Any],
    target_gameweek: int,
    expected_element_ids: set[int],
    bootstrap_payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rebuild holdings from GW1 prices, bootstrap season-start prices and transfers."""
    if target_gameweek < 2:
        raise CaptureError("historical fallback reconstruction requires target GW2 or later")
    picks = gw1_payload.get("picks")
    gw1_history = gw1_payload.get("entry_history")
    if not isinstance(picks, list) or len(picks) != 15 or not isinstance(gw1_history, dict):
        raise CaptureError("GW1 picks response must contain 15 picks and entry_history")
    if gw1_history.get("event") != 1:
        raise CaptureError("GW1 picks response has incorrect event number")
    bootstrap_prices: dict[int, int] = {}
    if bootstrap_payload is not None:
        elements = bootstrap_payload.get("elements")
        if not isinstance(elements, list):
            raise CaptureError("FPL bootstrap is missing its elements list")
        for row in elements:
            if not isinstance(row, dict):
                continue
            element_id = row.get("id")
            now_cost = row.get("now_cost")
            cost_change_start = row.get("cost_change_start")
            if (
                isinstance(element_id, int) and not isinstance(element_id, bool)
                and isinstance(now_cost, int) and not isinstance(now_cost, bool)
                and isinstance(cost_change_start, int) and not isinstance(cost_change_start, bool)
            ):
                starting_cost = now_cost - cost_change_start
                if starting_cost > 0:
                    bootstrap_prices[element_id] = starting_cost

    holdings: dict[int, int] = {}
    for pick in picks:
        if not isinstance(pick, dict):
            raise CaptureError("GW1 picks contains a malformed row")
        element = pick.get("element")
        if isinstance(element, bool) or not isinstance(element, int) or element < 1 or element in holdings:
            raise CaptureError("GW1 picks contains an invalid or duplicate player ID")
        recorded_price = pick.get("purchase_price")
        if isinstance(recorded_price, int) and not isinstance(recorded_price, bool) and recorded_price > 0:
            initial_price = recorded_price
        else:
            initial_price = bootstrap_prices.get(element)
            if initial_price is None:
                raise CaptureError(
                    f"GW1 purchase price is unavailable for player {element}; "
                    "neither picks nor bootstrap provide a verified season-start price"
                )
        holdings[element] = _valid_price(initial_price, f"GW1 purchase_price for player {element}")

    if not isinstance(transfers_payload, list):
        raise CaptureError("transfer history response must be a list")
    chips = history_payload.get("chips")
    if not isinstance(chips, list):
        raise CaptureError("manager history is missing its chips list")
    free_hit_events = {
        chip.get("event") for chip in chips
        if isinstance(chip, dict) and chip.get("name") == "freehit"
    }

    transfers = []
    for row in transfers_payload:
        if not isinstance(row, dict):
            raise CaptureError("transfer history contains a malformed row")
        event = row.get("event")
        if isinstance(event, bool) or not isinstance(event, int) or event < 1:
            raise CaptureError("transfer history contains an invalid event")
        if event >= target_gameweek:
            continue
        if event in free_hit_events:
            continue
        incoming = row.get("element_in")
        outgoing = row.get("element_out")
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in (incoming, outgoing)):
            raise CaptureError("transfer history contains an invalid player ID")
        incoming_cost = _valid_price(row.get("element_in_cost"), f"element_in_cost in GW{event}")
        transfers.append((event, str(row.get("time", "")), incoming, outgoing, incoming_cost))

    # FPL's endpoint is newest-first; applying the reverse chronological log
    # reconstructs the final state, including a player sold and later re-bought.
    transfers.sort(key=lambda item: (item[0], item[1]))
    for event, _, incoming, outgoing, incoming_cost in transfers:
        if outgoing not in holdings:
            raise CaptureError(f"GW{event} transfer sells player {outgoing}, who is not in reconstructed squad")
        del holdings[outgoing]
        if incoming in holdings:
            raise CaptureError(f"GW{event} transfer buys player {incoming}, already in reconstructed squad")
        holdings[incoming] = incoming_cost

    if set(holdings) != expected_element_ids:
        missing = sorted(expected_element_ids - set(holdings))
        unexpected = sorted(set(holdings) - expected_element_ids)
        raise CaptureError(f"reconstructed squad identity mismatch; missing={missing}, unexpected={unexpected}")
    return [
        {"fpl_element_id": element, "purchase_price": price / 10}
        for element, price in sorted(holdings.items())
    ]


def capture_manager_context(
    team_id: int,
    gameweek: int,
    *,
    expected_element_ids: set[int] | None = None,
    expected_bank: float | None = None,
    free_transfers: int,
    personal_risk_profile: str = "aggressive",
    formation: str = "4-3-3",
    starting_xi_ids: set[int] | None = None,
    allow_user_confirmed_fallback: bool = False,
) -> dict[str, Any]:
    if isinstance(free_transfers, bool) or not isinstance(free_transfers, int) or not 0 <= free_transfers <= 5:
        raise CaptureError("free_transfers must be an integer from 0 to 5")
    if personal_risk_profile not in {"conservative", "balanced", "aggressive"}:
        raise CaptureError("personal_risk_profile must be conservative, balanced, or aggressive")
    if formation not in {"3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1", "5-2-3", "5-3-2", "5-4-1"}:
        raise CaptureError("formation is not a supported FPL formation")

    if starting_xi_ids is not None:
        if len(starting_xi_ids) != 11 or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in starting_xi_ids
        ):
            raise CaptureError("starting_xi_ids must contain exactly 11 unique positive FPL element IDs")
        if expected_element_ids is not None and not starting_xi_ids.issubset(expected_element_ids):
            raise CaptureError("starting_xi_ids must be a subset of the confirmed 15-player squad")

    base = f"https://fantasy.premierleague.com/api/entry/{team_id}"
    target_url = f"{base}/event/{gameweek}/picks/"
    try:
        raw = fetch(target_url)
    except HTTPError as exc:
        if not (allow_user_confirmed_fallback and exc.code == 404):
            raise
        if expected_element_ids is None or len(expected_element_ids) != 15:
            raise CaptureError("pre-deadline fallback requires exactly 15 user-confirmed FPL element IDs") from exc
        if expected_bank is None:
            raise CaptureError("pre-deadline fallback requires an explicitly supplied bank value") from exc

        previous_gameweek = gameweek - 1
        previous_picks_url = f"{base}/event/{previous_gameweek}/picks/"
        gw1_url = f"{base}/event/1/picks/"
        transfers_url = f"{base}/transfers/"
        history_url = f"{base}/history/"
        bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
        previous_picks_raw = fetch(previous_picks_url)
        history_raw = fetch(history_url)
        previous_payload = _json(previous_picks_raw, f"GW{previous_gameweek} picks")
        history_payload = _json(history_raw, "manager history")
        chips = history_payload.get("chips")
        if not isinstance(chips, list):
            raise CaptureError("manager history is missing its chips list")
        free_hit_events = {
            chip.get("event") for chip in chips
            if isinstance(chip, dict) and chip.get("name") == "freehit"
        }

        previous_rows = previous_payload.get("picks")
        previous_history = previous_payload.get("entry_history")
        previous_ids = {
            row.get("element") for row in previous_rows
            if isinstance(row, dict) and isinstance(row.get("element"), int)
        } if isinstance(previous_rows, list) else set()
        previous_squad = None
        if (
            previous_history.get("event") == previous_gameweek
            if isinstance(previous_history, dict) else False
        ) and previous_gameweek not in free_hit_events and previous_ids == expected_element_ids and len(previous_rows) == 15:
            direct_rows = []
            try:
                for row in previous_rows:
                    price = _valid_price(row.get("purchase_price"), f"GW{previous_gameweek} purchase_price for player {row['element']}")
                    direct_rows.append({"fpl_element_id": row["element"], "purchase_price": price / 10})
                previous_squad = direct_rows
            except CaptureError:
                previous_squad = None

        if previous_squad is not None:
            squad = previous_squad
            purchase_price_source = f"Official FPL GW{previous_gameweek} picks purchase_price; exact squad identity match; previous GW not a Free Hit"
            source_type = "PREVIOUS_GAMEWEEK_PICKS"
            archive = {
                "source_type": source_type,
                "previous_gameweek_picks": base64.b64encode(previous_picks_raw).decode("ascii"),
                "history": base64.b64encode(history_raw).decode("ascii"),
            }
            source_urls = [previous_picks_url, history_url]
        else:
            gw1_raw = fetch(gw1_url)
            transfers_raw = fetch(transfers_url)
            bootstrap_raw = fetch(bootstrap_url)
            gw1_payload = _json(gw1_raw, "GW1 picks")
            try:
                transfers_payload = json.loads(transfers_raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as parse_error:
                raise CaptureError("transfer history response is not valid JSON") from parse_error
            if not isinstance(transfers_payload, list):
                raise CaptureError("transfer history response must be a JSON list")
            bootstrap_payload = _json(bootstrap_raw, "FPL bootstrap")
            squad = reconstruct_purchase_prices(
                gw1_payload, transfers_payload, history_payload, gameweek,
                expected_element_ids, bootstrap_payload,
            )
            purchase_price_source = "FPL GW1 picks; missing initial prices derived from bootstrap now_cost minus cost_change_start; chronological transfer-in costs applied; free-hit event transfers excluded"
            source_type = "FPL_SEASON_HISTORY_RECONSTRUCTION"
            archive = {
                "source_type": source_type,
                "previous_gameweek_picks": base64.b64encode(previous_picks_raw).decode("ascii"),
                "gw1_picks": base64.b64encode(gw1_raw).decode("ascii"),
                "transfers": base64.b64encode(transfers_raw).decode("ascii"),
                "history": base64.b64encode(history_raw).decode("ascii"),
                "bootstrap": base64.b64encode(bootstrap_raw).decode("ascii"),
            }
            source_urls = [previous_picks_url, gw1_url, transfers_url, history_url, bootstrap_url]
        archive_raw = json.dumps(archive, sort_keys=True, separators=(",", ":")).encode("utf-8")
        captured_at = utc_now()
        return {
            "manager_context_capture": {
                "team_id": team_id,
                "gameweek": gameweek,
                "captured_at_utc": captured_at,
                "source_url": target_url,
                "source_type": "USER_CONFIRMED_SQUAD_WITH_FPL_HISTORY_PRICES",
                "price_source_type": source_type,
                "identity_verification_method": "user-confirmed GW squad IDs cross-checked against official prior-GW picks or GW1 picks and season transfer history",
                "source_urls": source_urls,
                "raw_sha256": hashlib.sha256(archive_raw).hexdigest(),
                "raw_response_base64": base64.b64encode(archive_raw).decode("ascii"),
                "row_count": 15,
                "identity_verified": True,
            },
            "manager_context": {
                "squad_snapshot": squad,
                "bank": expected_bank,
                "free_transfers": free_transfers,
                "personal_risk_profile": personal_risk_profile,
                "formation": formation,
                "starting_xi": sorted(starting_xi_ids) if starting_xi_ids is not None else None,
                "entry_history": {},
                "purchase_price_source": purchase_price_source,
            },
        }

    captured_at = utc_now()
    payload = _json(raw, "FPL manager picks")
    picks = payload.get("picks")
    history = payload.get("entry_history")
    if not isinstance(picks, list) or not isinstance(history, dict):
        raise CaptureError("FPL response is missing picks or entry_history")
    if len(picks) != 15:
        raise CaptureError(f"expected 15 squad picks, received {len(picks)}")
    if history.get("event") != gameweek:
        raise CaptureError(f"FPL response event {history.get('event')!r} does not match requested GW{gameweek}")

    squad = []
    seen: set[int] = set()
    for row in picks:
        element = row.get("element")
        if isinstance(element, bool) or not isinstance(element, int) or element < 1:
            raise CaptureError("pick contains invalid FPL element ID")
        if element in seen:
            raise CaptureError(f"duplicate FPL element ID {element}")
        seen.add(element)
        price = _valid_price(row.get("purchase_price"), f"purchase_price for player {element}")
        squad.append({"fpl_element_id": element, "purchase_price": price / 10})

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

    return {
        "manager_context_capture": {
            "team_id": team_id,
            "gameweek": gameweek,
            "captured_at_utc": captured_at,
            "source_url": target_url,
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_response_base64": base64.b64encode(raw).decode("ascii"),
            "row_count": len(squad),
            "identity_verified": expected_element_ids is None or seen == expected_element_ids,
        },
        "manager_context": {
            "squad_snapshot": squad,
            "bank": bank,
            "free_transfers": free_transfers,
            "personal_risk_profile": personal_risk_profile,
            "formation": formation,
            "starting_xi": sorted(starting_xi_ids) if starting_xi_ids is not None else None,
            "entry_history": history,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-id", type=int, required=True)
    parser.add_argument("--gameweek", type=int, required=True)
    parser.add_argument("--expected-element-ids", default="")
    parser.add_argument("--expected-bank", type=float)
    parser.add_argument("--free-transfers", type=int, required=True)
    parser.add_argument("--personal-risk-profile", default="aggressive")
    parser.add_argument("--formation", default="4-3-3")
    parser.add_argument("--starting-xi-ids", default="")
    parser.add_argument("--allow-user-confirmed-fallback", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expected = {int(value) for value in args.expected_element_ids.split(",") if value.strip()}
    starting_xi = {int(value) for value in args.starting_xi_ids.split(",") if value.strip()}
    result = capture_manager_context(
        args.team_id, args.gameweek, expected_element_ids=expected or None,
        expected_bank=args.expected_bank, free_transfers=args.free_transfers,
        personal_risk_profile=args.personal_risk_profile, formation=args.formation,
        starting_xi_ids=starting_xi or None,
        allow_user_confirmed_fallback=args.allow_user_confirmed_fallback,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "team_id": args.team_id,
        "gameweek": args.gameweek,
        "squad_rows": result["manager_context_capture"]["row_count"],
        "identity_verified": result["manager_context_capture"]["identity_verified"],
        "bank": result["manager_context"]["bank"],
        "free_transfers": result["manager_context"]["free_transfers"],
        "raw_sha256": result["manager_context_capture"]["raw_sha256"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
