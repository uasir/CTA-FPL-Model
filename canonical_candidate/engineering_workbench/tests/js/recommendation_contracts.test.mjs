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
    player_forecasts: [
      { fpl_element_id: 1, expected_points: 4.2 },
      { fpl_element_id: 2, expected_points: 3.1 },
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
  general.player_forecasts.push({ fpl_element_id: 1 });
  assert.throws(() => validateGeneralMarketRequest(general), /Duplicate forecast/);

  const manager = personal();
  manager.player_forecasts.push({ fpl_element_id: 1 });
  assert.throws(() => validatePersonalSquadRequest(manager), /Duplicate forecast/);
});
