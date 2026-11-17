import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  completeStatsBombDirections,
  coordinateDiagnostics,
  runCoreEquivalent,
} from "../../src/js/cta_core.mjs";

const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const fixtureRoot = path.resolve(testDirectory, "../fixtures/3895320");
const events = JSON.parse(await readFile(path.join(fixtureRoot, "events/3895320.json"), "utf8"));
const frames = JSON.parse(await readFile(path.join(fixtureRoot, "three-sixty/3895320.json"), "utf8"));
const fixtureManifest = JSON.parse(await readFile(path.join(fixtureRoot, "manifest.json"), "utf8"));

test("fixture is a deterministic subset of the verified real pilot", () => {
  assert.equal(fixtureManifest.match_id, "3895320");
  assert.match(fixtureManifest.provenance_note, /actual event and 360 records/i);
  assert.equal(events.length, fixtureManifest.selection.event_count);
  assert.equal(frames.length, fixtureManifest.selection.frame_count);
  assert.ok(fixtureManifest.edge_cases.missing_location_event_ids.length > 0);
  assert.ok(fixtureManifest.edge_cases.pressured_receipt_event_ids.length > 0);
  assert.ok(fixtureManifest.edge_cases.out_of_bounds_360_samples.length > 0);
});

test("StatsBomb direction convention defaults true and rejects a false override", () => {
  const event = events.find((row) => row.possession_team?.name);
  const augmented = { ...event, _match_id: "3895320" };
  const directions = completeStatsBombDirections([augmented]);
  assert.equal([...directions.values()].every(Boolean), true);

  const key = JSON.stringify(["3895320", Number(event.period), event.possession_team.name]);
  assert.throws(
    () => completeStatsBombDirections([augmented], new Map([[key, false]])),
    /must be true/,
  );
});

test("missing event locations remain missing and spatial counts stay deterministic", () => {
  const result = runCoreEquivalent(events, frames, "3895320");
  const missingLocationIds = new Set(fixtureManifest.edge_cases.missing_location_event_ids);
  assert.ok(events.some((event) => missingLocationIds.has(event.id) && event.location == null));
  const openingSequence = result.sequenceRows.find(
    (row) => row.period === 1 && row.possession_id === 1,
  );
  assert.ok(openingSequence);
  assert.equal(openingSequence.event_count, 4);
  assert.equal(openingSequence.box_entries, 0);
  assert.equal(openingSequence.final_third_entries, 0);
  assert.equal(openingSequence.progressive_actions, 0);
});

test("out-of-bounds 360 coordinates are preserved and not used as event locations", () => {
  const before = structuredClone(frames);
  const sample = fixtureManifest.edge_cases.out_of_bounds_360_samples[0];
  const frame = frames.find((row) => row.event_uuid === sample.event_uuid);
  assert.ok(frame);
  assert.ok(frame.freeze_frame.some(
    (player) => JSON.stringify(player.location) === JSON.stringify(sample.location),
  ));

  const diagnostics = coordinateDiagnostics(frames);
  assert.ok(diagnostics.out_of_bounds_nominal_120x80 > 0);
  const result = runCoreEquivalent(events, frames, "3895320");
  assert.ok(result.statsbomb360Audit.matched_frame_uuids > 0);
  assert.deepEqual(frames, before);
});

test("canonical player rows retain sparse missing values as null rather than zero", () => {
  const result = runCoreEquivalent(events, frames, "3895320");
  const player = result.playerRows.find((row) => row.shots === null);
  assert.ok(player, "fixture should include a player with no shot Counter key");
  assert.ok(Object.hasOwn(player, "shots"));
  assert.equal(player.shots, null);
});
