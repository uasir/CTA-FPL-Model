export const RECOMMENDATION_CONTRACT_VERSION = "1.0.0";

const GENERAL_FORBIDDEN_FIELDS = new Set([
  "squad", "squad_snapshot", "bank", "free_transfers", "chips",
  "formation", "starting_xi", "bench_order", "manager_rank",
  "rank_target", "personal_risk_profile", "personal_preferences",
  "manager_id", "manager_entry_id", "team_id_for_manager",
]);

const SHARED_REQUIRED_FIELDS = [
  "forecast_snapshot_id",
  "model_version",
  "forecast_horizon_gameweeks",
  "forecast_quality",
  "player_forecasts",
];

export class RecommendationContractError extends Error {
  constructor(message) {
    super(message);
    this.name = "RecommendationContractError";
  }
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function nestedForbiddenFields(value, path = "") {
  const found = [];
  if (Array.isArray(value)) {
    value.forEach((child, index) => {
      found.push(...nestedForbiddenFields(child, `${path}[${index}]`));
    });
  } else if (isRecord(value)) {
    for (const [key, child] of Object.entries(value)) {
      const childPath = path ? `${path}.${key}` : key;
      if (GENERAL_FORBIDDEN_FIELDS.has(key)) found.push(childPath);
      found.push(...nestedForbiddenFields(child, childPath));
    }
  }
  return found;
}

function validateShared(payload) {
  if (!isRecord(payload)) {
    throw new RecommendationContractError("request must be an object");
  }
  const missing = SHARED_REQUIRED_FIELDS.filter(
    (field) => !Object.hasOwn(payload, field),
  );
  if (missing.length) {
    throw new RecommendationContractError(
      `Missing shared forecast fields: ${missing.join(", ")}`,
    );
  }
  for (const field of ["forecast_snapshot_id", "model_version"]) {
    if (typeof payload[field] !== "string" || !payload[field].trim()) {
      throw new RecommendationContractError(
        `${field} must be a non-empty string`,
      );
    }
  }
  const horizon = payload.forecast_horizon_gameweeks;
  if (!Number.isInteger(horizon) || horizon < 1) {
    throw new RecommendationContractError(
      "forecast_horizon_gameweeks must be a positive integer",
    );
  }
  const quality = payload.forecast_quality;
  if (!isRecord(quality)) {
    throw new RecommendationContractError("forecast_quality must be an object");
  }
  if (!["EXPLORATORY_ONLY", "VALIDATED", "UNAVAILABLE"].includes(quality.validation_status)) {
    throw new RecommendationContractError("forecast_quality.validation_status is invalid");
  }
  if (!["VERIFIED", "NOT_VERIFIED", "NOT_APPLICABLE"].includes(quality.point_in_time_status)) {
    throw new RecommendationContractError("forecast_quality.point_in_time_status is invalid");
  }
  if (!isRecord(quality.data_coverage)) {
    throw new RecommendationContractError("forecast_quality.data_coverage must be an object");
  }
  if (!Array.isArray(quality.limitations)) {
    throw new RecommendationContractError("forecast_quality.limitations must be a list");
  }
  if (!Array.isArray(payload.player_forecasts) || payload.player_forecasts.length === 0) {
    throw new RecommendationContractError("player_forecasts must be a non-empty list");
  }
  const seen = new Set();
  payload.player_forecasts.forEach((player, index) => {
    if (!isRecord(player)) {
      throw new RecommendationContractError(
        `player_forecasts[${index}] must be an object`,
      );
    }
    const id = player.fpl_element_id;
    if (id === null || id === undefined || String(id).trim() === "") {
      throw new RecommendationContractError(
        `player_forecasts[${index}] is missing fpl_element_id`,
      );
    }
    if (!Number.isInteger(id) || id < 1) {
      throw new RecommendationContractError(
        `player_forecasts[${index}].fpl_element_id must be a positive integer`,
      );
    }
    const key = String(id);
    if (seen.has(key)) {
      throw new RecommendationContractError(
        `Duplicate forecast for FPL element ID ${key}`,
      );
    }
    seen.add(key);
    for (const field of ["expected_points", "expected_minutes", "price"]) {
      if (typeof player[field] !== "number" || !Number.isFinite(player[field])) {
        throw new RecommendationContractError(
          `player_forecasts[${index}].${field} must be a finite number`,
        );
      }
    }
    if (player.expected_minutes < 0) {
      throw new RecommendationContractError(
        `player_forecasts[${index}].expected_minutes cannot be negative`,
      );
    }
    if (player.price <= 0) {
      throw new RecommendationContractError(
        `player_forecasts[${index}].price must be positive`,
      );
    }
    if (!Number.isInteger(player.team_id) || player.team_id < 1) {
      throw new RecommendationContractError(
        `player_forecasts[${index}].team_id must be a positive integer`,
      );
    }
    if (!["GKP", "DEF", "MID", "FWD"].includes(player.position)) {
      throw new RecommendationContractError(
        `player_forecasts[${index}].position is invalid`,
      );
    }
    if (Object.hasOwn(player, "effective_ownership_pct")
        && (typeof player.effective_ownership_pct !== "number"
          || !Number.isFinite(player.effective_ownership_pct)
          || player.effective_ownership_pct < 0)) {
      throw new RecommendationContractError(
        `player_forecasts[${index}].effective_ownership_pct must be non-negative`,
      );
    }
    if (Object.hasOwn(player, "points_variance")
        && (typeof player.points_variance !== "number"
          || !Number.isFinite(player.points_variance)
          || player.points_variance < 0)) {
      throw new RecommendationContractError(
        `player_forecasts[${index}].points_variance must be non-negative`,
      );
    }
    if (Object.hasOwn(player, "availability_probability")
        && (typeof player.availability_probability !== "number"
          || !Number.isFinite(player.availability_probability)
          || player.availability_probability < 0
          || player.availability_probability > 1)) {
      throw new RecommendationContractError(
        `player_forecasts[${index}].availability_probability must be between 0 and 1`,
      );
    }
  });
}

export function validateGeneralMarketRequest(payload) {
  validateShared(payload);
  const forbidden = nestedForbiddenFields(payload).sort();
  if (forbidden.length) {
    throw new RecommendationContractError(
      `general_market must not receive personal fields: ${forbidden.join(", ")}`,
    );
  }
  const filters = Object.hasOwn(payload, "filters") ? payload.filters : {};
  if (!isRecord(filters)) {
    throw new RecommendationContractError("filters must be an object");
  }
  return {
    system: "general_market",
    contract_version: RECOMMENDATION_CONTRACT_VERSION,
    forecast_snapshot_id: payload.forecast_snapshot_id,
    model_version: payload.model_version,
    forecast_horizon_gameweeks: payload.forecast_horizon_gameweeks,
    forecast_quality: payload.forecast_quality,
    player_forecasts: payload.player_forecasts,
    filters,
  };
}

export function validatePersonalSquadRequest(payload) {
  validateShared(payload);
  const required = [
    "squad_snapshot", "bank", "free_transfers", "personal_risk_profile",
  ];
  const missing = required.filter((field) => !Object.hasOwn(payload, field));
  if (missing.length) {
    throw new RecommendationContractError(
      `Missing personal squad fields: ${missing.join(", ")}`,
    );
  }
  const squad = payload.squad_snapshot;
  if (!Array.isArray(squad) || squad.length !== 15) {
    throw new RecommendationContractError(
      "squad_snapshot must contain exactly 15 players",
    );
  }
  const ids = new Set();
  squad.forEach((player, index) => {
    if (!isRecord(player)) {
      throw new RecommendationContractError(
        `squad_snapshot[${index}] must be an object`,
      );
    }
    const id = player.fpl_element_id;
    if (!Number.isInteger(id) || id < 1) {
      throw new RecommendationContractError(
        `squad_snapshot[${index}].fpl_element_id must be a positive integer`,
      );
    }
    const key = String(id);
    if (ids.has(key)) {
      throw new RecommendationContractError(`Duplicate squad FPL element ID ${key}`);
    }
    ids.add(key);
    if (typeof player.purchase_price !== "number"
        || !Number.isFinite(player.purchase_price)
        || player.purchase_price <= 0) {
      throw new RecommendationContractError(
        `squad_snapshot[${index}].purchase_price must be positive`,
      );
    }
  });
  const forecastById = new Map(
    payload.player_forecasts.map((player) => [player.fpl_element_id, player]),
  );
  const positionCounts = { GKP: 0, DEF: 0, MID: 0, FWD: 0 };
  const teamCounts = new Map();
  for (const player of squad) {
    const forecast = forecastById.get(player.fpl_element_id);
    if (!forecast) {
      throw new RecommendationContractError(
        `Missing forecast for owned FPL element ID ${player.fpl_element_id}`,
      );
    }
    positionCounts[forecast.position] += 1;
    teamCounts.set(forecast.team_id, (teamCounts.get(forecast.team_id) ?? 0) + 1);
  }
  const expectedPositions = { GKP: 2, DEF: 5, MID: 5, FWD: 3 };
  if (Object.keys(expectedPositions).some(
    (position) => positionCounts[position] !== expectedPositions[position],
  )) {
    throw new RecommendationContractError(
      "squad position composition must be 2 GKP, 5 DEF, 5 MID and 3 FWD",
    );
  }
  if ([...teamCounts.values()].some((count) => count > 3)) {
    throw new RecommendationContractError(
      "squad cannot contain more than 3 players from one team",
    );
  }
  if (typeof payload.bank !== "number" || !Number.isFinite(payload.bank) || payload.bank < 0) {
    throw new RecommendationContractError("bank must be a non-negative number");
  }
  if (!Number.isInteger(payload.free_transfers) || payload.free_transfers < 0) {
    throw new RecommendationContractError(
      "free_transfers must be a non-negative integer",
    );
  }
  const risk = payload.personal_risk_profile;
  if (!((typeof risk === "string" && risk.trim()) || isRecord(risk))) {
    throw new RecommendationContractError(
      "personal_risk_profile must be a non-empty string or object",
    );
  }
  return {
    system: "personal_squad",
    contract_version: RECOMMENDATION_CONTRACT_VERSION,
    forecast_snapshot_id: payload.forecast_snapshot_id,
    model_version: payload.model_version,
    forecast_horizon_gameweeks: payload.forecast_horizon_gameweeks,
    forecast_quality: payload.forecast_quality,
    player_forecasts: payload.player_forecasts,
    squad_snapshot: payload.squad_snapshot,
    bank: payload.bank,
    free_transfers: payload.free_transfers,
    personal_risk_profile: payload.personal_risk_profile,
    chips: payload.chips ?? [],
    formation: payload.formation ?? null,
    starting_xi: payload.starting_xi ?? null,
    bench_order: payload.bench_order ?? null,
    manager_rank: payload.manager_rank ?? null,
    rank_target: payload.rank_target ?? null,
    personal_preferences: payload.personal_preferences ?? {},
  };
}
