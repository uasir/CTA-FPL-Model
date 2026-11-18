import test from "node:test";
import assert from "node:assert/strict";
import {
  RecommendationContractError,
  validateGeneralMarketRequest,
  validatePersonalSquadRequest,
} from "../../src/js/recommendation_contracts.mjs";

function shared() {
  return {
    forecast_snapshot_id: "snapshot-2026-11-18T05:00:00Z",
    model_version: "unvalidated-baseline-0",
    forecast_horizon_gameweeks: 5,
    forecast_quality: {
      validation_status: "EXPLORATORY_ONLY",
      point_in_time_status: "NOT_VERIFIED",
      data_coverage: { season: "2026-27", gameweeks: [1, 10], players: 672 },
      limitations: ["Current snapshot; point-in-time history not verified."],
    },
    player_forecasts: [
      { fpl_element_id: 1, expected_points: 4.2, expected_minutes: 80, price: 5.0, position: "MID", team_id: 1 },
      { fpl_element_id: 2, expected_points: 3.1, expected_minutes: 75, price: 4.5, position: "DEF", team_id: 2 },
    ],
  };
}

function personal() {
  return {
    ...shared(),
    squad_snapshot: Array.from({ length: 15 }, (_, i) => ({
      fpl_element_id: i + 1,
      purchase_price: 5.0,
    })),
    bank: 4.6,
    free_transfers: 1,
    personal_risk_profile: "aggressive",
    chips: [],
    formation: "4-3-3",
  };
}

test("general market works without personal squad inputs", () => {
  const result = validateGeneralMarketRequest(shared());
  assert.equal(result.system, "general_market");
  assert.equal(Object.hasOwn(result, "squad_snapshot"), false);
});

test("general market rejects personal context, including nested fields", () => {
  for (const field of [
    "squad", "squad_snapshot", "bank", "free_transfers", "chips",
    "formation", "starting_xi", "bench_order", "manager_rank",
    "rank_target", "personal_risk_profile", "personal_preferences",
    "manager_id", "manager_entry_id", "team_id_for_manager",
  ]) {
    const payload = shared();
    payload[field] = "private";
    assert.throws(
      () => validateGeneralMarketRequest(payload),
      RecommendationContractError,
    );
  }
  const nested = shared();
  nested.filters = { position: "MID", nested: { squad_snapshot: [] } };
  assert.throws(
    () => validateGeneralMarketRequest(nested),
    /must not receive personal fields/,
  );
});

test("personal squad preserves manager constraints", () => {
  const result = validatePersonalSquadRequest(personal());
  assert.equal(result.system, "personal_squad");
  assert.equal(result.squad_snapshot.length, 15);
  assert.equal(result.bank, 4.6);
  assert.equal(result.free_transfers, 1);
  assert.equal(result.formation, "4-3-3");
  assert.equal(result.forecast_quality.point_in_time_status, "NOT_VERIFIED");
});

test("personal squad rejects malformed squad and budget constraints", () => {
  const short = personal();
  short.squad_snapshot.pop();
  assert.throws(() => validatePersonalSquadRequest(short), /exactly 15/);

  const duplicate = personal();
  duplicate.squad_snapshot[1] = duplicate.squad_snapshot[0];
  assert.throws(() => validatePersonalSquadRequest(duplicate), /Duplicate squad/);

  const negativeBank = personal();
  negativeBank.bank = -1;
  assert.throws(() => validatePersonalSquadRequest(negativeBank), /bank must be/);

  const noPrice = personal();
  delete noPrice.squad_snapshot[0].purchase_price;
  assert.throws(() => validatePersonalSquadRequest(noPrice), /purchase_price/);
});

test("both systems reject duplicate forecast IDs", () => {
  const general = shared();
  general.player_forecasts.push({ fpl_element_id: 1, expected_points: 4.2, expected_minutes: 80, price: 5.0, position: "MID", team_id: 1 });
  assert.throws(() => validateGeneralMarketRequest(general), /Duplicate forecast/);

  const manager = personal();
  manager.player_forecasts.push({ fpl_element_id: 1, expected_points: 4.2, expected_minutes: 80, price: 5.0, position: "MID", team_id: 1 });
  assert.throws(() => validatePersonalSquadRequest(manager), /Duplicate forecast/);
});


test("personal squad rejects non-finite money values", () => {
  for (const bad of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
    const bank = personal();
    bank.bank = bad;
    assert.throws(() => validatePersonalSquadRequest(bank), /bank must be/);

    const price = personal();
    price.squad_snapshot[0].purchase_price = bad;
    assert.throws(() => validatePersonalSquadRequest(price), /purchase_price/);
  }
});


test("both request types reject invalid forecast quality metadata", () => {
  const mutations = [
    (p) => { p.forecast_quality = null; },
    (p) => { p.forecast_quality.validation_status = "PRODUCTION_READY"; },
    (p) => { p.forecast_quality.point_in_time_status = "UNKNOWN"; },
    (p) => { p.forecast_quality.data_coverage = []; },
    (p) => { p.forecast_quality.limitations = "not-a-list"; },
    (p) => { delete p.forecast_quality.limitations; },
  ];
  for (const mutate of mutations) {
    for (const factory of [shared, personal]) {
      const payload = factory();
      mutate(payload);
      const validator = factory === shared
        ? validateGeneralMarketRequest
        : validatePersonalSquadRequest;
      assert.throws(() => validator(payload), /forecast_quality/);
    }
  }
});


test("player forecast records enforce shared required fields and bounds", () => {
  const cases = [
    ["expected_minutes", -1, /expected_minutes cannot be negative/],
    ["price", 0, /price must be positive/],
    ["position", "WING", /position is invalid/],
    ["team_id", 0, /team_id must be a positive integer/],
    ["availability_probability", 1.1, /availability_probability must be between 0 and 1/],
    ["points_variance", -0.1, /points_variance must be non-negative/],
  ];
  for (const [field, value, message] of cases) {
    const payload = shared();
    payload.player_forecasts[0][field] = value;
    assert.throws(() => validateGeneralMarketRequest(payload), message);
  }
  const missing = shared();
  delete missing.player_forecasts[0].expected_minutes;
  assert.throws(
    () => validateGeneralMarketRequest(missing),
    /expected_minutes must be a finite number/,
  );
});


test("squad purchase prices must be positive", () => {
  const payload = personal();
  payload.squad_snapshot[0].purchase_price = 0;
  assert.throws(
    () => validatePersonalSquadRequest(payload),
    /purchase_price must be a non-negative number/,
  );
});
