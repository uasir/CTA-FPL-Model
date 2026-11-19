#!/usr/bin/env python3
"""CTA–FPL v1.0 experimental feature pipeline. Python standard library only."""
from __future__ import annotations
import argparse, csv, json
from collections import defaultdict, Counter
from pathlib import Path

PITCH_X, PITCH_Y = 120.0, 80.0
GRID_X, GRID_Y = 16, 12

def name_of(obj):
    return ((obj or {}).get("name") or "").strip()

def event_type(e):
    return name_of(e.get("type"))

def player_of(e):
    return name_of(e.get("player"))

def player_identity(value):
    if not isinstance(value, dict):
        return None
    player_id = value.get("id")
    player_name = name_of(value)
    if player_id is None:
        if player_name:
            raise ValueError("StatsBomb player has a name but no ID; refusing name-keyed aggregation")
        return None
    return str(player_id), player_name

def set_player_name(counter, player_name):
    if not player_name:
        return
    existing = counter.get("statsbomb_player_name")
    if existing and existing != player_name:
        raise ValueError(
            f"Conflicting names for StatsBomb player ID: {existing!r} vs {player_name!r}"
        )
    counter["statsbomb_player_name"] = player_name

def team_of(e):
    return name_of(e.get("team"))

def possession_team_of(e):
    return name_of(e.get("possession_team")) or team_of(e)

def point(value):
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None
    return None

def action_locations(e):
    typ = event_type(e)
    start = point(e.get("location"))
    if typ == "Pass":
        end = point((e.get("pass") or {}).get("end_location"))
    elif typ == "Carry":
        end = point((e.get("carry") or {}).get("end_location"))
    else:
        end = None
    return start, end

def completed_pass(e):
    return event_type(e) == "Pass" and not (e.get("pass") or {}).get("outcome")

def load_directions(path):
    """Optional overrides: match_id,period,team,attacks_right.

    StatsBomb event coordinates are already normalised so the possession team
    attacks toward x=120. The run() path fills missing keys with True and
    rejects False overrides to prevent accidental double-flipping.
    """
    result = {}
    if not path or not Path(path).exists():
        return result
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = str(row["attacks_right"]).strip().lower()
            if raw not in {"true", "false", "1", "0", "yes", "no"}:
                raise ValueError(f"Invalid attacks_right value: {raw}")
            right = raw in {"true", "1", "yes"}
            result[(str(row["match_id"]), int(row["period"]), row["team"])] = right
    return result

def orient(p, attacks_right):
    if p is None:
        return None
    x, y = p
    return (x, y) if attacks_right else (PITCH_X - x, PITCH_Y - y)

def complete_statsbomb_directions(events, overrides=None):
    """Fill every StatsBomb possession-team/period key with attack-right=True.

    StatsBomb event coordinates are possession-oriented: the team in
    possession attacks toward x=120. A False override would double-flip the
    already-normalised coordinates and is therefore rejected.
    """
    directions = dict(overrides or {})
    false_keys = [key for key, value in directions.items() if not value]
    if false_keys:
        raise ValueError(
            "StatsBomb coordinates are already normalised toward x=120; "
            f"attacks_right must be true. Invalid keys: {false_keys[:5]}"
        )
    for e in events:
        key = (str(e.get("_match_id")), int(e.get("period") or 0),
               possession_team_of(e))
        directions.setdefault(key, True)
    return directions

def grid_cell(p):
    if p is None:
        return None
    x, y = p
    ix = min(GRID_X - 1, max(0, int(x / PITCH_X * GRID_X)))
    iy = min(GRID_Y - 1, max(0, int(y / PITCH_Y * GRID_Y)))
    return iy * GRID_X + ix

def read_event_files(folder):
    matches = []
    for path in sorted(Path(folder).glob("*.json")):
        with open(path, encoding="utf-8") as f:
            events = json.load(f)
        if isinstance(events, list):
            matches.append((path.stem, events))
    return matches

def flatten_matches(matches):
    out = []
    for match_id, events in matches:
        for index, event in enumerate(events):
            if isinstance(event, dict):
                row = dict(event)
                row["_match_id"] = str(match_id)
                row["_event_index"] = index
                out.append(row)
    return out

def audit_360(events, three_sixty_dir):
    """Audit 360 links using match-scoped (match_id, event_uuid) keys."""
    event_keys = {
        (str(event.get("_match_id")), str(event.get("id")))
        for event in events
        if event.get("_match_id") is not None and event.get("id") is not None
    }
    frames = []
    for path in sorted(Path(three_sixty_dir).glob("*.json")):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list):
            frames.extend((str(path.stem), frame) for frame in data if isinstance(frame, dict))

    frame_keys = [
        (match_id, str(frame.get("event_uuid")))
        for match_id, frame in frames
        if frame.get("event_uuid") is not None
    ]
    counts = Counter(frame_keys)
    matched_keys = set(frame_keys) & event_keys
    matched = sum(key in event_keys for key in frame_keys)
    unique_uuids = {event_uuid for _, event_uuid in frame_keys}
    return {
        "frames": len(frames),
        "frames_with_event_uuid": len(frame_keys),
        "unique_event_uuids": len(unique_uuids),
        "unique_match_event_keys": len(set(frame_keys)),
        "duplicate_frame_event_uuids": sum(count - 1 for count in counts.values() if count > 1),
        "matched_frame_uuids": matched,
        "unmatched_frame_uuids": len(frame_keys) - matched,
        "frame_to_event_join_rate": round(matched / len(frame_keys), 6) if frame_keys else None,
        "event_coverage_with_frame": round(len(matched_keys) / len(event_keys), 6) if event_keys else None
    }

def fit_xt(events, directions, iterations=1000, tolerance=1e-11, fit_match_ids=None):
    """Conventional action-based xT; optionally fit on an explicit training-match subset."""
    if fit_match_ids is not None:
        fit_match_ids = {str(value) for value in fit_match_ids}
        available_match_ids = {str(event.get("_match_id")) for event in events}
        unknown = fit_match_ids - available_match_ids
        if unknown:
            raise ValueError(f"xT fit match IDs are absent from input: {sorted(unknown)}")
        if not fit_match_ids:
            raise ValueError("xT fit match ID subset cannot be empty")
        events = [event for event in events if str(event.get("_match_id")) in fit_match_ids]
    moves = [Counter() for _ in range(GRID_X * GRID_Y)]
    move_n = [0] * (GRID_X * GRID_Y)
    shots = [0] * (GRID_X * GRID_Y)
    goals = [0] * (GRID_X * GRID_Y)
    usable_moves = 0
    for e in events:
        key = (e["_match_id"], int(e.get("period") or 0), possession_team_of(e))
        if key not in directions:
            continue
        right = directions[key]
        typ = event_type(e)
        if typ == "Shot":
            c = grid_cell(orient(point(e.get("location")), right))
            if c is not None:
                shots[c] += 1
                if name_of((e.get("shot") or {}).get("outcome")) == "Goal":
                    goals[c] += 1
        elif typ in {"Pass", "Carry"} and (typ == "Carry" or completed_pass(e)):
            start, end = action_locations(e)
            a = grid_cell(orient(start, right))
            b = grid_cell(orient(end, right))
            if a is not None and b is not None:
                moves[a][b] += 1
                move_n[a] += 1
                usable_moves += 1
    total_shots, total_goals = sum(shots), sum(goals)
    if total_shots == 0:
        return None, {"xt_status": "not_fitted_no_directional_shots",
                      "xt_shots": 0, "xt_usable_moves": usable_moves}
    global_goal_rate = total_goals / total_shots
    p_shot = []
    p_goal = []
    p_move = []
    for i in range(GRID_X * GRID_Y):
        denom = shots[i] + move_n[i]
        p_shot.append(shots[i] / denom if denom else 0.0)
        p_move.append(move_n[i] / denom if denom else 0.0)
        # Same empirical-Bayes prior as the v0.2 pilot: five pseudo-shots.
        p_goal.append((goals[i] + 5.0 * global_goal_rate) / (shots[i] + 5.0))
    values = [0.0] * (GRID_X * GRID_Y)
    for _ in range(iterations):
        updated = [0.0] * (GRID_X * GRID_Y)
        delta = 0.0
        for i in range(GRID_X * GRID_Y):
            continuation = 0.0
            if move_n[i]:
                continuation = sum((count / move_n[i]) * values[j]
                                   for j, count in moves[i].items())
            updated[i] = p_shot[i] * p_goal[i] + p_move[i] * continuation
            delta = max(delta, abs(updated[i] - values[i]))
        values = updated
        if delta < tolerance:
            break
    grid = [{"x_cell": i % GRID_X, "y_cell": i // GRID_X,
             "xT": round(values[i], 8), "shots": shots[i], "moves": move_n[i]}
            for i in range(GRID_X * GRID_Y)]
    audit = {"xt_status": "exploratory_fit", "xt_shots": total_shots,
             "xt_goals": total_goals, "xt_usable_moves": usable_moves,
             "xt_global_goal_per_shot": round(global_goal_rate, 6),
             "xt_grid": f"{GRID_X}x{GRID_Y}",
             "xt_prior_pseudo_shots": 5,
             "xt_fit_match_ids": sorted(fit_match_ids) if fit_match_ids is not None else "ALL_INPUT_MATCHES",
             "xt_fit_match_count": len({str(event.get("_match_id")) for event in events})}
    return values, audit

def build_features(events, directions, xt_values, progressive_threshold=10.0):
    possessions = defaultdict(list)
    for e in events:
        poss = e.get("possession")
        if poss is None:
            continue
        key = (e["_match_id"], int(e.get("period") or 0),
               int(poss), possession_team_of(e))
        possessions[key].append(e)

    sequence_rows = []
    players = defaultdict(Counter)
    for (match_id, period, poss, team), seq in possessions.items():
        seq.sort(key=lambda x: x["_event_index"])
        dkey = (match_id, period, team)
        has_direction = dkey in directions
        right = directions.get(dkey, True)
        shots = [e for e in seq if event_type(e) == "Shot"]
        passes = [e for e in seq if event_type(e) == "Pass"]
        carries = [e for e in seq if event_type(e) == "Carry"]
        receipts = [e for e in seq if event_type(e) in {"Ball Receipt*", "Ball Receipt"}]
        box_entries = final_third_entries = progressive_actions = 0
        xt_gains = []
        for e in seq:
            typ = event_type(e)
            if typ not in {"Pass", "Carry"}:
                continue
            if typ == "Pass" and not completed_pass(e):
                continue
            start, end = action_locations(e)
            if has_direction:
                sn, en = orient(start, right), orient(end, right)
                if en:
                    if en[0] >= 102 and 18 <= en[1] <= 62:
                        box_entries += 1
                    if en[0] >= 80:
                        final_third_entries += 1
                if sn and en and en[0] - sn[0] >= progressive_threshold:
                    progressive_actions += 1
                if xt_values is not None:
                    a, b = grid_cell(sn), grid_cell(en)
                    if a is not None and b is not None:
                        xt_gains.append(xt_values[b] - xt_values[a])
        pressured = [e for e in seq if e.get("under_pressure")]
        pressured_receipts = sum(bool(e.get("under_pressure")) for e in receipts)
        observed_shot_xg = []
        for shot in shots:
            raw_xg = (shot.get("shot") or {}).get("statsbomb_xg")
            if raw_xg is not None:
                observed_shot_xg.append(float(raw_xg))
        shot_xg = sum(observed_shot_xg) if observed_shot_xg else None
        # Rule-based candidate flag only; not a validated danger label.
        nonshot_candidate = (not shots and has_direction and
                             (box_entries >= 1 or
                              (final_third_entries >= 2 and pressured_receipts >= 1)))
        classification = "shot_linked" if shots else (
            "non_shot_candidate" if nonshot_candidate else "other_possession")
        first, last = seq[0], seq[-1]
        start_clock = float(first.get("minute") or 0) * 60 + float(first.get("second") or 0)
        end_clock = float(last.get("minute") or 0) * 60 + float(last.get("second") or 0)
        names = sorted({player_of(e) for e in seq if player_of(e)})
        seq_id = f"{match_id}:{period}:{poss}:{team}"
        sequence_rows.append({
            "sequence_id": seq_id, "match_id": match_id, "period": period,
            "possession_id": poss, "team": team, "event_count": len(seq),
            "duration_seconds": round(max(0, end_clock - start_clock), 2),
            "players": "|".join(names), "passes": len(passes),
            "completed_passes": sum(completed_pass(e) for e in passes),
            "carries": len(carries), "receipts": len(receipts),
            "pressured_events": len(pressured),
            "pressured_receipts": pressured_receipts,
            "box_entries": box_entries if has_direction else "",
            "final_third_entries": final_third_entries if has_direction else "",
            "progressive_actions": progressive_actions if has_direction else "",
            "shot_count": len(shots), "shot_xg_observed_count": len(observed_shot_xg),
            "shot_xg_reference_only": round(shot_xg, 6) if shot_xg is not None else "",
            "mean_action_xt_gain": round(sum(xt_gains) / len(xt_gains), 6) if xt_gains else "",
            "positive_action_xt_gain_sum": round(sum(max(0, x) for x in xt_gains), 6) if xt_gains else "",
            "direction_available": has_direction, "sequence_class": classification
        })

        # Actor-based attribution; receiver gets a receipt count from pass recipient field.
        for e in seq:
            identity = player_identity(e.get("player"))
            typ = event_type(e)
            if identity:
                player_id, player_name = identity
                c = players[player_id]
                set_player_name(c, player_name)
                c["event_involvements"] += 1
                if typ == "Pass":
                    c["passes"] += 1
                    c["completed_passes"] += int(completed_pass(e))
                elif typ == "Carry":
                    c["carries"] += 1
                elif typ == "Shot":
                    c["shots"] += 1
                    raw_xg = (e.get("shot") or {}).get("statsbomb_xg")
                    if raw_xg is not None:
                        c["shot_xg_reference_only"] += float(raw_xg)
                        c["shot_xg_observed_count"] += 1
                elif typ in {"Ball Receipt*", "Ball Receipt"}:
                    c["receipts"] += 1
                c["pressured_events"] += int(bool(e.get("under_pressure")))
                if has_direction and typ in {"Pass", "Carry"} and (typ == "Carry" or completed_pass(e)):
                    st, en = action_locations(e)
                    stn, enn = orient(st, right), orient(en, right)
                    if enn:
                        c["box_entries"] += int(enn[0] >= 102 and 18 <= enn[1] <= 62)
                        c["final_third_entries"] += int(enn[0] >= 80)
                    c["progressive_actions"] += int(bool(stn and enn and enn[0] - stn[0] >= progressive_threshold))
                    if xt_values is not None:
                        a, b = grid_cell(stn), grid_cell(enn)
                        if a is not None and b is not None:
                            c["action_xt_gain_sum"] += xt_values[b] - xt_values[a]
                            c["action_xt_gain_n"] += 1
                if typ in {"Ball Receipt*", "Ball Receipt"} and e.get("under_pressure"):
                    c["pressured_receipts"] += 1
            if typ == "Pass":
                recipient_identity = player_identity((e.get("pass") or {}).get("recipient"))
                if recipient_identity:
                    recipient_id, recipient_name = recipient_identity
                    recipient_counter = players[recipient_id]
                    set_player_name(recipient_counter, recipient_name)
                    recipient_counter["passes_received"] += 1
                    if e.get("under_pressure"):
                        recipient_counter["pressured_passes_received"] += 1
        sequence_identities = {}
        for e in seq:
            identity = player_identity(e.get("player"))
            if identity:
                sequence_identities[identity[0]] = identity[1]
        for player_id, player_name in sequence_identities.items():
            counter = players[player_id]
            set_player_name(counter, player_name)
            counter["sequences_involved"] += 1
            counter["shot_linked_sequences"] += int(classification == "shot_linked")
            counter["non_shot_candidate_sequences"] += int(classification == "non_shot_candidate")

    return sequence_rows, players

def load_minutes(path):
    values = {}
    if path and Path(path).exists():
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                values[row["player_name"]] = float(row.get("minutes") or 0)
    return values

def load_player_map(path):
    values = {}
    if path and Path(path).exists():
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                values[row["statsbomb_player_name"]] = row.get("fpl_player_name", "")
    return values

def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Player counters are sparse: different players naturally have different
    # action keys. Preserve first-seen column order while taking the union.
    fields = list(dict.fromkeys(key for row in rows for key in row.keys()))
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)

def run(args):
    matches = read_event_files(args.events_dir)
    if not matches:
        raise SystemExit(f"No StatsBomb event JSON files found in {args.events_dir}")
    events = flatten_matches(matches)
    directions = complete_statsbomb_directions(
        events, load_directions(args.direction_map))
    requested_fit_ids = [value.strip() for value in str(args.xt_fit_match_ids or "").split(",") if value.strip()]
    xt_values, xt_audit = fit_xt(
        events, directions, fit_match_ids=requested_fit_ids or None
    )
    sequences, players = build_features(events, directions, xt_values)
    player_rows = []
    for statsbomb_player_id, counts in sorted(players.items()):
        mins = 0.0  # Name-based minutes are intentionally not trusted or applied.
        player_name = counts.get("statsbomb_player_name", "")
        metrics = {key: value for key, value in counts.items() if key != "statsbomb_player_name"}
        row = {"statsbomb_player_id": statsbomb_player_id, "statsbomb_player_name": player_name,
               "fpl_player_name": "", **metrics, "minutes": ""}
        for metric in ("sequences_involved", "non_shot_candidate_sequences",
                       "shot_linked_sequences", "box_entries", "final_third_entries",
                       "progressive_actions", "pressured_receipts"):
            if metric in counts:
                row[metric + "_per90"] = round(counts[metric] * 90 / mins, 4) if mins > 0 else ""
        row["action_xt_gain_per90"] = (
            round(counts["action_xt_gain_sum"] * 90 / mins, 4)
            if mins > 0 and counts["action_xt_gain_n"] else "")
        row["mean_action_xt_gain"] = (
            round(counts["action_xt_gain_sum"] / counts["action_xt_gain_n"], 6)
            if counts["action_xt_gain_n"] else "")
        player_rows.append(row)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "sequences.csv", sequences)
    write_csv(out / "player_features.csv", player_rows)
    if xt_values is not None:
        write_csv(out / "xt_grid.csv", [
            {"x_cell": i % GRID_X, "y_cell": i // GRID_X, "xT": round(v, 8)}
            for i, v in enumerate(xt_values)])
    audit = {
        "model": "CTA-FPL feature pipeline",
        "version": "1.0.3-experimental",
        "matches_processed": len(matches), "events_processed": len(events),
        "sequences_processed": len(sequences), "players_observed": len(players),
        "direction_map_entries": len(directions),
        "directional_features_available": bool(directions),
        "cta_composite_score": "not produced; not calibrated",
        "validation_status": "not validated for FPL prediction",
        "xt": xt_audit,
        "limitations": [
            "non_shot_candidate is a rule-based screening flag, not a human-verified danger label",
            "space creation and defensive destabilisation are not inferred from event data",
            "per-90 metrics require trusted player minutes",
            "FPL joins require a verified StatsBomb player-ID crosswalk; names are display metadata only",
            "StatsBomb coordinates are possession-oriented; false direction overrides are invalid"
        ]
    }
    if args.three_sixty_dir and Path(args.three_sixty_dir).exists():
        audit["statsbomb_360_audit"] = audit_360(events, args.three_sixty_dir)
    with open(out / "audit.json", "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2)
    print(json.dumps(audit, indent=2))

def main():
    p = argparse.ArgumentParser(description="CTA–FPL v1.0.3 experimental feature pipeline")
    p.add_argument("--events-dir", default="data/events")
    p.add_argument("--three-sixty-dir", default="data/three-sixty")
    p.add_argument("--direction-map", default="data/direction_map.csv")
    p.add_argument("--player-map", default="data/player_id_map.csv")
    p.add_argument("--minutes", default="data/player_minutes.csv")
    p.add_argument("--output-dir", default="outputs")
    p.add_argument("--xt-fit-match-ids", default="",
                   help="Optional comma-separated training match IDs used to fit xT; features are still extracted for all input matches.")
    run(p.parse_args())

if __name__ == "__main__":
    main()
