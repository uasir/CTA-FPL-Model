import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { recommendGeneralMarket } from "../../src/js/general_market_engine.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(
  fs.readFileSync(path.join(here, "../fixtures/recommendation_requests.json"), "utf8"),
);

function request() {
  return structuredClone(fixture.general_market);
}

function addLockedEoProvenance(payload) {
  Object.assign(payload.forecast_quality.data_coverage, {
    target_deadline_utc: "2026-11-28T11:00:00+00:00",
    eo_cohort: "overall top-10k rank-stratified sample",
    eo_sample_managers: 100,
    eo_rank_cohort_captured_at_utc: "2026-11-28T10:55:00+00:00",
    eo_deadline_time_utc: "2026-11-28T11:00:00+00:00",
    eo_picks_captured_at_utc: "2026-11-28T11:01:00+00:00",
    eo_picks_lock_verified: true,
  });
  return payload;
}

test("general market runs independently of any personal squad context", () => {
  const result = recommendGeneralMarket(request());
  assert.equal(result.system, "general_market");
  assert.equal(result.covar_used, false);
  assert.equal(result.categories.overall.length, 10);
  assert.equal(result.recommendation_status, "EXPLORATORY_ONLY");
  assert.equal(Object.hasOwn(result, "squad_snapshot"), false);
});

test("public filters constrain rankings deterministically", () => {
  const payload = request();
  payload.filters = { position: "MID", min_price: 6, limit: 3 };
  const result = recommendGeneralMarket(payload);
  assert.equal(result.categories.overall.length, 3);
  assert.ok(result.categories.overall.every((row) => row.position === "MID" && row.price >= 6));
});

test("differentials require explicit EO and a threshold", () => {
  const payload = addLockedEoProvenance(request());
  payload.player_forecasts[0].effective_ownership_pct = 4.5;
  payload.player_forecasts[1].effective_ownership_pct = 55;
  payload.filters = { differential_eo_max_pct: 10 };
  const result = recommendGeneralMarket(payload);
  assert.equal(result.categories.differentials.status, "SAMPLED_EO_AVAILABLE");
  assert.deepEqual(
    result.categories.differentials.players.map((row) => row.fpl_element_id),
    [1],
  );
});

test("missing EO is reported rather than inferred from global ownership", () => {
  const payload = request();
  payload.filters = { differential_eo_max_pct: 10 };
  const result = recommendGeneralMarket(payload);
  assert.equal(result.categories.differentials.status, "EO_UNAVAILABLE");
  assert.deepEqual(result.categories.differentials.players, []);
});

test("invalid filters are rejected", () => {
  const payload = request();
  payload.filters = { position: "WING" };
  assert.throws(() => recommendGeneralMarket(payload), /filters.position is invalid/);
});


test("null filters are rejected instead of silently ignored", () => {
  const payload = request();
  payload.filters = null;
  assert.throws(() => recommendGeneralMarket(payload), /filters must be an object/);
});


test("EO values without locked cohort provenance are rejected", () => {
  const payload = request();
  payload.player_forecasts[0].effective_ownership_pct = 4.5;
  assert.throws(
    () => recommendGeneralMarket(payload),
    /verified cohort and post-lock provenance/,
  );
});


test("EO deadline must match the forecast target deadline", () => {
  const payload = addLockedEoProvenance(request());
  payload.player_forecasts[0].effective_ownership_pct = 4.5;
  payload.forecast_quality.data_coverage.eo_rank_cohort_captured_at_utc = "2026-11-29T10:55:00+00:00";
  payload.forecast_quality.data_coverage.eo_deadline_time_utc = "2026-11-29T11:00:00+00:00";
  payload.forecast_quality.data_coverage.eo_picks_captured_at_utc = "2026-11-29T11:01:00+00:00";
  assert.throws(
    () => recommendGeneralMarket(payload),
    /does not match the forecast snapshot deadline/,
  );
});
