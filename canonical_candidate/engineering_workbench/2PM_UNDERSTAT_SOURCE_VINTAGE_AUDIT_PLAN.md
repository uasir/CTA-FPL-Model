# 2PM Understat historical source-vintage audit

**Status:** audit specification only; not executed; no Understat feature admitted.

## Why this audit is required

The pinned Dastan loader at `qazybekb/smartplayfpl-dastan@758db9247e8b3a9a870c991064f74d8339d61cd0/dastan/rebuild/sources.py` does not load a separate contemporaneous Understat player file for every season.

The loader:
- discovers player files across the pinned Vaastav Git tree using `data/<season>/understat/<player>_<understat_id>.csv`;
- selects the latest season-path file for each Understat player ID;
- checks whether that file contains all expected played-FPL-match dates across the requested seasons;
- fetches a complete current Understat player match history when any expected date is missing; and
- prefers the live fallback JSON over the pinned CSV for that player.

For team histories, it loads per-season pinned team CSVs, but replaces a season's pinned team histories with a live Understat team API response if the pinned files fail its expected-row completeness check.

Therefore, the candidate may combine later-season player-history files and live fallback snapshots to reconstruct earlier seasons. The source's existence in a present-day file is not proof that the row/value was publicly available before its historical FPL deadline.

## Pinned source identities

- Dastan source: `qazybekb/smartplayfpl-dastan@758db9247e8b3a9a870c991064f74d8339d61cd0`.
- Vaastav source pin read from Dastan `data/source_pins.json`: `vaastav/Fantasy-Premier-League@8c97b2adb123863c3dd581e730f1360e89815ac2`.
- The live fallback is retrieved through `understatapi`; the Dastan download manifest records an acquisition timestamp and file hash, but that timestamp is not a historical publication timestamp.

## Required audit units

Audit player and team sources separately. Do not use one global status for all Understat features.

### Player source audit

For every Understat player ID mapped to an FPL player and every expected player-match row:
1. Identify the exact pinned Vaastav player-history path selected by Dastan.
2. Retrieve the file's commit history up to the pinned Vaastav commit and identify the earliest repository revision in which the relevant match key (`understat_id + date`) is present.
3. Record the first observed repository commit timestamp and SHA, the path, file hash, row key, and field-level values.
4. Compare the historical row values across subsequent file revisions through the pinned commit. A row's first appearance and a later value correction are separate events; the first appearance does not establish the vintage of the final value.
5. If Dastan used a live fallback JSON, record that it superseded the pinned CSV, its acquisition timestamp/hash, and mark historical publication vintage UNKNOWN unless an independently archived contemporaneous Understat capture proves the row/value.
6. Compare the row's Understat date and fixture identity to the FPL fixture/player mapping. Date-only joins, postponed fixtures, double gameweeks, and duplicate player/date keys must be explicitly reported rather than silently matched.

### Team source audit

For every season/team/match:
1. Identify the exact per-season Vaastav team CSVs selected by Dastan.
2. Retrieve their commit histories up to the pinned Vaastav commit and record the first repository revision containing each team-match key.
3. Compare each match's xG/xGA, goals, deep, PPDA and related values across revisions; first appearance and final value are distinct.
4. If Dastan used a live team fallback for a season, mark its historical vintage UNKNOWN absent a contemporaneous archived capture.
5. Reconcile expected rows against the FPL fixture calendar, including both team perspectives, postponements, neutral/duplicate dates and renamed teams.

## Deadline decision rules

For a target FPL deadline (D), use strict source availability before (D), with the existing five-minute safety buffer where the source archive provides a reliable timestamp.

- **Repository-proven pre-deadline:** the exact row/value is present in a repository revision whose commit timestamp is strictly before (D - 5) minutes. This proves availability in that repository by that time, not necessarily when Understat first published it.
- **Repository first-seen after deadline:** the first archived repository revision containing the row/value is at or after (D - 5) minutes. It is not eligible for that deadline on repository evidence.
- **Live fallback / no archived vintage:** historical publication time is unknown; keep unobserved.
- **Row existed earlier but value changed later:** only the value in a revision proven before the deadline can be considered. Never backfill the final corrected value into earlier deadlines.
- **Missing row:** distinguish no match/player coverage, mapping failure, and source-file absence. Never convert missing Understat metrics to zero.

Repository commit timestamps are evidence about when a repository version was committed, not a guarantee of public visibility at the same instant, and do not establish the original Understat publication time. Record this limitation in every report.

## Output contract

Produce separate player-row and team-row audit tables, plus a feature-family summary. Each row should include:
- season, FPL deadline/Gameweek, FPL fixture ID, FPL player ID where applicable, Understat ID/team;
- source kind (`pinned_player_csv`, `live_player_fallback`, `pinned_team_csv`, `live_team_fallback`);
- exact source path, source commit SHA/time or fallback acquisition time, and file hash;
- Understat match ID/date and the FPL fixture join result;
- first-seen revision/time and per-field value-change history;
- deadline eligibility verdict and explicit reason.

Summary coverage must be reported by season, deadline, player/team, feature and source kind. Include counts for pre-deadline, first-seen-after-deadline, live-fallback-unknown, missing, mismatched and corrected rows.

## Guardrails

- This audit must not use target FPL points or model outcomes to decide source vintage.
- Do not infer historical publication time from a present-day API response, current file modification time, or the Dastan acquisition timestamp.
- Do not admit an entire feature family because a sample of rows passes.
- Do not alter the 286-feature schema, tensor values, masks, or training configuration as part of the audit.
- All 152 Understat-derived features remain HOLD until row-level vintage, join integrity, missingness, and field-level value parity are independently reviewed.
- Candidate remains NOT_ADMITTED and training remains unauthorized.

## Implemented first-stage inventory

The repository now contains `scripts/inventory_2pm_understat_sources.py`. It mirrors the pinned Dastan selection rule for latest player CSV paths, inventories the exact local player and team files, distinguishes pinned CSVs from live fallback JSONs and missing sources, and compares local file hashes with the Dastan `downloads.json` manifest where available.

The workflow runs this inventory after source restoration and publishes:
- `understat_source_inventory.json`
- `understat_source_inventory.csv`

Unit tests cover latest-player-path selection, team-file selection (excluding the aggregate player CSV), and pinned-versus-live fallback classification.

**Execution status:** code and workflow integration are committed, but the workflow has not yet been dispatched and the inventory has not yet run against the six-season restored source cache. This first-stage inventory does not inspect Git history row-by-row and cannot establish historical deadline eligibility. The next implementation stage must add commit-history/value-revision tracing for each player/team match key. No feature admission or training authorization changes.
