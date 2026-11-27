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

This source-contract inspection preceded the dedicated bounded Python-tracer smoke run recorded below; neither activity is a deadline-eligibility decision. The team-key regression tests cover filename-derived identity, full timestamp, exclusion of `h_a` from identity, season-window boundaries, and rejection when team source identity is missing. No feature admission or training authorization changes.


The corrected team-key implementation and regression suite passed engineering CI run [46050270380](https://github.com/uasir/CTA-FPL-Model/actions/runs/46050270380), commit `828d1fbf7ef242075d68feaf3fa74a4a26d11e64`: **623 passed, 5 skipped, 18 warnings, and 3 subtests passed**. All JS contract, Python feature-core, engineering, and four identity-crosswalk validation steps completed successfully.


### Season-scoped team-row audit and sampled real revisions

The bounded read-only source inspection sampled five revisions each from the pinned 2024/25 Mohamed Salah player-history file (29 path commits total) and Arsenal team-history file (31 path commits total). Across those sampled revisions, player row counts/unique keys were 334, 341, 348, 356, and 365; team row counts/unique keys were 38, 7, 15, 23, and 31. No duplicate keys were found in the sampled revisions under the corrected player and team key contracts.

The team file's first sampled revision (2024-08-15) contained 38 rows dated in 2023/24; the later sampled revisions contained 2024/25 rows as that season progressed. This directly confirmed that the tracer must mirror Dastan's _load_vaastav_team_file season filter. The team row-key function now:
- derives season and understat_team from the exact pinned path;
- normalizes the parsed kickoff timestamp used by Dastan's team uniqueness check;
- excludes rows before July 1 of the path season or on/after July 1 of the following year, exactly matching Dastan's season-window filter; and
- leaves h_a in the row's value signature but not in its identity, so duplicate team/date rows cannot evade the duplicate-key guard by changing home/away.

Regression tests cover both July boundaries, exclusion of a previous-season row, source-path identity, and failure when the team source path is missing; h_a remains part of the row-value signature, not the row key. CI for commit 64bbecc90cb391d383120aa08e5cbb01e5a5dbe1 passed in run https://github.com/uasir/CTA-FPL-Model/actions/runs/46050586879: **626 passed, 5 skipped, 18 warnings, and 3 subtests passed**.

**Scope:** these five-revision samples validate source schema and row-key assumptions; they do not replace exhaustive row-level vintage adjudication or FPL fixture reconciliation. The dedicated two-file Python tracer smoke has now run successfully (see below), but the tracer has not yet been run against a generated six-season inventory artifact. No feature admission or training authorization changes.

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


### Dedicated Python tracer smoke result (2026-11-27)

The new focused workflow [46050872902](https://github.com/uasir/CTA-FPL-Model/actions/runs/46050872902) completed successfully against the pinned Vaastav commit. It ran the actual Python tracer on:
- Mohamed Salah player history, Understat ID 1250: five latest path revisions parsed, 365 distinct row keys in the latest revision.
- Arsenal team history: five latest path revisions parsed, 31 distinct season/team/kickoff row keys in the latest revision.

Both files returned **zero parser/duplicate-key errors**. Across the five sampled revisions, no row-value changes, disappearances, or reappearances were detected in these two files. The report marks both histories **truncated** because only five of 29 player revisions and five of 31 team revisions were requested; the sample therefore cannot establish first-ever row appearance or prove the absence of earlier revisions/corrections. The report keeps historical publication vintage UNKNOWN and admission_decision NO_FEATURES_ADMITTED.

The evidence artifact is workflow artifact `understat-source-revision-smoke` (ID `15224282557`). This is a real-source parser/row-identity smoke test using a minimal two-file inventory. It is separate from the candidate-rebuild workflow's six-season inventory and its 25-revision-per-file cached smoke audit, which still requires its own manual dispatch. No Understat features are admitted and no training authorization changes.

### First real pinned-source tracer smoke result (2026-11-27)

A dedicated GitHub Actions smoke run [46050872902](https://github.com/uasir/CTA-FPL-Model/actions/runs/46050872902) completed successfully on commit `a82a0478f6b2c105e45ce4e5ff358357093a3b6f`. It used a two-entry smoke inventory (one real pinned player file and one real pinned team file), requested the latest five path-specific revisions per file, and uploaded artifact [15224282557](https://github.com/uasir/CTA-FPL-Model/actions/runs/46050872902/artifacts/15224282557).

Observed results:
- **Mohamed Salah player history** `data/2024-25/understat/Mohamed_Salah_1250.csv`: all five revisions parsed, zero errors, no duplicate row keys. Row counts/unique keys increased 361 → 362 → 363 → 364 → 365. The four new rows first appeared in the successive sampled commits dated 2025-03-05, 2025-03-11, 2025-04-05, and 2025-04-11. No existing row value revisions, disappearances, or reappearances were detected in this five-revision window.
- **Arsenal team history** `data/2024-25/understat/understat_Arsenal.csv`: all five revisions parsed, zero errors, no duplicate row keys. Row counts/unique keys increased 27 → 28 → 29 → 30 → 31. The four new rows first appeared in the successive sampled commits dated 2025-03-11, 2025-03-24, 2025-04-05, and 2025-04-11. No existing row value revisions, disappearances, or reappearances were detected in this five-revision window.

Both results reported `history_truncated=true` because only five of 29 player-file commits and five of 31 team-file commits were requested. These are the latest five revisions, not the files' first revisions. The run validates live GitHub API access, CSV parsing, source-specific row identity, and revision-state tracking; it does **not** establish first appearance of historical rows, original Understat publication time, or deadline eligibility.

The candidate-rebuild workflow's generated six-season inventory and 25-revision resumable smoke step remain a separate, not-yet-dispatched workflow. No feature admission or training authorization changes.

### Complete pinned history for the two real-source smoke files (2026-11-27)

The expanded run [46051261448](https://github.com/uasir/CTA-FPL-Model/actions/runs/46051261448), commit `5302d4803602bdf5be5b1003c1404ad0bd57f96b`, completed the full path-specific histories through the pinned Vaastav commit for both smoke files. It returned 29/29 Salah player-file commits and 31/31 Arsenal team-file commits, with `history_truncated=false`, zero revision errors, and zero duplicate row keys. The report is artifact [15223928423](https://github.com/uasir/CTA-FPL-Model/actions/runs/46051261448/artifacts/15223928423).

**Salah player file**
- History spans 2024-08-15 17:16:49 UTC to 2025-04-11 12:32:01 UTC.
- The first revision contains 334 rows; the final revision contains 365. The 31 additional player-match rows were appended over the season.
- Across all 29 revisions, no existing row changed value, disappeared, or reappeared.

**Arsenal team file**
- History spans the same first and last commit timestamps.
- The first revision contains 38 raw rows, all from the prior season and therefore excluded by Dastan's 2024/25 July-to-June season filter. The first 2024/25 row appears in the 2024-08-20 revision; the final file has 31 eligible 2024/25 team-match rows.
- Across all 31 revisions, no eligible existing row changed value, disappeared, or reappeared.

This confirms the row lifecycle and revision parser over the complete repository history for these two files. It also illustrates why the team season filter matters: raw historical rows in a season-named file are not automatically rows for that season. The Salah file's initial 334-row snapshot was first present in the repository on 2024-08-15; therefore its repository lineage cannot substantiate availability of those rows at 2020/21–2023/24 deadlines. The later 2024/25 match rows were appended as the season progressed. For Arsenal, eligible 2024/25 team rows likewise first appear after the corresponding matches, beginning 2024-08-20.

These timestamps remain repository commit timestamps, not proof of public push time or Understat's original publication. We have not yet reconciled each row to official FPL fixture IDs and target Gameweek deadlines, so no row-level deadline admission is inferred. This audit covers only one player and one team's pinned files, not the full mapped population or all six seasons.

A cache-action correction followed: the dedicated workflow now uses `actions/cache/restore@v4` with a separate explicit save step, avoiding duplicate automatic/post-job cache saves. The repeat run [46051409807](https://github.com/uasir/CTA-FPL-Model/actions/runs/46051409807) completed successfully and reused/saved the resumable cache without the earlier duplicate-save warning. The candidate-rebuild workflow's Understat cache restore step was corrected the same way.

No feature admission or training authorization changes.

### Season distribution of the complete Salah player-history file

A follow-up inspection of the 365 tracked player rows by Understat's `season` field shows why latest-season player files cannot be treated as contemporaneous archives. In the pinned 2024/25 Salah CSV, all rows from Understat seasons 2014 through 2023 first appear together in the repository's first path revision on **2024-08-15 17:16:49 UTC**. This includes 37 rows tagged 2020, 35 tagged 2021, 38 tagged 2022, and 32 tagged 2023. The 31 rows tagged 2024 (2024/25) were appended over later revisions from 2024-08-20 through 2025-04-11.

For this player/file, repository lineage therefore provides no pre-deadline evidence for the 2020/21–2023/24 player-match rows; it only shows that they were present in the pinned repository by August 2024. This does not prove that Understat had not published the same values earlier through another channel, but the pinned Vaastav path cannot establish that earlier availability. The 2024/25 appended rows need a separate exact comparison against their next target Gameweek deadlines, with the repository-commit-versus-publication limitation retained.

This is one mapped player, not a population-wide conclusion. It reinforces the need for player-row vintage admission by row and season rather than assuming that a multi-season latest player file is a contemporaneous archive.

### Row-level as-of state events added and revalidated (2026-11-27)

The tracer now stores a compact `state_events` sequence per row: first appearance, each subsequent value change, each transition to missing, and each reappearance. Each event records the commit SHA, committer timestamp, presence status, and the full row-value signature when present. This makes it possible to reconstruct the row's last known repository value/state as of a candidate deadline, rather than relying only on first/latest signatures. Unchanged rows do not generate redundant events. Failed or duplicate-key revisions do not mutate the accepted event history.

The regression test now covers four chronological revisions: row appears at 0.2, disappears, reappears at 0.3, then changes to 0.4. It asserts the exact `present → missing → present → present` event sequence and both value revisions. Engineering CI run [46052122202](https://github.com/uasir/CTA-FPL-Model/actions/runs/46052122202) passed: **626 passed, 5 skipped, 18 warnings, and 3 subtests passed**.

The real-source full-path workflow was rerun on the state-event implementation: [run 46052122230](https://github.com/uasir/CTA-FPL-Model/actions/runs/46052122230), artifact [15225122341](https://github.com/uasir/CTA-FPL-Model/actions/runs/46052122230/artifacts/15225122341). It again parsed all 29 Salah revisions and all 31 Arsenal revisions, with no truncation, no errors, and no duplicate keys. The report contains 365 player-row presence events and 31 eligible team-row presence events; no value changes or missing/reappearance events occurred in these two histories. The cache restore/save flow completed successfully.

This event history is the necessary input for the next step: joining Understat source rows to canonical FPL fixtures and comparing each row's first-seen/value-event timestamps with the relevant target Gameweek deadlines. It remains repository-lineage evidence only, not proof of original Understat publication. No feature admission or training authorization changes.


### Empty-revision regression confirmed against the pinned real source (2026-11-27)

The corrected tracer completed the six-file real-source smoke workflow [run 46052818670](https://github.com/uasir/CTA-FPL-Model/actions/runs/46052818670), artifact [15226035441](https://github.com/uasir/CTA-FPL-Model/actions/runs/46052818670/artifacts/15226035441), at tracer commit `9f3d51335372a07cb2ab3baff313666efc335a7e`. All six requested histories were audited; all were complete (no truncation), with no parser errors and no duplicate-key failures. The audit preserved the Arsenal 2022/23 zero-byte revision `ca894952548be42c1d41b25c182e847568ffd52f` as an explicit `empty_file` revision with zero rows, rather than failing CSV parsing or silently skipping the revision.

The sample comprised the pinned 2024/25 Salah player file (29 commits, 365 row keys) and Arsenal team files: 2020/21 (40 commits, 45 row keys, 27 row-value revisions), 2021/22 (33 commits, 38 row keys, three missing/reappearance cycles), 2022/23 (37 commits, 39 row keys, including the explicit empty revision), 2023/24 (31 commits, 38 row keys), and 2024/25 (31 commits, 31 row keys). These counts describe repository path histories, not eligible historical observations. The workflow validation passed and the resumable cache was saved.

The next scope increase should be a bounded, diverse player/team sample across multiple clubs and seasons, using the restored cache, followed by canonical FPL fixture-key reconciliation and row-level comparison of first-seen/value-event times against target Gameweek deadlines. Do not scale to the full mapped population until sample runtime, API limits, row-key reconciliation, and revision semantics are validated. Repository timestamps remain lineage evidence only—not proof of original Understat publication or public visibility. No feature admission or training authorization changes: all 152 Understat features remain HOLD.

### Expanded complete-history sample and semantic revision audit (2026-11-27)

The dedicated workflow was expanded to seven mapped player files spanning the 2021/22, 2023/24, and 2024/25 source vintages, plus Arsenal team files for all five pinned seasons 2020/21–2024/25. Run [46053328557](https://github.com/uasir/CTA-FPL-Model/actions/runs/46053328557) completed successfully; artifact [15225930994](https://github.com/uasir/CTA-FPL-Model/actions/runs/46053328557/artifacts/15225930994). All 12 path histories were complete under the 100-commit cap, with zero parse errors and zero duplicate Dastan row keys.

The sampled player files contained 1,928 tracked rows across 23, 1, 1, 1, 14, 29, and 29 path commits respectively. None showed a value revision, disappearance, or reappearance in its sampled pinned history. Three files had only one path commit, so their repository lineage begins at that single commit; it does not establish earlier publication.

The five Arsenal team files contained 191 tracked row identities (183 present in the latest pinned revisions). The expanded history surfaced three important lifecycle cases:
- **2020/21:** seven July 2020 Arsenal rows appeared in the 2020/21 path on 2020-08-21 and were removed on 2020-09-15. They are outside the actual 2020/21 Premier League season but fell inside Dastan's July-to-June path-date filter while present. They are absent from the latest pinned file. This is a historical source correction/season-boundary issue, not evidence that the final pinned candidate contains those rows.
- **2021/22:** three early-season rows (2021-08-13, 2021-08-22, 2021-08-28) disappeared in the 2021-09-14 revision and reappeared unchanged on 2021-09-17. The state-event log preserves this temporary absence.
- **2022/23:** the team file had one whitespace-only empty revision on 2022-07-16, now correctly represented as `revision_status=empty_file`, not a CSV parser error. One Arsenal row first appeared dated 2023-03-02 20:00 and was later removed; a current row dated 2023-03-01 20:00 has an exact match on every non-date field. The tracer flags this as a **potential date correction**, not a confirmed fixture match, pending FPL fixture reconciliation.

A semantic signature correction was also added. Understat's `ppda` and `ppda_allowed` CSV cells are serialized dictionaries; key-order-only changes had previously inflated the 2020/21 team's value-revision count. The tracer now parses and canonicalizes structured cells before comparing rows. After this correction, all 12 sampled file histories report **zero semantic value revisions**. The three 2021/22 disappear/reappear rows and the 2020/21/2022/23 removals remain explicit presence events, not value changes.

Engineering CI run [46053323143](https://github.com/uasir/CTA-FPL-Model/actions/runs/46053323143) passed: **631 passed, 5 skipped, 18 warnings, and 3 subtests passed**.

**Next required analysis:** reconcile the potential 2022/23 date correction and the row lifecycle events to canonical FPL fixture IDs, official target deadlines, and the exact player/team rolling windows. Repository commit timestamps remain lineage evidence only; they are not proof of Understat publication or public visibility. This is still a 7-player/one-team sample, not population-wide admission. All 152 Understat features remain HOLD.
