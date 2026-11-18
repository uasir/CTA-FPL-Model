import { readFileSync } from "node:fs";
import {
  validateGeneralMarketRequest,
  validatePersonalSquadRequest,
} from "../../src/js/recommendation_contracts.mjs";

const fixture = JSON.parse(
  readFileSync(new URL("../fixtures/recommendation_requests.json", import.meta.url), "utf8"),
);
const result = {
  general_market: validateGeneralMarketRequest(fixture.general_market),
  personal_squad: validatePersonalSquadRequest(fixture.personal_squad),
};
process.stdout.write(JSON.stringify(result));
