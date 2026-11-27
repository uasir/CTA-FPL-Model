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


## Second-stage implementation: pinned Git row-revision tracer

A first implementation is now present at `scripts/audit_2pm_understat_git_history.py`. It:
- queries the pinned Vaastav repository's path-specific commit history;
- fetches each returned file revision in chronological order;
- records commit timestamps and file SHA-256 values;
- builds per-row first-seen and value-change histories;
- separates player and team row keys; and
- marks publication vintage UNKNOWN, with explicit limits for truncated history and missing revisions.

Regression tests cover player keys using the mapped Understat ID (the source CSV itself does not carry that mapping ID) and team keys using the pinned team-file identity contract.

**Important implementation boundary:** this is a research tracer, not yet the full six-season deadline adjudicator. Its row keys still require reconciliation to FPL fixture IDs; it does not yet produce deadline-level eligibility, does not include live fallback JSON revision histories, and must be performance-tested before running against every file. GitHub API calls scale with file count and revision count, so a bounded sample/smoke run and cost/rate-limit assessment are required before full execution. It is deliberately not wired into the candidate rebuild workflow yet.

Engineering CI was triggered by push for commit `216e63a99b41e31e6e2ebddc6649f9aa87bca186`; the run was pending at the time of this update. Earlier inventory regression tests passed in CI run `46047545444` (commit `2e9185051ad992cfc3f012206211dd555790c24b`). No Understat features are admitted and no training authorization changes.


### Row-key correction and regression result

Inspection of the pinned Dastan loader clarified the exact join identities:
- Player history is validated for uniqueness on `(understat_id, date_only)`; the tracer now uses the mapped Understat ID plus the first ten characters of the source date, matching that contract.
- Team history is per-team; the pinned CSV filename supplies `understat_team`, while the row supplies the full match date and `h_a` flag.
- The tracer now fails the affected file revision closed if duplicate row keys are found, rather than silently overwriting a duplicate in its in-memory map.

The first corrected helper/test CI run passed: `46048025031`, with **619 passed, 5 skipped, 18 warnings, and 3 subtests passed**. Subsequent row-key alignment and duplicate-key guard commits have triggered fresh CI runs; their final status must be checked before treating the latest branch state as green. The earlier failure was a test exposing a missed helper-signature edit; that was corrected and the next run passed.


The revision tracer additionally records each row's last-seen revision, missing-revision count, reappearance count, and whether it remains present in the latest inspected revision. This avoids treating a row deleted and later reintroduced as continuously present. A mocked three-revision regression test exercises first appearance, deletion, reappearance, and value change; CI for the implementation commit `39b8369cf9533f0c93fb34a5353cb5dbc97da54a` passed (619 passed, 5 skipped, 18 warnings, 3 subtests).


### Latest regression-test hardening

A further lifecycle test now exercises a player row appearing, disappearing, reappearing, and changing value across three mocked revisions. The first run exposed a missing `io` import in the CSV byte-reader path (the audit function had caught that exception and returned an empty history, which the test had not previously asserted against). The import is fixed, and the regression now explicitly requires all three revisions to parse without errors. CI for commit `9227fec2f4dc97321da933cb707e261676d7ac21` is in progress; do not treat this latest change as green until that run completes.


### API isolation, atomic revision validation, and latest CI

The revision tracer was further hardened:
- GitHub API authorization is now sent only to `api.github.com`; raw source-file requests to `raw.githubusercontent.com` receive no API token.
- Each CSV revision is fully parsed and checked for duplicate row keys before any row-history state is mutated. A duplicate-key revision is rejected atomically, preserving the last accepted revision state.
- Regression tests now assert GitHub's newest-first commit-list ordering is reversed into chronological processing, check first/latest revision identities and value signatures, verify raw-host token isolation, and prove a duplicate revision cannot partially mutate accepted history.

The first run of the new duplicate-key test failed because its byte fixture encoded literal backslash-n text instead of actual CSV line breaks. The fixture was corrected; this was a test-data defect, not a production audit failure.

Engineering CI run [46049971385](https://github.com/uasir/CTA-FPL-Model/actions/runs/46049971385), for commit `3c7dfa25633f8151eedbd4bb404d4201997c4699`, completed successfully: **622 passed, 5 skipped, 18 warnings, and 3 subtests passed**. The job's JS contract tests, canonical Python feature-core tests, engineering pytest suite, and all four identity crosswalk validations passed.

**Execution boundary remains unchanged:** the tracer has not yet been run against actual pinned Vaastav player/team file histories. The candidate workflow has not been dispatched to generate the new six-season source inventory artifact, and the existing Run 86 artifact predates that inventory step. The tracer remains outside the candidate rebuild workflow until a bounded real-source smoke test and runtime/rate-limit assessment are completed. All 152 Understat features remain HOLD; no feature admission or training authorization changes.


### Real pinned-source schema correction: team row identity

A bounded read-only inspection of the pinned Vaastav Git tree and actual historical CSV revisions exposed a source-schema mismatch in the first tracer implementation. The team CSV schema contains `h_a`, `date`, and metrics such as xG/xGA; it does **not** contain home-team and away-team name columns. Each CSV is already team-specific (for example, `data/2024-25/understat/understat_Arsenal.csv`). The pinned Dastan loader derives `understat_team` from that filename and retains the full parsed match date.

The tracer's team row key has therefore been corrected to match the exact Dastan uniqueness contract: `season | filename-derived understat_team | parsed kickoff timestamp`. The `h_a` field is retained in the full row-value signature but is not part of row identity; otherwise a duplicate could evade detection by changing home/away. The key function also applies Dastan's season-directory date window (July 1 inclusive through the following July 1 exclusive). Player row keys are normalized to `understat_id | date_only`, matching the pinned Dastan uniqueness check.

The read-only source inspection confirmed:
- The pinned Vaastav tree is complete (not truncated) and contains 25,924 tree entries.
- The mapped Mohamed Salah Understat ID is 1250; Dastan's latest-path rule selects `data/2024-25/understat/Mohamed_Salah_1250.csv`.
- That player file has 29 path-specific commits through the pinned source commit. The earliest returned revision is dated 2024-08-15 and the latest 2025-04-11.
- The Arsenal team file `data/2024-25/understat/understat_Arsenal.csv` has 31 path-specific commits over the same first/last commit dates.
- Actual player and team CSV revisions were inspected at the oldest and newest returned commits; their headers confirmed the distinct player and team schemas.

This was a source-contract inspection, not a completed execution of the Python tracer or a deadline-eligibility decision. The team-key regression tests cover filename-derived identity, full timestamp, exclusion of `h_a` from identity, season-window boundaries, and rejection when team source identity is missing. No feature admission or training authorization changes.


The corrected team-key implementation and regression suite passed engineering CI run [46050270380](https://github.com/uasir/CTA-FPL-Model/actions/runs/46050270380), commit `828d1fbf7ef242075d68feaf3fa74a4a26d11e64`: **623 passed, 5 skipped, 18 warnings, and 3 subtests passed**. All JS contract, Python feature-core, engineering, and four identity-crosswalk validation steps completed successfully.


### Season-scoped team-row audit and sampled real revisions

The bounded read-only source inspection sampled five revisions each from the pinned 2024/25 Mohamed Salah player-history file (29 path commits total) and Arsenal team-history file (31 path commits total). Across those sampled revisions, player row counts/unique keys were 334, 341, 348, 356, and 365; team row counts/unique keys were 38, 7, 15, 23, and 31. No duplicate keys were found in the sampled revisions under the corrected player and team key contracts.

The team file's first sampled revision (2024-08-15) contained 38 rows dated in 2023/24; the later sampled revisions contained 2024/25 rows as that season progressed. This directly confirmed that the tracer must mirror Dastan's _load_vaastav_team_file season filter. The team row-key function now:
- derives season and understat_team from the exact pinned path;
- normalizes the parsed kickoff timestamp used by Dastan's team uniqueness check;
- excludes rows before July 1 of the path season or on/after July 1 of the following year, exactly matching Dastan's season-window filter; and
- leaves h_a in the row's value signature but not in its identity, so duplicate team/date rows cannot evade the duplicate-key guard by changing home/away.

Regression tests cover both July boundaries, exclusion of a previous-season row, source-path identity, and missing h_a/path failures. CI for commit 64bbecc90cb391d383120aa08e5cbb01e5a5dbe1 passed in run https://github.com/uasir/CTA-FPL-Model/actions/runs/46050586879: **626 passed, 5 skipped, 18 warnings, and 3 subtests passed**.

**Scope:** these five-revision samples validate source schema and row-key assumptions; they do not replace the Python tracer's full path-history execution, exhaustive row-level vintage adjudication, or FPL fixture reconciliation. The tracer has not yet been run end-to-end against a generated six-season inventory artifact. No feature admission or training authorization changes.

### Resumable revision cache and workflow smoke-test integration (2026-11-27)

The Python Git-history tracer now has resumable, source-pinned caches:
- Path-specific GitHub commit-list pages are cached by repository, pinned commit, source path, page, and page size.
- Raw CSV revision bytes are cached by repository, source path, and commit SHA, with a SHA-256 sidecar checked before reuse.
- Cache files are written atomically. Missing, malformed, or hash-mismatched cache entries are fetched again; already cached pages/revisions survive interrupted runs.
- CLI limits can independently select a bounded number of pinned player files and team files.

The candidate-rebuild workflow now restores a cache scoped to the pinned Vaastav source and tracer implementation, then performs a bounded smoke audit of one pinned player file and one pinned team file, with at most 25 path revisions per file. The cache is saved even if later workflow steps fail, and the smoke report is included in the workflow artifact and job summary. This is a schema/runtime smoke test only; a 25-revision cap is deliberately reported as potentially truncated and cannot establish a row's first-ever appearance.

Engineering CI for the latest team-identity and season-window tests completed successfully in run [46050701031](https://github.com/uasir/CTA-FPL-Model/actions/runs/46050701031): **626 passed, 5 skipped, 18 warnings, and 3 subtests passed**. The cache implementation and cache-reuse tests were also included in the passing run.

**Execution boundary:** the newly integrated candidate workflow has not yet been manually dispatched, so no generated six-season inventory or Python tracer smoke report exists yet. The current GitHub integration does not expose a workflow-dispatch action in this session. When manually dispatching the workflow, keep `rebuild_candidate=false` to reuse the completed candidate cache and avoid rebuilding the six-season candidate. The run must confirm the reusable raw-source/candidate caches are present; if not, it will fail closed rather than rebuild implicitly.

The audit still distinguishes Git repository commit history from original Understat publication time. Publication vintage remains UNKNOWN, all 152 Understat features remain HOLD, and no model training is authorized.
