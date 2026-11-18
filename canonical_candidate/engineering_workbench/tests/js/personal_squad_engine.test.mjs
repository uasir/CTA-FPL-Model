import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { recommendPersonalSquad } from "../../src/js/personal_squad_engine.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(
  fs.readFileSync(path.join(here, "../fixtures/recommendation_requests.json"), "utf8"),
);

function request() {
  const payload = structuredClone(fixture.personal_squad);
  payload.player_forecasts[2].price = 5.2;
  payload.player_forecasts.push(
    { fpl_element_id: 16, expected_points: 7.0, expected_minutes: 85, price: 5.0, position: "DEF", team_id: 6 },
    { fpl_element_id: 17, expected_points: 8.0, expected_minutes: 90, price: 5.0, position: "DEF", team_id: 1 },
    { fpl_element_id: 18, expected_points: 9.0, expected_minutes: 90, price: 20.0, position: "DEF", team_id: 7 },
  );
  return payload;
}

test("personal squad returns a legal XI and constrained transfer", () => {
  const result = recommendPersonalSquad(request());
  assert.equal(result.system, "personal_squad");
  assert.equal(result.squad_plan.formation, "4-3-3");
  assert.equal(result.squad_plan.starting_xi.length, 11);
  assert.ok(result.squad_plan.starting_xi.includes(result.squad_plan.captain));
  assert.equal(result.transfer_recommendation.action, "TRANSFER");
  assert.equal(result.transfer_recommendation.best_candidate.transfer_out_id, 6);
  assert.equal(result.transfer_recommendation.best_candidate.transfer_in_id, 17);
  const sameTeamReplacement = result.transfer_recommendation.alternatives.find(
    (candidate) => candidate.transfer_out_id === 3 && candidate.transfer_in_id === 16,
  );
  assert.equal(sameTeamReplacement.selling_price, 5.1);
  assert.equal(sameTeamReplacement.bank_after_transfer, 4.7);
  assert.equal(result.portfolio_risk.covar_used, false);
});

test("a four-point hit is applied when no free transfer remains", () => {
  const payload = request();
  payload.free_transfers = 0;
  payload.personal_preferences = { hit_cost_points: 5 };
  const result = recommendPersonalSquad(payload);
  assert.equal(result.transfer_recommendation.action, "HOLD");
  assert.equal(result.transfer_recommendation.hit_cost_points_applied, 5);
});

test("zero hit cost can be explicitly selected in personal preferences", () => {
  const payload = request();
  payload.free_transfers = 0;
  payload.personal_preferences = { hit_cost_points: 0 };
  const result = recommendPersonalSquad(payload);
  assert.equal(result.transfer_recommendation.action, "TRANSFER");
  assert.equal(result.transfer_recommendation.hit_cost_points_applied, 0);
});

test("invalid formation is rejected", () => {
  const payload = request();
  payload.formation = "2-4-4";
  assert.throws(() => recommendPersonalSquad(payload), /legal FPL/);
});


test("team limit allows a replacement only when outgoing player frees the same team slot", () => {
  const result = recommendPersonalSquad(request());
  const teamOneReplacements = result.transfer_recommendation.alternatives
    .filter((candidate) => candidate.transfer_in_id === 17);
  assert.ok(teamOneReplacements.length > 0);
  assert.ok(teamOneReplacements.every((candidate) => candidate.transfer_out_id === 6));
  assert.ok(result.transfer_recommendation.alternatives.every(
    (candidate) => candidate.transfer_in_id !== 18,
  ));
});


test("personal squad remains exploratory with a stale forecast snapshot", () => {
  const payload = request();
  payload.forecast_quality.validation_status = "VALIDATED";
  payload.forecast_quality.point_in_time_status = "VERIFIED";
  payload.forecast_quality.data_coverage.freshness_status = "STALE_OVER_24H";
  const result = recommendPersonalSquad(payload);
  assert.equal(result.recommendation_status, "EXPLORATORY_ONLY");
});


test("personal squad validated status requires fresh verified forecast", () => {
  const payload = request();
  payload.forecast_quality.validation_status = "VALIDATED";
  payload.forecast_quality.point_in_time_status = "VERIFIED";
  payload.forecast_quality.data_coverage.freshness_status = "FRESH_WITHIN_24H";
  const result = recommendPersonalSquad(payload);
  assert.equal(result.recommendation_status, "VALIDATED");
});
