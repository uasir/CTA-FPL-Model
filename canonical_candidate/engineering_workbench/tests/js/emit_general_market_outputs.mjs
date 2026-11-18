import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { recommendGeneralMarket } from "../../src/js/general_market_engine.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(
  fs.readFileSync(path.join(here, "../fixtures/recommendation_requests.json"), "utf8"),
);
process.stdout.write(JSON.stringify(recommendGeneralMarket(fixture.general_market)));
