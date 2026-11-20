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

function ctaEvidenceSummary(cta) {
  const fixtures = Array.isArray(cta.fixtures) ? cta.fixtures : [];
  const available = fixtures.filter((row) =>
    row && typeof row === "object" && row.snapshot_available_as_of_deadline === true);
  const sourceRow = available[0] ?? fixtures.find((row) => row && typeof row === "object") ?? {};
  const identityVerified = cta.identity_verified === true;
  const priorCount = Number(sourceRow.prior_matches_count ?? 0) || 0;
  const prior3Count = Number(sourceRow.prior3_matches_count ?? 0) || 0;
  const features = sourceRow.features && typeof sourceRow.features === "object"
    ? sourceRow.features : {};
  const featureMap = {
    shots_per_match: "cta_prior3_matches_shots_avg",
    shots_on_target_per_match: "cta_prior3_matches_shots_on_target_avg",
    key_passes_per_match: "cta_prior3_matches_key_passes_avg",
    box_attempts_per_match: "cta_prior3_matches_attempts_inside_box_avg",
    tracked_xg_per_match: "cta_prior3_matches_tracked_xg_sum_avg",
    big_chances_per_match: "cta_prior3_matches_big_chances_avg",
  };
  const values = {};
  for (const [label, key] of Object.entries(featureMap)) {
    const value = features[key];
    if (value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value))) {
      values[label] = Number(value);
    }
  }
  let status = "RESEARCH_ONLY_EVIDENCE_AVAILABLE";
  if (!identityVerified) status = "UNVERIFIED_IDENTITY";
  else if (priorCount <= 0) status = "VERIFIED_IDENTITY_NO_PRIOR_HISTORY";
  else if (Object.keys(values).length === 0) status = "VERIFIED_IDENTITY_NO_FEATURE_VALUES";
  return {
    status,
    source_snapshot_as_of: cta.source_snapshot_as_of ?? null,
    target_gameweek: cta.target_gameweek ?? null,
    prior_matches_count: priorCount,
    prior3_matches_count: prior3Count,
    feature_window: "prior 3 matches",
    feature_averages: values,
    decision_use_status: "RESEARCH_ONLY_NOT_IN_BASELINE",
    decision_weight: 0,
    ranking_effect: "NONE",
  };
}

function playerCtaContext(player) {
  const cta = player.cta && typeof player.cta === "object" && !Array.isArray(player.cta)
    ? player.cta
    : {
      identity_verified: false,
      identity_status: "NO_CTA_SIDECAR",
      coverage_status: "NO_CTA_SIDECAR",
      composite: null,
      decision_use_status: "UNAVAILABLE",
      fixtures: [],
    };
  return {
    fpl_element_id: player.fpl_element_id,
    web_name: player.web_name ?? "",
    cta,
    cta_evidence_summary: ctaEvidenceSummary(cta),
  };
}

function sellingPrice(currentPrice, purchasePrice) {
  const currentTenths = Math.round(currentPrice * 10);
  const purchaseTenths = Math.round(purchasePrice * 10);
  if (currentTenths <= purchaseTenths) return currentTenths / 10;
  return (purchaseTenths + Math.floor((currentTenths - purchaseTenths) / 2)) / 10;
}

function transferCandidates(request, forecasts, starting, formation, captain) {
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
  const currentStartingIds = new Set(starting.map((player) => player.fpl_element_id));
  const currentStartingPoints = starting.reduce((sum, player) => sum + player.expected_points, 0);
  const currentDecisionPoints = currentStartingPoints + captain.expected_points;
  const currentBench = [...ownedIds]
    .filter((id) => !currentStartingIds.has(id) && forecastById.get(id).position !== "GKP")
    .map((id) => forecastById.get(id));
  const currentBenchDepth = [...currentBench].sort(playerOrder).slice(0, 2)
    .reduce((sum, player) => sum + player.expected_points, 0);
  const formationValue = formation.join("-");
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

      const candidateIds = [...ownedIds].filter((id) => id !== outId).concat(inId).sort((a, b) => a - b);
      const candidateOwned = candidateIds.map((id) => forecastById.get(id));
      const candidateStarting = bestStartingXI(candidateOwned, forecastById, formationValue, null).starting;
      const candidateStartingIds = new Set(candidateStarting.map((player) => player.fpl_element_id));
      const candidateStartingPoints = candidateStarting.reduce((sum, player) => sum + player.expected_points, 0);
      const candidateCaptain = [...candidateStarting].sort(playerOrder)[0];
      const candidateDecisionPoints = candidateStartingPoints + candidateCaptain.expected_points;
      const candidateBench = candidateOwned.filter((player) =>
        !candidateStartingIds.has(player.fpl_element_id) && player.position !== "GKP");
      const candidateBenchDepth = [...candidateBench].sort(playerOrder).slice(0, 2)
        .reduce((sum, player) => sum + player.expected_points, 0);

      const playerDelta = incoming.expected_points - outForecast.expected_points;
      const startingDelta = candidateStartingPoints - currentStartingPoints;
      const captaincyDelta = candidateCaptain.expected_points - captain.expected_points;
      const decisionDelta = candidateDecisionPoints - currentDecisionPoints;
      const benchDelta = candidateBenchDepth - currentBenchDepth;
      const net = decisionDelta - appliedHitCost;
      candidates.push({
        transfer_out_id: outId,
        transfer_in_id: inId,
        expected_points_delta: Number(decisionDelta.toFixed(8)),
        player_expected_points_delta: Number(playerDelta.toFixed(8)),
        starting_xi_expected_points_delta: Number(startingDelta.toFixed(8)),
        captaincy_expected_points_delta: Number(captaincyDelta.toFixed(8)),
        bench_depth_expected_points_delta: Number(benchDelta.toFixed(8)),
        current_decision_expected_points: Number(currentDecisionPoints.toFixed(8)),
        candidate_decision_expected_points: Number(candidateDecisionPoints.toFixed(8)),
        starting_xi_after_transfer_ids: candidateStarting.map((player) => player.fpl_element_id),
        captain_after_transfer_id: candidateCaptain.fpl_element_id,
        hit_cost_points: appliedHitCost,
        net_expected_points_gain: Number(net.toFixed(8)),
        selling_price: Number(sellPrice.toFixed(2)),
        incoming_price: Number(incoming.price.toFixed(2)),
        bank_after_transfer: Number((available - incoming.price).toFixed(2)),
      });
    }
  }
  candidates.sort((a, b) =>
    b.net_expected_points_gain - a.net_expected_points_gain
    || b.starting_xi_expected_points_delta - a.starting_xi_expected_points_delta
    || b.bench_depth_expected_points_delta - a.bench_depth_expected_points_delta
    || b.player_expected_points_delta - a.player_expected_points_delta
    || a.transfer_out_id - b.transfer_out_id
    || a.transfer_in_id - b.transfer_in_id);
  const alternatives = candidates.slice(0, maxAlternatives);
  const hasCtaSidecar = forecasts.some((player) =>
    player.cta && typeof player.cta === "object" && !Array.isArray(player.cta));
  if (hasCtaSidecar) {
    for (const candidate of alternatives) {
      candidate.cta_context = {
        outgoing: playerCtaContext(forecastById.get(candidate.transfer_out_id)),
        incoming: playerCtaContext(forecastById.get(candidate.transfer_in_id)),
      };
    }
  }
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
    scope: "one-transfer lookahead ranked by marginal starting-XI plus captaincy EV; bench-depth change reported separately",
  };
}

function squadSupportMetrics(owned, starting, benchOrder, forecastById, captain) {
  const benchPlayers = benchOrder.map((id) => forecastById.get(id));
  const topTwo = [...benchPlayers].sort(playerOrder).slice(0, 2);
  const eoOwned = owned.filter((player) => typeof player.effective_ownership_pct === "number"
    && Number.isFinite(player.effective_ownership_pct)).map((player) => player.effective_ownership_pct);
  const eoStarting = starting.filter((player) => typeof player.effective_ownership_pct === "number"
    && Number.isFinite(player.effective_ownership_pct)).map((player) => player.effective_ownership_pct);
  return {
    bench_depth: {
      outfield_bench_count: benchPlayers.length,
      top_two_outfield_bench_ids: topTwo.map((player) => player.fpl_element_id),
      top_two_outfield_bench_expected_points: Number(topTwo.reduce((sum, player) => sum + player.expected_points, 0).toFixed(6)),
      top_two_outfield_bench_mean_expected_minutes: topTwo.length
        ? Number((topTwo.reduce((sum, player) => sum + player.expected_minutes, 0) / topTwo.length).toFixed(6)) : null,
      policy: "DESCRIPTIVE_ONLY_FIXED_STARTING_XI_NO_ROUTINE_ROTATION",
      note: "Bench depth is reported separately; it does not displace a higher-EV starting player or trigger routine rotation.",
    },
    effective_ownership_context: {
      owned_players_with_eo: eoOwned.length,
      owned_player_eo_coverage: eoOwned.length / owned.length,
      starting_xi_players_with_eo: eoStarting.length,
      starting_xi_eo_coverage: eoStarting.length / starting.length,
      mean_owned_eo_pct: eoOwned.length ? eoOwned.reduce((sum, value) => sum + value, 0) / eoOwned.length : null,
      mean_starting_xi_eo_pct: eoStarting.length ? eoStarting.reduce((sum, value) => sum + value, 0) / eoStarting.length : null,
      captain_eo_pct: captain.effective_ownership_pct ?? null,
      decision_role: "FIELD_REFERENCE_ONLY_NOT_A_CTA_PREREQUISITE",
      missing_eo_policy: "PRESERVE_MISSING_AND_REPORT_COVERAGE",
    },
  };
}

function decisionAudit(request, transfer, starting, formation, captain, vice) {
  const options = [{ option_id: "HOLD", action: "HOLD", predicted_net_expected_points_gain: 0, feasible: true }];
  for (const candidate of transfer.alternatives) {
    options.push({
      option_id: `TRANSFER:${candidate.transfer_out_id}:${candidate.transfer_in_id}`,
      action: "TRANSFER",
      transfer_out_id: candidate.transfer_out_id,
      transfer_in_id: candidate.transfer_in_id,
      predicted_net_expected_points_gain: candidate.net_expected_points_gain,
      feasible: true,
    });
  }
  const chosen = transfer.action === "TRANSFER" && transfer.best_candidate
    ? `TRANSFER:${transfer.best_candidate.transfer_out_id}:${transfer.best_candidate.transfer_in_id}` : "HOLD";
  return {
    decision_record_status: "AUDIT_PAYLOAD_READY_AWAITING_DEADLINE_LOCK_AND_ARCHIVAL",
    forecast_snapshot_id: request.forecast_snapshot_id,
    model_version: request.model_version,
    target_horizon_gameweeks: request.forecast_horizon_gameweeks,
    target_deadline: request.forecast_quality.data_coverage.target_deadline ?? null,
    squad_snapshot: request.squad_snapshot.map((row) => ({ fpl_element_id: row.fpl_element_id, purchase_price: row.purchase_price })),
    bank: request.bank,
    free_transfers: request.free_transfers,
    transfer_decision: {
      chosen_option_id: chosen,
      options,
      candidate_universe_count: transfer.candidate_count,
      recorded_alternative_scope: "HOLD plus top-ranked feasible transfers returned by the optimiser; regret against this shortlist must not be described as global feasible-set regret.",
      realised_utility: null,
      scoring_status: "AWAITING_OFFICIAL_GAMEWEEK_OUTCOMES",
    },
    starting_xi_decision: {
      chosen_player_ids: starting.map((player) => player.fpl_element_id),
      formation: formation.join("-"),
      realised_utility: null,
      scoring_status: "AWAITING_OFFICIAL_GAMEWEEK_OUTCOMES",
    },
    captaincy_decision: {
      chosen_option_id: String(captain.fpl_element_id),
      vice_captain_option_id: String(vice.fpl_element_id),
      options: starting.map((player) => ({ option_id: String(player.fpl_element_id), predicted_points: player.expected_points, feasible: true })),
      realised_utility: null,
      scoring_status: "AWAITING_OFFICIAL_GAMEWEEK_OUTCOMES",
    },
  };
}

export function recommendPersonalSquad(payload) {
  const request = validatePersonalSquadRequest(payload);
  const forecasts = request.player_forecasts;
  const forecastById = new Map(forecasts.map((player) => [player.fpl_element_id, player]));
  const squad = request.squad_snapshot;
  const ownedIds = new Set(squad.map((player) => player.fpl_element_id));
  const owned = [...ownedIds].map((id) => forecastById.get(id));
  const hasCtaSidecar = forecasts.some((player) =>
    player.cta && typeof player.cta === "object" && !Array.isArray(player.cta));
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
  const transfer = transferCandidates(request, forecasts, starting, formation, captain);
  const supportMetrics = squadSupportMetrics(owned, starting, benchOrder, forecastById, captain);
  const audit = decisionAudit(request, transfer, starting, formation, captain, vice);
  const quality = request.forecast_quality;
  return {
    system: "personal_squad",
    forecast_snapshot_id: request.forecast_snapshot_id,
    model_version: request.model_version,
    forecast_horizon_gameweeks: request.forecast_horizon_gameweeks,
    forecast_quality: quality,
    recommendation_status: quality.validation_status === "VALIDATED"
      && quality.point_in_time_status === "VERIFIED"
      && quality.data_coverage.freshness_status === "FRESH_WITHIN_24H"
      ? "VALIDATED" : "EXPLORATORY_ONLY",
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
      ...supportMetrics,
      ...(hasCtaSidecar ? {
        owned_squad_cta_context: squad.map((row) => playerCtaContext(forecastById.get(row.fpl_element_id))),
        starting_xi_cta_context: starting.map(playerCtaContext),
        bench_cta_context: benchOrder.map((playerId) => playerCtaContext(forecastById.get(playerId))),
        reserve_goalkeeper_cta_context: playerCtaContext(reserveGk[0]),
        cta_context_status: "RESEARCH_ONLY_NOT_IN_BASELINE",
      } : {}),
    },
    decision_audit: audit,
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
