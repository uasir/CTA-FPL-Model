import fs from "node:fs";
import { recommendGeneralMarket } from "../../src/js/general_market_engine.mjs";

const [snapshotPath, outputPath] = process.argv.slice(2);
if (!snapshotPath || !outputPath) {
  throw new Error("Usage: node run_fpl_general_market_snapshot.mjs <snapshot.json> <output.json>");
}
const snapshot = JSON.parse(fs.readFileSync(snapshotPath, "utf8"));
const result = recommendGeneralMarket(snapshot);
fs.writeFileSync(outputPath, JSON.stringify(result, null, 2));
