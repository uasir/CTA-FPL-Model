import {
  validatePersonalSquadRequest,
  RecommendationContractError,
} from "./recommendation_contracts.mjs";

const POSITIONS = ["GKP", "DEF", "MID", "FWD"];

function playerOrder(a, b) {
  return b.expected_points - a.expected_points
    || b.expected_minutes - a.expected_minutes
    || a.fpl_element_id - b.fpl_element_id;
}

function minutesOrder(a, b) {
  return b.expected_minutes - a.expected_minutes
    || b.expected_points - a.expected_points
    || a.fpl_element_id - b.fpl_element_id;
}

function formationCounts(value) {
  if (typeof value !== "string") {
    throw new RecommendationContractError("formation must be a string such as 4-3-3");
  }
  const parts = value.split("-");
  if (parts.length !== 3 || parts.some((part) => !/^\d+$/.test(part))) {
    throw new RecommendationContractError("formation must be DEF-MID-FWD, such as 4-3-3");
  }
  const counts = parts.map(Number);
  const [defenders, midfielders, forwards] = counts;
  if (!(defenders >= 3 && defenders <= 5
    && midfielders >= 2 && midfielders <= 5
    && forwards >= 1 && forwards <= 3
    && defenders + midfielders + forwards === 10)) {
    throw new RecommendationContractError("formation must be a legal FPL outfield formation");
  }
  return counts;
}

function selectForFormation(owned, byId, formation) {
  const [defenders, midfielders, forwards] = formation;
  const counts = { GKP: 1, DEF: defenders, MID: midfielders, FWD: forwards };
  const selected = [];
  for (const position of POSITIONS) {
    const candidates = owned
      .map((player) => byId.get(player.fpl_element_id))
      .filter((player) => player.position === position)
      .sort(playerOrder);
    if (candidates.length < counts[position]) {
      throw new RecommendationContractError("Not enough players for requested formation: " + position);
    }
    selected.push(...candidates.slice(0, counts[position]));
  }
  return selected;
}

function bestStartingXi(owned, byId, formationValue, startingXiValue) {
  const requested = formationValue !== null && formationValue !== undefined
    ? formationCounts(formationValue) : null;
  let formation;
  let selected;
  if (startingXiValue !== null && startingXiValue !== undefined) {
    if (!Array.isArray(startingXiValue) || startingXiValue.length !== 11
      || startingXiValue.some((id) => !Number.isInteger(id) || id < 1)) {
      throw new RecommendationContractError("starting_xi must contain exactly 11 FPL element IDs");
    }
    if (new Set(startingXiValue).size !== 11
      || startingXiValue.some((id) => !owned.some((player) => player.fpl_element_id === id))) {
      throw new RecommendationContractError("starting_xi must contain 11 unique players from the current squad");
    }
    selected = startingXiValue.map((id) => byId.get(id));
    formation = ["DEF", "MID", "FWD"].map((position) =>
      selected.filter((player) => player.position === position).length);
    formationCounts(formation.join("-"));
    if (requested !== null && formation.some((count, index) => count !== requested[index])) {
      throw new RecommendationContractError("starting_xi does not match requested formation");
    }
  } else if (requested !== null) {
    formation = requested;
    selected = selectForFormation(owned, byId, formation);
  } else {
    let best = null;
    for (let defenders = 3; defenders <= 5; defenders += 1) {
      for (let midfielders = 2; midfielders <= 5; midfielders += 1) {
        const forwards = 10 - defenders - midfielders;
        if (forwards < 1 || forwards > 3) continue;
        const candidate = [defenders, midfielders, forwards];
        const xi = selectForFormation(owned, byId, candidate);
        const score = xi.reduce((sum, player) => sum + player.expected_points, 0);
        if (best === null || score > best.score + 1e-12) {
          best = { score, formation: candidate, xi };
        }
      }
    }
    if (best === null) {
      throw new RecommendationContractError("No legal starting XI could be constructed");
    }
    formation = best.formation;
    selected = best.xi;
  }
  const ordered = [];
  for (const position of POSITIONS) {
    ordered.push(...selected.filter((player) => player.position === position).sort(playerOrder));
  }
  return { starting: ordered, formation };
}

function sellingPrice(currentPrice, purchasePrice) {
  const currentTenths = Math.round(currentPrice * 10);
  const purchaseTenths = Math.round(purchasePrice * 10);
  if (currentTenths <= purchaseTenths) return currentTenths / 10;
  return (purchaseTenths + Math.floor((currentTenths - purchaseTenths) / 2)) / 10;
}

function transferCandidates(request, forecasts) {
  const squad = request.squad_snapshot;
  const ownedIds = new Set(squad.map((player) => player.fpl_element_id));
  const forecastById = new Map(forecasts.map((player) => [player.fpl_element_id, player]));
  const teamCounts = new Map();
  for (const playerId of ownedIds) {
    const teamId = forecastById.get(playerId).team_id;
    teamCounts.set(teamId, (teamCounts.get(teamId) ?? 0) + 1);
  }
  const preferences = request.personal_preferences ?? {};
  if (preferences === null || typeof preferences !== "object" || Array.isArray(preferences)) {
    throw new RecommendationContractError("personal_preferences must be an object");
  }
  const hitCost = Object.hasOwn(preferences, "hit_cost_points") ? preferences.hit_cost_points : 4;
  const minGain = Object.hasOwn(preferences, "min_transfer_gain_points") ? preferences.min_transfer_gain_points : 0;
  const maxAlternatives = Object.hasOwn(preferences, "max_transfer_alternatives") ? preferences.max_transfer_alternatives : 5;
  for (const [name, value] of [["hit_cost_points", hitCost], ["min_transfer_gain_points", minGain]]) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
      throw new RecommendationContractError("personal_preferences." + name + " must be a non-negative finite number");
    }
  }
  if (!Number.isInteger(maxAlternatives) || maxAlternatives < 1 || maxAlternatives > 20) {
    throw new RecommendationContractError("personal_preferences.max_transfer_alternatives must be an integer from 1 to 20");
  }
  const appliedHitCost = request.free_transfers > 0 ? 0 : hitCost;
  const candidates = [];
  for (const outgoing of squad) {
    const outId = outgoing.fpl_element_id;
    const outForecast = forecastById.get(outId);
    const sellPrice = sellingPrice(outForecast.price, outgoing.purchase_price);
    const teamAfter = new Map(teamCounts);
    teamAfter.set(outForecast.team_id, (teamAfter.get(outForecast.team_id) ?? 0) - 1);
    const available = request.bank + sellPrice;
    for (const incoming of forecasts) {
      const inId = incoming.fpl_element_id;
      if (ownedIds.has(inId) || incoming.position !== outForecast.position) continue;
      if ((teamAfter.get(incoming.team_id) ?? 0) >= 3) continue;
      if (incoming.price > available + 1e-9) continue;
        const delta = incoming.expected_points - outForecast.expected_points;
      const net = delta - appliedHitCost;
      candidates.push({
        transfer_out_id: outId,
        transfer_in_id: inId,
        expected_points_delta: delta,
        hit_cost_points: appliedHitCost,
        net_expected_points_gain: net,
        selling_price: Number(sellPrice.toFixed(2)),
        incoming_price: Number(incoming.price.toFixed(2)),
        bank_after_transfer: Number((available - incoming.price).toFixed(2)),
      });
    }
  }
  candidates.sort((a, b) =>
    b.net_expected_points_gain - a.net_expected_points_gain
    || b.expected_points_delta - a.expected_points_delta
    || a.transfer_out_id - b.transfer_out_id
    || a.transfer_in_id - b.transfer_in_id);
  const alternatives = candidates.slice(0, maxAlternatives);
  const bestCandidate = alternatives[0] ?? null;
  return {
    action: bestCandidate && bestCandidate.net_expected_points_gain > minGain
      ? "TRANSFER" : "HOLD",
    best_candidate: bestCandidate,
    alternatives,
    hit_cost_points_applied: Number(appliedHitCost.toFixed(8)),
    minimum_gain_threshold: minGain,
    free_transfers_available: request.free_transfers,
    candidate_count: candidates.length,
    scope: "one-transfer lookahead only",
  };
}

export function recommendPersonalSquad(payload) {
  const request = validatePersonalSquadRequest(payload);
  const forecasts = request.player_forecasts;
  const forecastById = new Map(forecasts.map((player) => [player.fpl_element_id, player]));
  const squad = request.squad_snapshot;
  const ownedIds = new Set(squad.map((player) => player.fpl_element_id));
  const owned = [...ownedIds].map((id) => forecastById.get(id));
  const preferences = request.personal_preferences ?? {};
  if (preferences === null || typeof preferences !== "object" || Array.isArray(preferences)) {
    throw new RecommendationContractError("personal_preferences must be an object");
  }
  const formationValue = request.formation ?? preferences.formation ?? null;
  const startingValue = request.starting_xi ?? preferences.starting_xi ?? null;
  const benchValue = request.bench_order ?? preferences.bench_order ?? null;
  const { starting, formation } = bestStartingXi(owned, forecastById, formationValue, startingValue);
  const startingIds = new Set(starting.map((player) => player.fpl_element_id));
  const remaining = owned.filter((player) => !startingIds.has(player.fpl_element_id));
  const reserveGk = remaining.filter((player) => player.position === "GKP");
  const outfieldBench = remaining.filter((player) => player.position !== "GKP");
  if (reserveGk.length !== 1 || outfieldBench.length !== 3) {
    throw new RecommendationContractError("Squad must leave one reserve goalkeeper and three outfield bench players");
  }
  let benchOrder;
  if (benchValue !== null) {
    if (!Array.isArray(benchValue) || benchValue.length !== 3
      || benchValue.some((id) => !Number.isInteger(id) || id < 1)) {
      throw new RecommendationContractError("bench_order must contain exactly three positive integer outfield player IDs");
    }
    const available = new Set(outfieldBench.map((player) => player.fpl_element_id));
    if (new Set(benchValue).size !== 3 || benchValue.some((id) => !available.has(id))) {
      throw new RecommendationContractError("bench_order must contain all three outfield substitutes exactly once");
    }
    benchOrder = benchValue;
  } else {
    benchOrder = [...outfieldBench].sort(minutesOrder).map((player) => player.fpl_element_id);
  }
  const captaincy = [...starting].sort(playerOrder);
  const captain = captaincy[0];
  const vice = captaincy[1];
  const expectedPoints = starting.reduce((sum, player) => sum + player.expected_points, 0)
    + captain.expected_points;
  const transfer = transferCandidates(request, forecasts);
  const quality = request.forecast_quality;
  return {
    system: "personal_squad",
    forecast_snapshot_id: request.forecast_snapshot_id,
    model_version: request.model_version,
    forecast_horizon_gameweeks: request.forecast_horizon_gameweeks,
    forecast_quality: quality,
    recommendation_status: quality.validation_status !== "VALIDATED"
      || quality.point_in_time_status !== "VERIFIED" ? "EXPLORATORY_ONLY" : "VALIDATED",
    manager_context: {
      bank: request.bank,
      free_transfers: request.free_transfers,
      personal_risk_profile: request.personal_risk_profile,
      manager_rank: request.manager_rank ?? null,
      rank_target: request.rank_target ?? null,
    },
    transfer_recommendation: transfer,
    squad_plan: {
      formation: formation.join("-"),
      starting_xi: starting.map((player) => player.fpl_element_id),
      captain: captain.fpl_element_id,
      vice_captain: vice.fpl_element_id,
      reserve_goalkeeper: reserveGk[0].fpl_element_id,
      bench_order: benchOrder,
      expected_starting_points: expectedPoints,
    },
    portfolio_risk: {
      covar_used: false,
      risk_profile_applied: false,
      status: "NOT_VALIDATED",
      note: "No CoVar or unvalidated variance estimate affects this decision.",
    },
    limitations: [
      "This is an exploratory one-gameweek squad optimiser, not a validated multiweek planner.",
      "CoVar and player variance are excluded because the available covariance estimate is not validated.",
      "The supplied risk profile is recorded but not applied until calibrated player-level variance is available.",
      "Only one transfer is evaluated; multi-transfer sequences, future price changes and transfer flexibility are not modelled.",
      "Chip effects are not simulated in this version.",
      "The starting XI is selected by expected points under the requested legal formation; bench order is a minutes/points proxy.",
    ],
  };
}
