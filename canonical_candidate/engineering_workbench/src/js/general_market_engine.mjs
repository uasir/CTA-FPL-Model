import {
  validateGeneralMarketRequest,
  RecommendationContractError,
} from "./recommendation_contracts.mjs";

const POSITIONS = ["GKP", "DEF", "MID", "FWD"];

function numberFilter(filters, field) {
  const value = filters[field];
  if (value === undefined || value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new RecommendationContractError(`filters.${field} must be a finite number`);
  }
  return value;
}

function validateFilters(filters) {
  if (filters === null || typeof filters !== "object" || Array.isArray(filters)) {
    throw new RecommendationContractError("filters must be an object");
  }
  const position = filters.position ?? null;
  if (position !== null && !POSITIONS.includes(position)) {
    throw new RecommendationContractError("filters.position is invalid");
  }
  const teamId = filters.team_id ?? null;
  if (teamId !== null && (!Number.isInteger(teamId) || teamId < 1)) {
    throw new RecommendationContractError("filters.team_id must be a positive integer");
  }
  const limit = filters.limit ?? 10;
  if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
    throw new RecommendationContractError("filters.limit must be an integer from 1 to 50");
  }
  const minPrice = numberFilter(filters, "min_price");
  const maxPrice = numberFilter(filters, "max_price");
  const minPoints = numberFilter(filters, "min_expected_points");
  const eoThreshold = numberFilter(filters, "differential_eo_max_pct");
  if (minPrice !== null && minPrice <= 0) {
    throw new RecommendationContractError("filters.min_price must be positive");
  }
  if (maxPrice !== null && maxPrice <= 0) {
    throw new RecommendationContractError("filters.max_price must be positive");
  }
  if (minPrice !== null && maxPrice !== null && minPrice > maxPrice) {
    throw new RecommendationContractError("filters.min_price cannot exceed max_price");
  }
  if (eoThreshold !== null && eoThreshold < 0) {
    throw new RecommendationContractError("filters.differential_eo_max_pct cannot be negative");
  }
  return { position, teamId, limit, minPrice, maxPrice, minPoints, eoThreshold };
}

function compareOverall(a, b) {
  return b.expected_points - a.expected_points
    || b.expected_minutes - a.expected_minutes
    || a.fpl_element_id - b.fpl_element_id;
}

function compareValue(a, b) {
  return b.value_score - a.value_score
    || b.expected_points - a.expected_points
    || a.fpl_element_id - b.fpl_element_id;
}

export function recommendGeneralMarket(payload) {
  const request = validateGeneralMarketRequest(payload);
  const { position, teamId, limit, minPrice, maxPrice, minPoints, eoThreshold } =
    validateFilters(request.filters ?? {});
  const players = request.player_forecasts;
  const filtered = players
    .filter((player) => (position === null || player.position === position)
      && (teamId === null || player.team_id === teamId)
      && (minPrice === null || player.price >= minPrice)
      && (maxPrice === null || player.price <= maxPrice)
      && (minPoints === null || player.expected_points >= minPoints))
    .map((player) => ({
      ...player,
      value_score: player.expected_points / player.price,
    }));

  const overallSorted = [...filtered].sort(compareOverall);
  const valueSorted = [...filtered].sort(compareValue);
  const eoPlayers = filtered.filter((player) =>
    Object.hasOwn(player, "effective_ownership_pct"));
  let differentials;
  if (eoThreshold === null) {
    differentials = { status: "EO_THRESHOLD_NOT_SET", players: [], threshold_pct: null };
  } else if (!eoPlayers.length) {
    differentials = { status: "EO_UNAVAILABLE", players: [], threshold_pct: eoThreshold };
  } else {
    differentials = {
      status: "SAMPLED_EO_AVAILABLE",
      players: eoPlayers
        .filter((player) => player.effective_ownership_pct <= eoThreshold)
        .sort(compareOverall)
        .slice(0, limit),
      threshold_pct: eoThreshold,
    };
  }

  const quality = request.forecast_quality;
  const byPosition = Object.fromEntries(POSITIONS.map((key) => [
    key,
    filtered.filter((player) => player.position === key)
      .sort(compareOverall)
      .slice(0, limit),
  ]));

  return {
    system: "general_market",
    forecast_snapshot_id: request.forecast_snapshot_id,
    model_version: request.model_version,
    forecast_horizon_gameweeks: request.forecast_horizon_gameweeks,
    forecast_quality: quality,
    recommendation_status: quality.validation_status !== "VALIDATED"
      ? "EXPLORATORY_ONLY" : "VALIDATED",
    ranking_basis: "expected_points (EV), expected_points / price (value), and sampled EO only when explicitly supplied",
    covar_used: false,
    coverage: {
      input_players: players.length,
      filtered_players: filtered.length,
      players_with_eo: eoPlayers.length,
      point_in_time_status: quality.point_in_time_status,
    },
    categories: {
      overall: overallSorted.slice(0, limit),
      by_position: byPosition,
      value: valueSorted.slice(0, limit),
      captaincy: overallSorted.slice(0, Math.min(5, limit)),
      differentials,
    },
    limitations: [
      "This is a deterministic ranking layer, not a trained CTA points model.",
      "The engine does not use personal squad, bank, transfers, chips, formation or manager rank.",
      "CoVar is deliberately excluded until covariance is stable and validated out of sample.",
      "EO rankings are unavailable unless a locked, cohort-labelled EO field is supplied.",
    ],
  };
}
