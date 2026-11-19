import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { recommendPersonalSquad } from "../../src/js/personal_squad_engine.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(
  fs.readFileSync(path.join(here, "../fixtures/recommendation_requests.json"), "utf8"),
);
const payload = structuredClone(fixture.personal_squad);
payload.player_forecasts[2].price = 5.2;
payload.player_forecasts.push(
  { fpl_element_id: 16, expected_points: 7.0, expected_minutes: 85, price: 5.0, position: "DEF", team_id: 6 },
  { fpl_element_id: 17, expected_points: 8.0, expected_minutes: 90, price: 5.0, position: "DEF", team_id: 1 },
  { fpl_element_id: 18, expected_points: 9.0, expected_minutes: 90, price: 20.0, position: "DEF", team_id: 7 },
);
for (const player of payload.player_forecasts) {
  player.cta = {
    identity_verified: true,
    identity_status: "VERIFIED_IDENTITY_AND_PRIOR_CTA_HISTORY",
    coverage_status: "HAS_PRIOR_VERIFIED_HISTORY",
    source_snapshot_as_of: "2026-11-10T12:21:18+00:00",
    composite: null,
    decision_use_status: "RESEARCH_ONLY_NOT_IN_BASELINE",
    fixtures: [{ fixture_id: "501", prior_matches_count: 3, features: { shots_avg: 2.5 } }],
  };
}
process.stdout.write(JSON.stringify(recommendPersonalSquad(payload)));
