#!/usr/bin/env node
import { createHash } from "node:crypto";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  parseDirectionCsv,
  runCoreEquivalent,
} from "./cta_core.mjs";

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (!flag.startsWith("--")) throw new Error(`Unexpected argument: ${flag}`);
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) throw new Error(`Missing value for ${flag}`);
    args[flag.slice(2)] = value;
    index += 1;
  }
  for (const required of ["events", "three-sixty", "out"]) {
    if (!args[required]) throw new Error(`Missing required option --${required}`);
  }
  return args;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

async function readJson(file) {
  return JSON.parse(await readFile(file, "utf8"));
}

async function writeJson(file, value) {
  await writeFile(file, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const eventPath = path.resolve(args.events);
  const framePath = path.resolve(args["three-sixty"]);
  const outDir = path.resolve(args.out);
  const [eventBytes, frameBytes] = await Promise.all([
    readFile(eventPath),
    readFile(framePath),
  ]);
  const rawEvents = JSON.parse(eventBytes.toString("utf8"));
  const frames = JSON.parse(frameBytes.toString("utf8"));
  const matchId = path.basename(eventPath, path.extname(eventPath));
  let directionOverrides = new Map();
  if (args["direction-map"]) {
    directionOverrides = parseDirectionCsv(await readFile(path.resolve(args["direction-map"]), "utf8"));
  }
  const result = runCoreEquivalent(rawEvents, frames, matchId, directionOverrides);

  await mkdir(outDir, { recursive: true });
  await Promise.all([
    writeJson(path.join(outDir, "sequences.json"), result.sequenceRows),
    writeJson(path.join(outDir, "players.json"), result.playerRows),
    writeJson(path.join(outDir, "xt_grid.json"), result.xtGridRows),
    writeJson(path.join(outDir, "input_diagnostics.json"), {
      statsbomb_360_audit: result.statsbomb360Audit,
      visible_player_coordinate_diagnostics: result.coordinateDiagnostics,
    }),
    writeJson(path.join(outDir, "javascript_run_manifest.json"), {
      implementation: "CTA-FPL core parity JavaScript reproduction",
      version: "1.0.3",
      match_id: result.matchId,
      input_files: {
        events: { path: eventPath, bytes: eventBytes.length, sha256: sha256(eventBytes) },
        three_sixty: { path: framePath, bytes: frameBytes.length, sha256: sha256(frameBytes) },
      },
      direction: result.directionAudit,
      core_summary: {
        events_processed: result.eventsProcessed,
        sequences_processed: result.sequenceRows.length,
        players_observed: result.playerRows.length,
        xt_grid_cells: result.xtGridRows.length,
        xt: result.xtAudit,
      },
    }),
  ]);

  process.stdout.write(`${JSON.stringify({
    match_id: result.matchId,
    events: result.eventsProcessed,
    sequences: result.sequenceRows.length,
    players: result.playerRows.length,
    xt_grid_cells: result.xtGridRows.length,
    frame_linkage: result.statsbomb360Audit,
    direction: result.directionAudit,
  }, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack ?? error}\n`);
  process.exitCode = 1;
});
