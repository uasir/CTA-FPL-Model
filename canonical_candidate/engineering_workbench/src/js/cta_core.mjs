export const PITCH_X = 120;
export const PITCH_Y = 80;
export const GRID_X = 16;
export const GRID_Y = 12;

export const SEQUENCE_FEATURES = [
  "sequence_id",
  "event_count",
  "duration_seconds",
  "players",
  "passes",
  "completed_passes",
  "carries",
  "receipts",
  "pressured_events",
  "pressured_receipts",
  "box_entries",
  "final_third_entries",
  "progressive_actions",
  "shot_count",
  "shot_xg_reference_only",
  "mean_action_xt_gain",
  "positive_action_xt_gain_sum",
  "direction_available",
  "sequence_class",
];

export const PLAYER_FEATURES = [
  "event_involvements",
  "passes",
  "completed_passes",
  "pressured_events",
  "box_entries",
  "final_third_entries",
  "progressive_actions",
  "action_xt_gain_sum",
  "action_xt_gain_n",
  "passes_received",
  "pressured_passes_received",
  "receipts",
  "carries",
  "sequences_involved",
  "shot_linked_sequences",
  "non_shot_candidate_sequences",
  "shots",
  "shot_xg_reference_only",
  "mean_action_xt_gain",
  "pressured_receipts",
];

const RECEIPT_TYPES = new Set(["Ball Receipt*", "Ball Receipt"]);
const ACTION_TYPES = new Set(["Pass", "Carry"]);

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function nameOf(value) {
  return typeof value?.name === "string" ? value.name.trim() : "";
}

function eventType(event) {
  return nameOf(event.type);
}

function playerOf(event) {
  return nameOf(event.player);
}

function teamOf(event) {
  return nameOf(event.team);
}

function possessionTeamOf(event) {
  return nameOf(event.possession_team) || teamOf(event);
}

function numberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function point(value) {
  if (!Array.isArray(value) || value.length < 2) return null;
  const x = numberOrNull(value[0]);
  const y = numberOrNull(value[1]);
  return x === null || y === null ? null : [x, y];
}

function actionLocations(event) {
  const start = point(event.location);
  const type = eventType(event);
  let end = null;
  if (type === "Pass") end = point(event.pass?.end_location);
  else if (type === "Carry") end = point(event.carry?.end_location);
  return [start, end];
}

function completedPass(event) {
  return eventType(event) === "Pass" && !event.pass?.outcome;
}

function directionKey(matchId, period, team) {
  return JSON.stringify([String(matchId), Number(period) || 0, String(team ?? "")]);
}

function directionKeyForEvent(event) {
  return directionKey(
    event._match_id,
    Math.trunc(Number(event.period) || 0),
    possessionTeamOf(event),
  );
}

function orient(location, attacksRight) {
  if (!location) return null;
  const [x, y] = location;
  return attacksRight ? [x, y] : [PITCH_X - x, PITCH_Y - y];
}

function roundHalfEven(value, digits) {
  const factor = 10 ** digits;
  const scaled = value * factor;
  const lower = Math.floor(scaled);
  const fraction = scaled - lower;
  const tieEpsilon = Number.EPSILON * Math.max(1, Math.abs(scaled)) * 2;
  let rounded;
  if (Math.abs(fraction - 0.5) <= tieEpsilon) {
    rounded = lower % 2 === 0 ? lower : lower + 1;
  } else {
    rounded = Math.floor(scaled + 0.5);
  }
  return rounded / factor;
}

function gridCell(location) {
  if (!location) return null;
  const x = Math.min(GRID_X - 1, Math.max(0, Math.trunc((location[0] / PITCH_X) * GRID_X)));
  const y = Math.min(GRID_Y - 1, Math.max(0, Math.trunc((location[1] / PITCH_Y) * GRID_Y)));
  return y * GRID_X + x;
}

function parseCsvLine(line) {
  const values = [];
  let current = "";
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      if (quoted && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === "," && !quoted) {
      values.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  values.push(current);
  return values;
}

export function parseDirectionCsv(text) {
  const lines = text.split(/\r?\n/).filter((line) => line.length > 0);
  if (lines.length === 0) return new Map();
  const header = parseCsvLine(lines[0]);
  const required = ["match_id", "period", "team", "attacks_right"];
  if (required.some((field) => !header.includes(field))) {
    throw new Error(`Direction CSV must contain ${required.join(",")}`);
  }
  const column = Object.fromEntries(header.map((name, index) => [name, index]));
  const overrides = new Map();
  for (const line of lines.slice(1)) {
    const values = parseCsvLine(line);
    const raw = (values[column.attacks_right] ?? "").trim().toLowerCase();
    if (!["true", "false", "1", "0", "yes", "no"].includes(raw)) {
      throw new Error(`Invalid attacks_right value: ${raw}`);
    }
    const attacksRight = ["true", "1", "yes"].includes(raw);
    const key = directionKey(
      values[column.match_id],
      values[column.period],
      values[column.team],
    );
    overrides.set(key, attacksRight);
  }
  return overrides;
}

export function completeStatsBombDirections(events, overrides = new Map()) {
  const directions = new Map(overrides);
  for (const [key, value] of directions) {
    if (!value) {
      throw new Error(`StatsBomb direction override must be true: ${key}`);
    }
  }
  for (const event of events) {
    const key = directionKeyForEvent(event);
    if (!directions.has(key)) directions.set(key, true);
  }
  return directions;
}

export function fitXt(events, directions, iterations = 1000, tolerance = 1e-11) {
  const cells = GRID_X * GRID_Y;
  const moves = Array.from({ length: cells }, () => new Map());
  const moveCounts = Array(cells).fill(0);
  const shots = Array(cells).fill(0);
  const goals = Array(cells).fill(0);
  let usableMoves = 0;

  for (const event of events) {
    const key = directionKeyForEvent(event);
    if (!directions.has(key)) continue;
    const type = eventType(event);
    if (type === "Shot") {
      const cell = gridCell(orient(point(event.location), directions.get(key)));
      if (cell !== null) {
        shots[cell] += 1;
        if (nameOf(event.shot?.outcome) === "Goal") goals[cell] += 1;
      }
    } else if (ACTION_TYPES.has(type) && (type === "Carry" || completedPass(event))) {
      const [start, end] = actionLocations(event);
      const source = gridCell(orient(start, directions.get(key)));
      const destination = gridCell(orient(end, directions.get(key)));
      if (source !== null && destination !== null) {
        const destinations = moves[source];
        destinations.set(destination, (destinations.get(destination) ?? 0) + 1);
        moveCounts[source] += 1;
        usableMoves += 1;
      }
    }
  }

  const totalShots = shots.reduce((sum, value) => sum + value, 0);
  const totalGoals = goals.reduce((sum, value) => sum + value, 0);
  if (totalShots === 0) {
    return {
      values: null,
      audit: { xt_status: "not_fitted_no_directional_shots", xt_shots: 0, xt_usable_moves: usableMoves },
    };
  }

  const globalGoalRate = totalGoals / totalShots;
  const pShot = [];
  const pGoal = [];
  const pMove = [];
  for (let i = 0; i < cells; i += 1) {
    const denominator = shots[i] + moveCounts[i];
    pShot.push(denominator ? shots[i] / denominator : 0);
    pMove.push(denominator ? moveCounts[i] / denominator : 0);
    pGoal.push((goals[i] + 5 * globalGoalRate) / (shots[i] + 5));
  }

  let values = Array(cells).fill(0);
  for (let iteration = 0; iteration < iterations; iteration += 1) {
    const updated = Array(cells).fill(0);
    let delta = 0;
    for (let i = 0; i < cells; i += 1) {
      let continuation = 0;
      if (moveCounts[i]) {
        for (const [destination, count] of moves[i]) {
          continuation += (count / moveCounts[i]) * values[destination];
        }
      }
      updated[i] = pShot[i] * pGoal[i] + pMove[i] * continuation;
      delta = Math.max(delta, Math.abs(updated[i] - values[i]));
    }
    values = updated;
    if (delta < tolerance) break;
  }

  return {
    values,
    audit: {
      xt_status: "exploratory_fit",
      xt_shots: totalShots,
      xt_goals: totalGoals,
      xt_usable_moves: usableMoves,
      xt_global_goal_per_shot: roundHalfEven(globalGoalRate, 6),
      xt_grid: `${GRID_X}x${GRID_Y}`,
      xt_prior_pseudo_shots: 5,
    },
  };
}

function increment(counter, field, amount = 1) {
  counter[field] = (counter[field] ?? 0) + amount;
}

function numberOrZero(value) {
  return Number(value || 0);
}

export function buildFeatures(events, directions, xtValues) {
  const possessions = new Map();
  for (const event of events) {
    if (event.possession === null || event.possession === undefined) continue;
    const period = Math.trunc(Number(event.period) || 0);
    const possession = Math.trunc(Number(event.possession));
    const team = possessionTeamOf(event);
    const key = JSON.stringify([event._match_id, period, possession, team]);
    if (!possessions.has(key)) possessions.set(key, { matchId: event._match_id, period, possession, team, events: [] });
    possessions.get(key).events.push(event);
  }

  const sequenceRows = [];
  const players = new Map();
  const playerCounter = (name) => {
    if (!players.has(name)) players.set(name, {});
    return players.get(name);
  };

  for (const group of possessions.values()) {
    const sequence = group.events.sort((a, b) => a._event_index - b._event_index);
    const directionKeyValue = directionKey(group.matchId, group.period, group.team);
    const hasDirection = directions.has(directionKeyValue);
    const attacksRight = directions.get(directionKeyValue) ?? true;
    const shots = sequence.filter((event) => eventType(event) === "Shot");
    const passes = sequence.filter((event) => eventType(event) === "Pass");
    const carries = sequence.filter((event) => eventType(event) === "Carry");
    const receipts = sequence.filter((event) => RECEIPT_TYPES.has(eventType(event)));
    let boxEntries = 0;
    let finalThirdEntries = 0;
    let progressiveActions = 0;
    const xtGains = [];

    for (const event of sequence) {
      const type = eventType(event);
      if (!ACTION_TYPES.has(type)) continue;
      const [start, end] = actionLocations(event);
      if (hasDirection) {
        const startOriented = orient(start, attacksRight);
        const endOriented = orient(end, attacksRight);
        if (endOriented) {
          if (endOriented[0] >= 102 && endOriented[1] >= 18 && endOriented[1] <= 62) boxEntries += 1;
          if (endOriented[0] >= 80) finalThirdEntries += 1;
        }
        if (startOriented && endOriented && endOriented[0] - startOriented[0] >= 10) progressiveActions += 1;
        if (xtValues) {
          const source = gridCell(startOriented);
          const destination = gridCell(endOriented);
          if (source !== null && destination !== null) xtGains.push(xtValues[destination] - xtValues[source]);
        }
      }
    }

    const pressured = sequence.filter((event) => Boolean(event.under_pressure));
    const pressuredReceipts = receipts.reduce(
      (sum, event) => sum + Number(Boolean(event.under_pressure)),
      0,
    );
    const shotXg = shots.reduce((sum, event) => sum + numberOrZero(event.shot?.statsbomb_xg), 0);
    const nonShotCandidate = shots.length === 0
      && hasDirection
      && (boxEntries >= 1 || (finalThirdEntries >= 2 && pressuredReceipts >= 1));
    const classification = shots.length
      ? "shot_linked"
      : nonShotCandidate
        ? "non_shot_candidate"
        : "other_possession";
    const first = sequence[0];
    const last = sequence[sequence.length - 1];
    const startClock = numberOrZero(first.minute) * 60 + numberOrZero(first.second);
    const endClock = numberOrZero(last.minute) * 60 + numberOrZero(last.second);
    const names = [...new Set(sequence.map(playerOf).filter(Boolean))].sort();
    const sequenceId = `${group.matchId}:${group.period}:${group.possession}:${group.team}`;

    sequenceRows.push({
      sequence_id: sequenceId,
      match_id: group.matchId,
      period: group.period,
      possession_id: group.possession,
      team: group.team,
      event_count: sequence.length,
      duration_seconds: roundHalfEven(Math.max(0, endClock - startClock), 2),
      players: names.join("|") || null,
      passes: passes.length,
      completed_passes: passes.reduce((sum, event) => sum + Number(completedPass(event)), 0),
      carries: carries.length,
      receipts: receipts.length,
      pressured_events: pressured.length,
      pressured_receipts: pressuredReceipts,
      box_entries: hasDirection ? boxEntries : null,
      final_third_entries: hasDirection ? finalThirdEntries : null,
      progressive_actions: hasDirection ? progressiveActions : null,
      shot_count: shots.length,
      shot_xg_reference_only: roundHalfEven(shotXg, 6),
      mean_action_xt_gain: xtGains.length
        ? roundHalfEven(xtGains.reduce((sum, value) => sum + value, 0) / xtGains.length, 6)
        : null,
      positive_action_xt_gain_sum: xtGains.length
        ? roundHalfEven(xtGains.reduce((sum, value) => sum + Math.max(0, value), 0), 6)
        : null,
      direction_available: hasDirection,
      sequence_class: classification,
    });

    for (const event of sequence) {
      const actor = playerOf(event);
      const type = eventType(event);
      if (actor) {
        const counter = playerCounter(actor);
        increment(counter, "event_involvements");
        if (type === "Pass") {
          increment(counter, "passes");
          increment(counter, "completed_passes", Number(completedPass(event)));
        } else if (type === "Carry") {
          increment(counter, "carries");
        } else if (type === "Shot") {
          increment(counter, "shots");
          increment(counter, "shot_xg_reference_only", numberOrZero(event.shot?.statsbomb_xg));
        } else if (RECEIPT_TYPES.has(type)) {
          increment(counter, "receipts");
        }
        increment(counter, "pressured_events", Number(Boolean(event.under_pressure)));

        if (hasDirection && ACTION_TYPES.has(type)) {
          const [start, end] = actionLocations(event);
          const startOriented = orient(start, attacksRight);
          const endOriented = orient(end, attacksRight);
          if (endOriented) {
            increment(counter, "box_entries", Number(endOriented[0] >= 102 && endOriented[1] >= 18 && endOriented[1] <= 62));
            increment(counter, "final_third_entries", Number(endOriented[0] >= 80));
          }
          increment(counter, "progressive_actions", Number(Boolean(
            startOriented && endOriented && endOriented[0] - startOriented[0] >= 10,
          )));
          if (xtValues) {
            const source = gridCell(startOriented);
            const destination = gridCell(endOriented);
            if (source !== null && destination !== null) {
              increment(counter, "action_xt_gain_sum", xtValues[destination] - xtValues[source]);
              increment(counter, "action_xt_gain_n");
            }
          }
        }
        if (RECEIPT_TYPES.has(type) && event.under_pressure) increment(counter, "pressured_receipts");
      }

      if (type === "Pass") {
        const recipient = nameOf(event.pass?.recipient);
        if (recipient) {
          const counter = playerCounter(recipient);
          increment(counter, "passes_received");
          if (event.under_pressure) increment(counter, "pressured_passes_received");
        }
      }
    }

    for (const player of names) {
      const counter = playerCounter(player);
      increment(counter, "sequences_involved");
      increment(counter, "shot_linked_sequences", Number(classification === "shot_linked"));
      increment(counter, "non_shot_candidate_sequences", Number(classification === "non_shot_candidate"));
    }
  }

  return { sequenceRows, players };
}

export function canonicalSequenceRows(sequenceRows) {
  return sequenceRows.map((row) => {
    const canonical = {
      match_id: row.match_id,
      period: row.period,
      possession_id: row.possession_id,
      team: row.team,
    };
    for (const feature of SEQUENCE_FEATURES) canonical[feature] = row[feature] ?? null;
    return canonical;
  });
}

export function canonicalPlayerRows(players) {
  return [...players.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([name, counter]) => {
      const row = { statsbomb_player_name: name };
      for (const feature of PLAYER_FEATURES) {
        if (feature === "mean_action_xt_gain") {
          const count = counter.action_xt_gain_n ?? 0;
          row[feature] = count
            ? roundHalfEven(counter.action_xt_gain_sum / count, 6)
            : null;
        } else {
          row[feature] = Object.hasOwn(counter, feature) ? counter[feature] : 0;
        }
      }
      return row;
    });
}

export function xtGridRows(values) {
  if (!values) return [];
  return values.map((value, index) => ({
    x_cell: index % GRID_X,
    y_cell: Math.trunc(index / GRID_X),
    xT: roundHalfEven(value, 8),
  }));
}

export function audit360(events, frames, matchId) {
  const scopedMatchId = String(matchId);
  const eventKeys = new Set(
    events
      .filter((event) => event.id !== null && event.id !== undefined
        && String(event._match_id ?? scopedMatchId) === scopedMatchId)
      .map((event) => JSON.stringify([scopedMatchId, String(event.id)])),
  );
  const uuids = frames
    .filter((frame) => isObject(frame) && frame.event_uuid !== null && frame.event_uuid !== undefined)
    .map((frame) => String(frame.event_uuid));
  const frameKeys = uuids.map((uuid) => JSON.stringify([scopedMatchId, uuid]));
  const counts = new Map();
  for (const key of frameKeys) counts.set(key, (counts.get(key) ?? 0) + 1);
  const matched = frameKeys.reduce((sum, key) => sum + Number(eventKeys.has(key)), 0);
  const matchedEventKeys = new Set(frameKeys.filter((key) => eventKeys.has(key)));
  return {
    frames: frames.filter(isObject).length,
    frames_with_event_uuid: uuids.length,
    unique_event_uuids: new Set(uuids).size,
    unique_match_event_keys: new Set(frameKeys).size,
    duplicate_frame_event_uuids: [...counts.values()].reduce((sum, count) => sum + Math.max(0, count - 1), 0),
    matched_frame_uuids: matched,
    unmatched_frame_uuids: frameKeys.length - matched,
    frame_to_event_join_rate: frameKeys.length ? roundHalfEven(matched / frameKeys.length, 6) : null,
    event_coverage_with_frame: eventKeys.size ? roundHalfEven(matchedEventKeys.size / eventKeys.size, 6) : null,
  };
}

export function coordinateDiagnostics(frames) {
  const visible = [];
  let invalidShapeOrType = 0;
  let missingLocation = 0;
  let nonObjectEntries = 0;
  for (const frame of frames) {
    if (!isObject(frame) || !Array.isArray(frame.freeze_frame)) continue;
    for (const item of frame.freeze_frame) {
      if (!isObject(item)) {
        nonObjectEntries += 1;
        continue;
      }
      const location = item.location;
      if (location === null || location === undefined) {
        missingLocation += 1;
        continue;
      }
      const normalized = point(location);
      if (!normalized) {
        invalidShapeOrType += 1;
        continue;
      }
      visible.push(normalized);
    }
  }
  const outOfBounds = visible.filter(([x, y]) => x < 0 || x > PITCH_X || y < 0 || y > PITCH_Y);
  const coordinateRange = visible.reduce((range, [x, y]) => ({
    min_x: Math.min(range.min_x, x),
    max_x: Math.max(range.max_x, x),
    min_y: Math.min(range.min_y, y),
    max_y: Math.max(range.max_y, y),
  }), {
    min_x: Infinity,
    max_x: -Infinity,
    min_y: Infinity,
    max_y: -Infinity,
  });
  return {
    visible_player_records: visible.length + missingLocation + invalidShapeOrType + nonObjectEntries,
    missing_location: missingLocation,
    invalid_location_shape_or_type: invalidShapeOrType,
    non_object_entries: nonObjectEntries,
    numeric_locations: visible.length,
    out_of_bounds_nominal_120x80: outOfBounds.length,
    coordinate_range: visible.length ? coordinateRange : null,
    policy: "Coordinates are reported without clipping and are not used as event locations.",
  };
}

export function runCoreEquivalent(rawEvents, frames, matchId, directionOverrides = new Map()) {
  if (!Array.isArray(rawEvents) || !Array.isArray(frames)) {
    throw new TypeError("Events and 360 inputs must each be JSON arrays");
  }
  const events = rawEvents
    .filter(isObject)
    .map((event, index) => ({ ...event, _match_id: String(matchId), _event_index: index }));
  const neededDirectionKeys = new Set(events.map(directionKeyForEvent));
  const directions = completeStatsBombDirections(events, directionOverrides);
  const explicitKeys = [...neededDirectionKeys].filter((key) => directionOverrides.has(key)).length;
  const generatedKeys = [...neededDirectionKeys].filter((key) => !directionOverrides.has(key)).length;
  const { values, audit: xtAudit } = fitXt(events, directions);
  const { sequenceRows, players } = buildFeatures(events, directions, values);
  return {
    matchId: String(matchId),
    eventsProcessed: events.length,
    sequenceRows: canonicalSequenceRows(sequenceRows),
    playerRows: canonicalPlayerRows(players),
    xtGridRows: xtGridRows(values),
    xtAudit,
    directionAudit: {
      explicit_direction_keys: explicitKeys,
      generated_direction_keys: generatedKeys,
      direction_keys_total: directions.size,
      convention: "StatsBomb possession-oriented coordinates; attacks_right=true when no override exists.",
    },
    statsbomb360Audit: audit360(events, frames, matchId),
    coordinateDiagnostics: coordinateDiagnostics(frames),
  };
}
