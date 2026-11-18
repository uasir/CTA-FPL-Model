import fs from "node:fs";
import { recommendPersonalSquad } from "../../src/js/personal_squad_engine.mjs";

const [requestPath, outputPath] = process.argv.slice(2);
if (!requestPath || !outputPath) {
  throw new Error("Usage: node run_fpl_personal_squad_snapshot.mjs <request.json> <output.json>");
}
const request = JSON.parse(fs.readFileSync(requestPath, "utf8"));
const result = recommendPersonalSquad(request);
fs.writeFileSync(outputPath, JSON.stringify(result, null, 2));
