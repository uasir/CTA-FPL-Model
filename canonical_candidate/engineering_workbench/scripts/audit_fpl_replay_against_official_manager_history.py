#!/usr/bin/env python3
"""Audit the one-gameweek replay scorer against official historical FPL teams.

Only aggregate validation results are written. Manager IDs, picks and player-
level rows remain in runner memory and are never exported by this script.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from capture_fpl_ranked_manager_picks import (
    BASE, PAGE_SIZE, choose_pages, fetch_json, select_managers,
)
from replay_fpl_gameweek_decisions import replay_gameweek

ELEMENT_TYPE = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
CHIP_TYPE = {
    None: None,
    "bboost": "bench_boost",
    "3xc": "triple_captain",
    "freehit": "free_hit",
    "wildcard": "wildcard",
}


def build_replay_record(picks_payload, live_payload, position_by_player):
    history = picks_payload.get("entry_history") or {}
    picks = picks_payload.get("picks") or []
    if len(picks) != 15:
        raise ValueError("historical picks response does not contain 15 players")
    ordered = sorted(picks, key=lambda pick: int(pick.get("position", 0)))
    if [int(pick.get("position", 0)) for pick in ordered] != list(range(1, 16)):
        raise ValueError("historical pick slots are not exactly 1 through 15")

    ids = [str(int(pick["element"])) for pick in ordered]
    xi = [str(int(pick["element"])) for pick in ordered if int(pick["position"]) <= 11]
    bench_slots = [str(int(pick["element"])) for pick in ordered if int(pick["position"]) >= 12]
    # The historical picks endpoint exposes four bench slots, but the reserve
    # goalkeeper is not guaranteed to occupy slot 15. Normalize to the replay
    # contract's three ordered outfield substitutes followed by the goalkeeper,
    # preserving the relative order of the three outfield slots.
    bench_outfield = [player_id for player_id in bench_slots
                      if position_by_player.get(player_id) != "GKP"]
    bench_goalkeepers = [player_id for player_id in bench_slots
                         if position_by_player.get(player_id) == "GKP"]
    if len(bench_outfield) != 3 or len(bench_goalkeepers) != 1:
        raise ValueError("historical bench must contain three outfield players and one goalkeeper")
    bench = bench_outfield + bench_goalkeepers
    captain_rows = [pick for pick in ordered if pick.get("is_captain")]
    vice_rows = [pick for pick in ordered if pick.get("is_vice_captain")]
    if len(captain_rows) != 1 or len(vice_rows) != 1:
        raise ValueError("historical picks must identify exactly one captain and vice-captain")

    live_elements = live_payload.get("elements") or []
    live_by_id = {str(int(row["id"])): row.get("stats") or {} for row in live_elements}
    points, minutes, played, positions = {}, {}, {}, {}
    for player_id in ids:
        if player_id not in live_by_id:
            raise ValueError("official live event is missing a selected player")
        stats = live_by_id[player_id]
        points[player_id] = float(stats["total_points"])
        minutes[player_id] = float(stats["minutes"])
        cards = float(stats.get("yellow_cards", 0) or 0) + float(stats.get("red_cards", 0) or 0)
        played[player_id] = minutes[player_id] > 0 or cards > 0
        if player_id not in position_by_player:
            raise ValueError("bootstrap is missing a selected player's position")
        positions[player_id] = position_by_player[player_id]

    active_chip = picks_payload.get("active_chip")
    if active_chip not in CHIP_TYPE:
        raise ValueError(f"unrecognized active chip: {active_chip}")
    hit_cost = int(history.get("event_transfers_cost", 0) or 0)
    decision = {
        "action_legality_verified": True,
        "starting_xi": xi,
        "bench_order": bench,
        "captain": str(int(captain_rows[0]["element"])),
        "vice_captain": str(int(vice_rows[0]["element"])),
        "transfers_made": int(history.get("event_transfers", 0) or 0),
        "free_transfers": 0,
        "transfer_hit_cost": hit_cost,
        "chip": CHIP_TYPE[active_chip],
        "chip_legality_verified": active_chip is not None,
    }
    official_team_points = history.get("points")
    if official_team_points is None:
        raise ValueError("historical entry history is missing official points")
    auto_subs = picks_payload.get("automatic_subs") or []
    official_sub_pairs = sorted(
        (str(int(item["element_in"])), str(int(item["element_out"])))
        for item in auto_subs
        if item.get("element_in") is not None and item.get("element_out") is not None
    )
    return {
        "decision": decision,
        "official_points": points,
        "minutes": minutes,
        "played_by_player": played,
        "positions": positions,
        "official_team_points": float(official_team_points),
        "official_net_points": float(official_team_points) - hit_cost,
        "official_sub_pairs": official_sub_pairs,
        "official_sub_pairs_ordered": [
            (str(int(item["element_in"])), str(int(item["element_out"])))
            for item in auto_subs
            if item.get("element_in") is not None and item.get("element_out") is not None
        ],
        "starting_xi": xi,
        "bench_order": bench,
        "event_transfers_cost": hit_cost,
    }


def audit_record(picks_payload, live_payload, position_by_player):
    record = build_replay_record(picks_payload, live_payload, position_by_player)
    replay = replay_gameweek(
        record["decision"], record["official_points"], record["minutes"],
        record["positions"], played_by_player=record["played_by_player"],
    )
    replay_sub_pairs = sorted((item["in"], item["out"]) for item in replay["substitutions"])
    replay_sub_pairs_ordered = [(item["in"], item["out"]) for item in replay["substitutions"]]
    positions = record["positions"]
    bench_slot = {player_id: index + 1 for index, player_id in enumerate(record["bench_order"][:3])}
    official_ordered = record["official_sub_pairs_ordered"]
    official_position_pairs = sorted((positions[in_id], positions[out_id]) for in_id, out_id in official_ordered)
    replay_position_pairs = sorted((positions[in_id], positions[out_id]) for in_id, out_id in replay_sub_pairs_ordered)
    official_slots = [bench_slot.get(in_id, 0) for in_id, _ in official_ordered]
    replay_slots = [bench_slot.get(in_id, 0) for in_id, _ in replay_sub_pairs_ordered]
    return {
        "replay_net_points": replay["net_points"],
        "replay_gross_points": replay["gross_points"],
        "official_team_points": record["official_team_points"],
        "net_point_difference": replay["net_points"] - record["official_net_points"],
        "gross_point_difference": replay["gross_points"] - record["official_team_points"],
        "autosub_pairs_match": replay_sub_pairs == record["official_sub_pairs"],
"autosub_position_pairs_match": replay_position_pairs == official_position_pairs,
"autosub_count_match": len(replay_sub_pairs_ordered) == len(official_ordered),
"official_sub_count": len(official_ordered),
"replay_sub_count": len(replay_sub_pairs_ordered),
"official_bench_slots": official_slots,
"replay_bench_slots": replay_slots,
"official_position_pairs": official_position_pairs,
"replay_position_pairs": replay_position_pairs,
        "transfer_hit_cost": record["event_transfers_cost"],
    }


def audit_sample(bootstrap, rank_limit=1000, sample_size=100, seed=20261119,
                 workers=4, delay=0.5, max_gameweeks=10, fetch=fetch_json):
    events = [event for event in bootstrap.get("events", []) if event.get("finished")]
    events = sorted(events, key=lambda event: int(event["id"]))[-max_gameweeks:]
    if not events:
        raise ValueError("No completed gameweeks are available for replay validation")
    page_numbers = choose_pages(rank_limit, sample_size, seed)
    page_payloads = {}

    def get_page(page):
        url = f"{BASE}/leagues-classic/314/standings/?page_standings={page}"
        return page, fetch(url, delay=delay)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(get_page, page) for page in page_numbers]
        for future in as_completed(futures):
            page, payload = future.result()
            page_payloads[page] = payload
    managers = select_managers(page_payloads, sample_size, rank_limit, seed)

    position_by_player = {
        str(int(element["id"])): ELEMENT_TYPE[int(element["element_type"])]
        for element in bootstrap.get("elements", [])
    }
    live_by_event = {}
    for event in events:
        live_by_event[int(event["id"])] = fetch(
            f"{BASE}/event/{int(event['id'])}/live/", delay=delay
        )

    requests = [
        (manager, event)
        for manager in managers
        for event in events
    ]
    results = []

    def get_picks(manager, event):
        event_id = int(event["id"])
        url = f"{BASE}/entry/{manager['entry_id']}/event/{event_id}/picks/"
        return manager, event, fetch(url, delay=delay)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(get_picks, manager, event) for manager, event in requests]
        for future in as_completed(futures):
            manager, event, payload = future.result()
            results.append((int(event["id"]), payload))

    by_event = defaultdict(list)
    for event_id, payload in results:
        by_event[event_id].append(payload)

    event_reports = []
    error_counts = Counter()
    total_records = 0
    total_exact_net = 0
    total_exact_gross = 0
    total_autosub_matches = 0
    total_autosub_comparable = 0
    absolute_net_differences = []
    autosub_position_pair_matches = 0
    autosub_count_matches = 0
    official_bench_priority_usage = Counter()
    replay_bench_priority_usage = Counter()
    autosub_mismatch_signatures = Counter()
    for event in events:
        event_id = int(event["id"])
        live = live_by_event[event_id]
        n = net_exact = gross_exact = autosub_match = autosub_comparable = 0
        event_position_pair_matches = 0
        event_count_matches = 0
        differences = []
        for payload in by_event[event_id]:
            try:
                result = audit_record(payload, live, position_by_player)
            except (KeyError, TypeError, ValueError) as exc:
                error_counts[str(exc)] += 1
                continue
            n += 1
            net_exact += int(result["net_point_difference"] == 0)
            gross_exact += int(result["gross_point_difference"] == 0)
            if payload.get("automatic_subs") is not None:
                autosub_comparable += 1
                autosub_match += int(result["autosub_pairs_match"])
                autosub_position_pair_matches += int(result["autosub_position_pairs_match"])
                autosub_count_matches += int(result["autosub_count_match"])
                event_position_pair_matches += int(result["autosub_position_pairs_match"])
                event_count_matches += int(result["autosub_count_match"])
                official_bench_priority_usage.update(str(slot) for slot in result["official_bench_slots"])
                replay_bench_priority_usage.update(str(slot) for slot in result["replay_bench_slots"])
                if not result["autosub_pairs_match"]:
                    signature = (
                        f"official_slots={result['official_bench_slots']};"
                        f"replay_slots={result['replay_bench_slots']};"
                        f"official_positions={result['official_position_pairs']};"
                        f"replay_positions={result['replay_position_pairs']};"
                        f"counts={result['official_sub_count']}:{result['replay_sub_count']}"
                    )
                    autosub_mismatch_signatures[signature] += 1
            differences.append(abs(result["net_point_difference"]))
        total_records += n
        total_exact_net += net_exact
        total_exact_gross += gross_exact
        total_autosub_matches += autosub_match
        total_autosub_comparable += autosub_comparable
        absolute_net_differences.extend(differences)
        event_reports.append({
            "gameweek": event_id,
            "n_valid_manager_records": n,
            "exact_net_team_score_matches": net_exact,
            "net_team_score_match_rate": net_exact / n if n else None,
            "exact_gross_team_score_matches": gross_exact,
            "autosub_comparisons": autosub_comparable,
            "autosub_exact_match_rate": autosub_match / autosub_comparable if autosub_comparable else None,
"autosub_position_pair_match_rate": autosub_position_pair_matches / autosub_comparable if autosub_comparable else None,
"autosub_count_match_rate": autosub_count_matches / autosub_comparable if autosub_comparable else None,
            "mean_absolute_net_score_difference": sum(differences) / len(differences) if differences else None,
        })

    return {
        "status": "RESEARCH_ONLY_OFFICIAL_HISTORY_REPLAY_AUDIT",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "rank_cohort": "current overall global rank 1..rank_limit, stratified sample",
        "rank_limit": rank_limit,
        "sample_size_requested": sample_size,
        "sampled_manager_count": len(managers),
        "sampled_manager_gameweek_records_expected": len(managers) * len(events),
        "gameweeks": [int(event["id"]) for event in events],
        "valid_manager_gameweek_records": total_records,
        "exact_net_team_score_matches": total_exact_net,
        "net_team_score_match_rate": total_exact_net / total_records if total_records else None,
        "exact_gross_team_score_matches": total_exact_gross,
        "autosub_comparisons": total_autosub_comparable,
        "autosub_exact_match_rate": total_autosub_matches / total_autosub_comparable if total_autosub_comparable else None,
        "autosub_position_pair_match_rate": autosub_position_pair_matches / total_autosub_comparable if total_autosub_comparable else None,
        "autosub_count_match_rate": autosub_count_matches / total_autosub_comparable if total_autosub_comparable else None,
        "official_bench_priority_usage": dict(official_bench_priority_usage),
        "replay_bench_priority_usage": dict(replay_bench_priority_usage),
        "top_autosub_mismatch_signatures": [
            {"signature": signature, "records": count}
            for signature, count in autosub_mismatch_signatures.most_common(12)
        ],
        "mean_absolute_net_score_difference": (
            sum(absolute_net_differences) / len(absolute_net_differences)
            if absolute_net_differences else None
        ),
        "error_categories": dict(error_counts),
        "by_gameweek": event_reports,
        "privacy": "No manager identifiers, raw picks or player-level outcomes are written to the report.",
        "limitations": [
            "Current-rank sampling is survivor- and rank-conditioned; this is a scoring-engine audit, not a representative manager-performance study.",
            "Official FPL entry_history.points is treated as gross before hits; event_transfers_cost is subtracted for net comparison.",
            "The replay audit validates scoring and autosubs only; it does not evaluate recommendation quality or decision value.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rank-limit", type=int, default=1000)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20261119)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--max-gameweeks", type=int, default=10)
    args = parser.parse_args()
    bootstrap = fetch_json(f"{BASE}/bootstrap-static/", delay=args.delay)
    report = audit_sample(
        bootstrap, rank_limit=args.rank_limit, sample_size=args.sample_size,
        seed=args.seed, workers=args.workers, delay=args.delay,
        max_gameweeks=args.max_gameweeks,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
