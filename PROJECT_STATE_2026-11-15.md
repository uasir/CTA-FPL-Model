# CTA-FPL Model — durable engineering state

Date: 2026-11-15
Status: source archives recovered and inspected; candidate baseline identified; local tests and synthetic CLI smoke test pass. Real pilot parity and FPL integration remain incomplete.

## Source recovery and archive integrity

All five recovery archives were found in the Library, materialized, extracted, and passed ZIP integrity checks (`ZipFile.testzip() == None`). Archive SHA-256 values:

- `CTA_FPL_reconstruction_scaffold_v0_1.zip`: `b96b6e3c3ef04b4e12d5d153f4f381843f4ecc2e48f0ae54d41d4ec14c1d6dc1`
- `CTA-FPL-Engineering-Workbench.zip`: `b7e62bec4299a63fb06d72e7bc38f54f2726ea68f366a29b4e3f64607f6e4630`
- `CTA_FPL_Model_v1_0_2_Engineering_Build.zip`: `7c8960ef250472eb2bb57b3d82f4ebec8dec00096482307470aedecb40cf5a73`
- `CTA_FPL_Model_v1_0_1_Engineering_Fix.zip`: `2c000b3c3f84bf1197303013d0d21e402b01d8ebfbddef3aa6558cfc50ab7553`
- `CTA_FPL_Model_v1_0_Experimental.zip`: `2d8278b593165b2bad7d55ee50969d166070e8872288a7fc59d07976ae17d749`

## Lineage assessment

1. `CTA_FPL_Model_v1_0_Experimental.zip` contains the initial v1.0 experimental model.
2. `CTA_FPL_Model_v1_0_1_Engineering_Fix.zip` changes `write_csv()` to use a stable first-seen union of row keys and `extrasaction='raise'`, fixing sparse player-counter CSV failures.
3. `CTA_FPL_Model_v1_0_2_Engineering_Build.zip` builds on v1.0.1 and adds `complete_statsbomb_directions()`: StatsBomb possession-oriented coordinates default to attacks-right and false direction overrides are rejected to prevent double-flipping. It also adds two tests for this behavior and updates version metadata to `1.0.2-experimental`.
4. `CTA-FPL-Engineering-Workbench.zip` is a separate complementary package: Python–JavaScript parity harness, feature registry, raw-data contract preflight, and exploratory xT baseline. Its examples are explicitly synthetic; it is not a replacement for the v1.0.2 pipeline.
5. `CTA_FPL_reconstruction_scaffold_v0_1.zip` is an earlier minimal scaffold, not the latest model.

Working candidate assembled non-destructively at `canonical_candidate/`: v1.0.2 model at root and the Workbench nested under `engineering_workbench/`. Original extracted archives remain untouched.

## Verified checks

- All ZIP archives passed integrity tests.
- v1.0.2 model unit tests: **7/7 PASS** (`python -m unittest discover -s tests -v`).
- Engineering Workbench unit tests: **17/17 PASS** (`PYTHONPATH=src python -m unittest discover -s tests -v`).
- v1.0.2 synthetic CLI smoke test: **PASS**. Three synthetic events, one match, two players; produced sequences/player features/16x12 xT grid/audit JSON; direction defaults active; synthetic 360 join 3/3 with 100% frame-to-event join and event coverage. This is execution-path verification only, not real-match validation.
- Workbench includes synthetic parity examples and tests. No actual Python-vs-JavaScript pilot parity pass has been established.

Note: `BUILD_TESTS.txt` in the v1.0.2 archive is stale and shows four earlier test cases plus a startup warning from a spreadsheet runtime. The current actual test file contains seven tests; all seven pass in the current Python runtime.

## Data and prior-run evidence

Pilot match: Bayer Leverkusen 2–2 VfB Stuttgart, StatsBomb match ID `3895320`.
Previously recorded source hashes:
- Events: `2f4cc3c3f8173e923485db7e0c814980080ecdb4`
- 360: `80cd519d37fcea4681e38a3806b69ae9f9af9fa0`

Previous connector-side JavaScript reproduction reports 3,771 events, 3,185 frames, 176 possessions/sequences, 32 observed players, 100% frame-to-event UUID join and 84.4604% event coverage. It explicitly did not execute original Python v1.0.2 and is not Python/JS parity evidence.

The two raw StatsBomb blobs were successfully fetched in this run through the GitHub connector (events 3,272,384 characters; 360 8,412,091 characters), but the connector result could not be transferred into the local Python filesystem. A local real-pilot Python execution and parity audit therefore remain unrun.

## FPL integration gates and limitations

The v1.0.2 README requires verified StatsBomb-player aliases to FPL player IDs, trusted player minutes, sequence-boundary harmonisation, multi-team/multi-match coverage, human review and inter-rater reliability for non-shot candidates, time-ordered FPL backtests, and forward validation. The current StatsBomb Open Data coverage is selected-competition and does not supply a complete current Premier League feed. A current-season FPL integration requires a licensed/permitted event or tracking source for the target league/season, or a clearly scoped historical evaluation.

No calibrated CTA composite or FPL points prediction exists. Preserve the vector of features; do not assign a sequence's total threat to every participant. Keep xT as an independent spatial baseline. EV/EO/CoVar are downstream FPL decision-layer requirements, not currently implemented in these recovered archives.

## Exact next actions

1. Transfer the immutable pilot event and 360 blobs into the local workspace using an approved connector/file route; verify their SHA-256 hashes against the hashes above.
2. Run the original v1.0.2 Python CLI on match `3895320`; preserve `sequences.csv`, `player_features.csv`, `xt_grid.csv`, and `audit.json`.
3. Run the JavaScript reproduction on exactly the same immutable inputs; export both runtime outputs.
4. Use `engineering_workbench/src/cta_audit/audit.py` and `config/feature_registry.json` for row-key, schema, join, null, categorical, numeric-tolerance, and per-feature parity checks. Freeze the registry/config only after evidence review.
5. Resolve mismatches and rerun the full affected audit. Do not widen tolerances or drop difficult rows to force a pass.
6. After pilot parity, execute the agreed 34-match audit; then independent time-safe xT and VAEP baselines; then CTA incremental evaluation.
7. Build the verified FPL ID/minutes mapping and time-ordered baseline-vs-baseline+CTA backtests. Add EV, EO and CoVar decision features only after data quality and predictive evaluation gates are passed.
8. Push the validated canonical project and durable state to the user's GitHub repository only after confirming the repository's current contents and selecting a reviewed commit plan; prior check found the public repo empty (size 0), so do not assume any prior code was pushed.

## Current state / no overclaim

Recovered source code is now available locally in this execution environment. Candidate baseline is v1.0.2 plus the separate Workbench. Synthetic/unit tests pass. Real pilot Python execution, real Python/JavaScript parity, 34-match validation, predictive validity, and FPL integration are all still open.

## Additional verification in immediate run

- Re-ran Workbench parity CLI against the packaged synthetic Python/JavaScript examples: PASS, 2 rows each, 2 shared keys, 0 missing/extra/duplicate/null keys, 4/4 registered features passed. Input SHA-256 values were identical for both example CSVs (`f5cee251eea7c81801f4a3cfc174c37109fcbb2d57a766d2ec8eea66bb235088`), so this remains a harness/synthetic smoke check, not independent runtime parity evidence.
- Re-ran v1.0.2 CLI end-to-end on a 3-event synthetic match with synthetic 360 frames: PASS; generated all expected output files, auto-filled the direction key, and reconciled 3/3 frame UUIDs. Temporary synthetic source inputs were removed from the extracted model tree after the test; outputs remain under `v102_cli_smoke/`.
- Reconfirmed GitHub repository `uasir/CTA-FPL-Model` is public, default branch `main`, currently size 0, and connector permissions include push. No files have been pushed yet.

## Immediate-run stop point

Next action remains immutable pilot data transfer into local Python execution. The GitHub connector can fetch the two raw source blobs by their known blob SHAs, but the connector response cannot be written into the local container filesystem through the available bridge. Do not substitute synthetic data for the real pilot. Continue by testing an approved connector-to-file transfer path or use a supported cloud execution route, then resume pilot Python CLI and row-level parity.
