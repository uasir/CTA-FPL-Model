# M3 Five-Provider Conventional Forecast Integration

**Status:** Integration specification; provider-by-provider implementation in progress  
**Decision date:** 2026-11-21  
**Milestone:** M3 — Integrated Decision Engine

## 1. Provider set

The shared conventional forecast interface contains exactly these five providers:

1. FPL Cat — existing live adapter.
2. Sideline Quant — new adapter.
3. FPLRogue — new adapter.
4. FPL Lucho — new adapter.
5. FPL Wildcard — new adapter.

FPL Forecaster and FPL Review are excluded. Do not ingest their current forecasts or historical data, register them as active providers, or use them in provider comparisons.

### Other discovered sources — not active providers

- FPLWise is a permission-required research candidate only. Do not acquire, store, ingest or compare its forecasts until the provider's applicable terms and any required written authorization have been reviewed and confirmed.
- RotoWire is a research-only reference candidate pending explicit authorization for the intended acquisition and processing method. Do not automate extraction or use its projections as CTA forecast inputs before that review.
- These sources do not change the active five-provider set.

## 2. Integration principles

- One provider-neutral canonical snapshot contract; provider-specific acquisition and parsing adapters.
- Preserve provider name, product, variant, version, raw source bytes/hash, source URL, provider-declared generation/training/update time, local capture time, target Gameweek, deadline, grain and coverage.
- Preserve each provider's original expected-points values. Do not calibrate, rescale, average or blend forecasts at ingestion.
- Retain provider-specific additional fields (minutes, start probability, floor/ceiling, uncertainty and component estimates) as provider-native metadata. Do not relabel them as equivalent across providers without a separate semantic contract.
- A missing or untrusted provider-generation timestamp makes a snapshot diagnostic-only for strict pre-deadline decision use. Never substitute local retrieval time as provider-generation time.
- Reject post-deadline captures, target-Gameweek/deadline mismatches, duplicate keys, invalid numeric values and incomplete identity mapping.
- Preserve fixture-grain data. Any conversion to player-Gameweek grain must be an explicit, separately tested transformation that records its aggregation rule and source grain.
- Keep provider identity and outputs separately addressable through M3. Provider performance evaluation is deferred until the upcoming Gameweek's official scores are available (M2 evaluation gate); this does not block adapter engineering.
- No provider is promoted, selected as superior or weighted based on a single snapshot.

## 3. Public source discovery

### FPL Cat — existing integration

- Endpoint: `https://fplcat.com/api/v1/projections`
- Existing capture: `scripts/capture_fpl_cat_snapshot.py`
- Existing capture preserves raw provider and official FPL bootstrap payloads in the runner's temporary workspace, hashes, capture times, provider-declared `computed_at`, expected points and expected minutes. Its public workflow artifact is now metadata-only; raw forecast rows and FPL bootstrap data are not uploaded.
- Bounded live GW12 capture succeeded on 21 Nov 2026 at 17:44:52.710605Z (run [#44931714336](https://github.com/uasir/CTA-FPL-Model/actions/runs/44931714336)): 672 provider rows and 672 official FPL metadata rows; provider `computed_at` 17:10:08.084Z; capture strictly before the official GW12 deadline 27 Nov 2026 18:30Z. Provider API SHA-256: `e6a1bcd630578b71bbc50fcfa718d151f24463eddc33882efb9e866c33e488bb`; official bootstrap SHA-256: `74d3f581149bf05f977d02d862db5ba6e5c83c2b5e0711935811636daaf94435`. Snapshot ID: `fplcat-gw12-20261121T174452710605Z`. Generation time is explicitly verified; only the sanitized summary artifact was uploaded.
- Grain: player-Gameweek.
- Keep this implementation as the existing baseline; do not duplicate it with a second FPL Cat adapter.

### Sideline Quant — source verified

- Gameweek-specific JSON pattern: `https://sidelinequant.com/data/gw/{gameweek}/projections.json`
- Current pointer: `https://sidelinequant.com/data/latest.json` (redirects to the current Gameweek-specific resource).
- Public feed documents `generated_at`, `gameweek`, `deadline`, `n_players`, `n_rows`, model accuracy and row-level field definitions.
- Grain: player-fixture. A double-Gameweek player has multiple rows; the publisher explicitly says to sum fixture xP for the player-Gameweek total.
- Join key: `player_id` (official FPL element ID); fixture key: `fixture_id`.
- Forecast field: `xP`; minutes field: `e_mins`; start probability: `p_start`.
- The source is CC BY 4.0 for the provider's own data, with attribution; FPL-owned fields remain subject to their own terms.
- Implemented first-stage raw capture plus a parser for the documented `rows` array. The parser validates `player_id`, `fixture_id`, `gameweek`, `xP`, `e_mins` and `p_start`; cross-checks player IDs against the archived official FPL bootstrap; rejects duplicate player-fixture keys and provider count mismatches; and preserves all native row fields.
- The canonical snapshot remains at player-fixture grain. A separate derived player-Gameweek view explicitly sums fixture `xP` and provider `e_mins` by `player_id`, with fixture count and aggregation provenance. It does not aggregate start probabilities or fixture-level distribution fields; publisher-provided Gameweek distribution fields are retained once after cross-fixture consistency checks.
- The manual capture workflow now runs the parser after raw capture. A target Gameweek must be supplied explicitly; there is no stale default to a Gameweek whose deadline has passed. The workflow publishes only a sanitized metadata summary; raw provider rows and the official FPL bootstrap are not uploaded to the public repository's workflow artifacts.
- Engineering tests have been added for raw capture, fixture parser, double-Gameweek sum, native-field retention, identity mapping, duplicate keys and invalid Gameweek data. The M3 feature-branch CI run at commit `6427d3351d37d9715ca8d30219f7d678becc78fb` passed the full engineering test suite (433 tests and 3 subtests). This verifies software behavior, not forecast accuracy.


### Sideline Quant GW12 bounded live-capture attempt (2026-11-21)

- One pre-deadline GW12 capture was attempted through the existing workflow (run [#44931321831](https://github.com/uasir/CTA-FPL-Model/actions/runs/44931321831)).
- The provider's GW12-specific endpoint returned HTTP 404 before any source payload was captured. The provider's `latest.json` pointer still redirects to the GW11 release (generated 18 Nov 2026 03:33:09Z); the GW11 release is not a valid substitute for a GW12 decision snapshot.
- The temporary push trigger and marker were removed immediately after the attempt. The regular manual workflow remains available. Do not repeat the capture until the provider publishes a GW12 release or the current pointer advances.
- The parser and recommendation-boundary tests now verify that player-Gameweek expected minutes are explicitly summed from the provider's fixture-level `e_mins` alongside fixture xP. This is a provider-native aggregation, not a cross-provider minutes proxy. The fixture-grain source snapshot remains preserved, and start probabilities and fixture distribution fields are not summed.
- The bounded live attempt is therefore blocked by provider publication timing, not by the parser or recommendation contract. Software CI passed on commit `7568ccceb12bbb67faf7d8dc79bd2829b9734a55` (run [#44931237094](https://github.com/uasir/CTA-FPL-Model/actions/runs/44931237094)): 540 tests passed, 3 subtests passed, JavaScript recommendation contracts passed, and all four identity-crosswalk validators passed.

### FPLRogue — source verified

- Research page: `https://www.fplrogue.com/research/projections`
- Current CSV link: `https://www.fplrogue.com/research/projections.csv`
- Page identifies the current accepted release, target Gameweek, player count, projection engine (`xpts_v1`), update time and model-training time.
- Page exposes xPts, xMins, floor/ceiling and start probability, and states that floor/ceiling are indicative display ranges rather than calibrated probability intervals.
- Implemented first-stage accepted-release capture: archives the HTML page, CSV and official FPL bootstrap with independent SHA-256 hashes; records the exact CSV headers and row count; and cross-checks page Gameweek, player count and official deadline.
- The page's `Updated` timestamp and `Model trained` timestamp are retained separately. Because the page does not explicitly define `Updated` as the forecast-generation timestamp, the capture leaves canonical `generated_at_utc` unset and is diagnostic-only for strict point-in-time decision use until the provider's timestamp semantics are verified.
- Added a manual capture workflow and tests for page metadata, CSV shape, hashes, row-count checks and post-deadline rejection. A bounded live GW12 capture succeeded on 21 Nov 2026 at 17:24:30Z (GitHub Actions run [#44929866200](https://github.com/uasir/CTA-FPL-Model/actions/runs/44929866200)): 672 rows, target deadline 27 Nov 2026 18:30Z, provider release Updated 16:59Z, model trained 05:00Z. The actual CSV headers were `player_id`, `player`, `team`, `position`, `price`, `three_gw_xpts`, `next_gw_xpts`, `floor`, `ceiling`, `expected_minutes`, `start_probability`, `ownership_percent`, `gameweek`, `captured_at`, and `model_version`. Only a sanitized summary was uploaded; raw CSV, page HTML and official bootstrap remained in the ephemeral runner workspace.
- The schema inspector deliberately assigns no column semantics. The live schema confirms a `player_id` field, but the provider page does not document it as FPL's element ID, and the sanitized artifact contains no row values. Do not infer identity from the column name or row count. No canonical player-Gameweek parser or recommendation route is approved until the ID semantics and source-backed identity join are established. `generated_at_utc` also remains unset because the page's Updated and Model trained timestamps are not explicitly defined as the forecast-generation time.
- Attribution: FPLRogue. The source states it is independent and not affiliated with the Premier League.

### FPL Lucho — source verified

- Forecast page: `https://fpllucho.pythonanywhere.com/forecast`
- Current CSV link: `https://fpllucho.pythonanywhere.com/export/predictions.csv`
- The CSV export covers every player, xP and fixtures for the next four Gameweeks.
- The page reports an xP model calculation timestamp separately from the page build timestamp. A first-stage raw intake script now captures the page, CSV and official FPL bootstrap, preserving exact CSV bytes, headers and SHA-256 while recording page-build and raw-model calculation timestamps separately.
- The CSV export URL is verified from the live page's download link, but the actual CSV response remains unavailable to the current web reader (`text/csv`). Exact headers and values must be inspected from a permitted downloaded payload before mapping; no guessed column mapping is present.
- The served product is explicitly **odds-anchored xP**. Keep it distinct from raw model xP and the separately reported Odds xP series. The raw-model calculation time is not treated as the generation time of the served odds-anchored CSV; `generated_at_utc` remains null and strict point-in-time eligibility is withheld until the served forecast's timestamp semantics are established.
- Synthetic fixture tests cover timestamp provenance, raw-byte preservation, schema inspection, target Gameweek and deadline rejection. A bounded live GW12 capture succeeded on 21 Nov 2026 at 17:25:57Z (GitHub Actions run [#44929998742](https://github.com/uasir/CTA-FPL-Model/actions/runs/44929998742)): 672 rows, deadline 27 Nov 2026 18:30Z, page built 17:17Z, raw-model last calculated 14:41Z. The actual CSV headers were `id`, `name`, `team`, `position`, `price`, `status`, `chance_next_round`, `news`, `ownership_pct`, `xp_gw12`, `fixtures_gw12`, `xp_gw13`, `fixtures_gw13`, `xp_gw14`, `fixtures_gw14`, `xp_gw15`, `fixtures_gw15`, and `xp_total_4_gws`. The sanitized schema/provenance summary only was uploaded; raw CSV and bootstrap bytes remained in the ephemeral runner workspace. The `id` field is not documented by the provider as the official FPL element ID, so identity is not yet verified. No expected-minutes field appears in the export; the recommendation adapter's expected-minutes requirement must be resolved without substituting another provider's minutes. The served CSV remains diagnostic-only until identity, xP/minutes semantics and its own generation-time semantics are established.

### FPL Wildcard — source verified

- Projection dataset page: `https://fplwildcard.com/data/projections/`
- Current CSV link: `https://fplwildcard.com/data/projections/current.csv`
- Published grain: one row per selectable player in one projected Gameweek.
- Displayed forecast field: `xpts`; minutes: `xmins`; optional start, appearance, sixty-plus, blank and haul probabilities.
- Page exposes model version and projection update time; the adapter must preserve these values and their timestamp provenance.
- The site states that no redistribution licence is granted. **FPL Wildcard remains an active fifth provider; lack of redistribution permission is not a reason to drop it.** Do not republish raw rows, redistribute provider data, or place its raw/derived provider values in public repository files, public CI logs, or public workflow artifacts.
- Use a compliant acquisition route: prefer a user-initiated download or other provider-permitted access, then process the file in private, access-controlled project storage. Do not automate scraping or repeated downloads unless the provider's terms or written permission clearly allow that access method. If automated retrieval is not permitted, keep the provider active through the manual/private intake path rather than excluding it.
- Keep provider-specific values private and use only outputs/aggregates that are permitted for internal decision support. Re-check the applicable terms before any external display or sharing.
- A local/private parser validates required/optional headers, target Gameweek, SHA-256, duplicate rows and numeric/probability ranges. Its player-plus-club lookup against official FPL bootstrap names is a deterministic candidate join, not an independently verified provider-ID crosswalk. It explicitly marks identity as `UNVERIFIED_NAME_CLUB_MATCH`, so the shared recommendation adapter rejects it.
- The parser preserves raw rows only in the private intake result and leaves provider generation time unset. Identity and timing independently block strict recommendation use. Synthetic-fixture tests verify parser behavior only; the live CSV bytes and exact headers have not yet been inspected, and no live Wildcard capture has been performed.

## 4. Current engineering verification

- M3 feature-branch CI at commit `49ba63112276cb5dfc2713ad3635cfbc4ae520e7` completed successfully: **540 tests passed, 3 subtests passed**, plus JavaScript recommendation-contract tests and all four identity-crosswalk validators.
- This is software-contract and parser-fixture verification. It is not evidence that Sideline Quant, FPLRogue, FPL Lucho or FPL Wildcard live captures have succeeded, nor that any provider is forecast-accurate. The repository is public, so FPL Cat, Sideline Quant and FPLRogue workflows now upload metadata-only summaries; their raw source files remain temporary runner files and are not retained as public artifacts. FPL Lucho and FPL Wildcard remain private-intake paths.
- Provider crosswalk validation remains `EMPTY_NOT_READY` until actual source player IDs/names are mapped and checked.

## 5. Provider-specific implementation gates

A provider is not marked integrated merely because its URL is known. Each adapter must pass:

1. Successful retrieval with HTTP status, content type, source URL and retrieval timestamp recorded.
2. Raw response retention in private, access-controlled storage and SHA-256 verification. Never place raw provider rows or FPL bootstrap payloads in public GitHub artifacts; public workflow artifacts are limited to sanitized metadata summaries.
3. Exact schema/column verification against the actual downloaded payload.
4. Provider identity, product/variant and target Gameweek verification.
5. Provider-generation timestamp provenance and strict deadline eligibility handling.
6. FPL element identity mapping and duplicate/coverage checks.
7. Canonical contract normalization with source grain preserved.
8. Deterministic parser tests using captured, sanitized fixtures that respect source terms.
9. A provider-specific capture workflow or an explicitly documented compliant manual/private intake route where automation is not permitted. Restricted sources must not be forced into public artifact storage just to satisfy automation parity.

Do not create synthetic forecasts to fill gaps. A provider with unresolved access, terms or schema remains explicitly blocked/pending rather than being represented as integrated.

## 6. Evaluation boundary

The five providers are integrated as independent forecast sources. Formal provider-by-provider performance evaluation is deferred until the upcoming Gameweek's official scores are available. When evaluation begins, compare providers on matched player/Gameweek populations and common outcome/finality evidence, while retaining provider-specific native fields and separate scorecards. Do not infer that one provider is superior from unmatched coverage or a single Gameweek.

M4 recommendation-product performance evaluation is also deferred until the upcoming Gameweek's official scores. These evaluation deferrals do not stop independent M3 adapter and decision-engine engineering.


## 7. Shared provider routing boundary

The \`scripts/provider_forecast_router.py\` module is the common entry point for all five provider adapters. It validates the canonical snapshot, resolves the provider against the active registry, and checks the exact product and registered forecast variant. It returns a provider-labelled routing envelope and never blends provider values.

Routing outcomes are explicit:

- \`DIAGNOSTIC_ONLY\`: provider-generation time is missing or the snapshot is not strict pre-deadline eligible.
- \`EXPLICIT_PLAYER_GAMEWEEK_TRANSFORM_REQUIRED\`: the canonical source remains fixture-grain; no implicit aggregation is performed.
- \`READY_FOR_RECOMMENDATION_ADAPTER\`: a strict pre-deadline player-Gameweek snapshot is ready for the recommendation adapter, but has not yet been joined to player metadata.
- \`RECOMMENDATION_PAYLOAD_READY\`: the caller explicitly supplied player metadata and an as-of timestamp, and the existing recommendation adapter accepted the snapshot.

The router rejects excluded/research-only providers, unregistered products and unregistered variants. It does not claim that a provider is live-captured, calibrated, validated through M2, or production-approved. Sideline Quant fixture rows must first pass its documented explicit player-Gameweek derivation; provider-native rows remain preserved.


## FPLRogue schema inspection and registry alignment

The raw capture identifies FPLRogue as `accepted_projections_release` / `provider_native_xpts`, matching the active registry. The model engine label (for example `xpts_v1`) remains provider version metadata, not a forecast variant. `scripts/inspect_fplrogue_csv_schema.py` reports the exact CSV headers, row widths, sample values and conservative lexical type hints. It deliberately leaves every semantic field mapping unset. A normalized player-Gameweek adapter is blocked until the actual CSV bytes and provider documentation support each mapping; display labels such as xPts/xMins are not sufficient proof of units, timing, identity or statistical semantics.


## FPLRogue public release archive and forecast semantics (2026-11-21)

- The live research page identifies the accepted release as GW11, 672 players, engine `xpts_v1`, with distinct page-update and model-trained timestamps. It exposes a current CSV download and a dated-snapshot archive.
- The public historical archive currently lists 13 frozen accepted releases across GW3–GW9. Each archive entry exposes a dated snapshot page and CSV link; the publisher describes the archive as append-only and says releases are replaced only to correct capture errors.
- Treat each dated archive capture as its own point-in-time source object. Preserve its capture timestamp, target GW, engine/version, row count, source URL, raw hash and exact CSV bytes. Do not substitute the current live CSV for a historical snapshot.
- The live page distinguishes one-Gameweek “Next GW” xPts from a three-Gameweek xPts total. The provider's xPts description says expected points combine expected minutes and position-specific routes to FPL points. xMins and start probability are separate forecast fields.
- The current xPts v1 floor and ceiling are explicitly described by the publisher as indicative display ranges, not calibrated probability intervals or guaranteed bounds. Do not map them to q10/q90, floor/ceiling distributions or variance.
- The displayed “Updated” and “Model trained” times remain distinct. Neither is silently promoted to a forecast-generation timestamp. A dated archive's explicit “Captured” time can be recorded as the publisher's snapshot capture time, but the semantic relationship between that time and forecast generation must remain explicit.
- The web reader cannot retrieve the CSV payload because it is served as `text/csv`; no actual FPLRogue CSV bytes have yet been inspected by this project. The raw capture/schema-inspection tools are implemented, but no live capture or canonical column mapping is claimed.
- Historical archive discovery is research-source evidence only. It does not start or complete the deferred M2 forecast-performance evaluation.
- Attribution is required on public FPLRogue research material. Review the source's applicable terms before any redistribution or public artifact use; retain the current restricted/no-public-payload policy until reviewed.


## FPLRogue frozen archive intake implementation (2026-11-21)

- Added `capture_fplrogue_frozen_archive_raw(...)` for one explicitly selected dated archive release. It accepts the exact snapshot-page and frozen-CSV URLs; it is not a bulk archive crawler or scheduled downloader.
- The capture preserves the publisher's archived `Captured` time separately from local page/CSV/bootstrap retrieval times. It permits retrieval after the Gameweek deadline only when the publisher's frozen snapshot page declares a capture time before the official deadline.
- The function validates archive slug, target Gameweek, player count, CSV headers/row widths, publisher capture time against official FPL deadline, and model-training time against the archive capture time. It hashes and retains the exact page, CSV and official bootstrap bytes.
- It leaves `generated_at_utc` unset because the page does not explicitly define the archive capture time as the model's generation time. It marks the point-in-time status as publisher-asserted frozen pre-deadline archive, not as an independently verified generation timestamp.
- Synthetic tests cover post-deadline retrieval of a publisher-frozen pre-deadline release and rejection of a publisher capture that is itself after deadline.
- CI passed on commit `0d7419e305aaf0984d04a4d89b8ac398f058e23e`: 486 Python tests passed, 3 subtests passed, JavaScript contract tests passed, and all four crosswalk validation steps completed. This verifies code and fixtures only; no real archive CSV has yet been downloaded or inspected.


## Provider registry alignment check (2026-11-21)

- Corrected FPL Lucho raw-intake metadata to use the exact registry product `forecast_csv` and variant `served_odds_anchored_xp`. Human-readable variant semantics remain separately documented; raw model xP and Odds xP remain distinct registered variants and are not substituted for the served CSV.
- This resolves a routing-contract mismatch in which the capture metadata used descriptive labels that the shared registry would not accept. It does not imply the CSV columns have been semantically mapped or that the capture has been executed against live bytes.
- The live forecast page currently reports GW11, built 21 Nov 2026 09:13 UTC, with the model last calculated 09:03 UTC, and exports the next four Gameweeks. The page's export remains served odds-anchored xP. Preserve the build and raw-model calculation times separately; the served CSV's own generation timestamp remains undisclosed.
- CI passed on commit `84760c4bfac0d583e8cc0954c1db60d4eb4bb2f9` (run [#44893153890](https://github.com/uasir/CTA-FPL-Model/actions/runs/44893153890)): 486 Python tests passed, 3 subtests passed, JavaScript contract tests passed, and four crosswalk checks completed.



## FPL Lucho schema-only inspection utility (2026-11-21)

- Added `scripts/inspect_fpl_lucho_csv_schema.py` to inspect an actual private capture after retrieval. It verifies provider/product/variant identity and the raw CSV SHA-256 before reporting exact headers, row counts, lexical type counts and Gameweek-like header tokens.
- Unlike a value-sampling report, the Lucho inspector deliberately emits no player names or forecast row values. Every column remains semantically unmapped; the tool does not infer xP units, player identity, or Gameweek semantics from header text alone.
- Added synthetic tests for hash mismatch, provider-variant mismatch, duplicate headers, ragged rows, empty CSV, Gameweek token extraction and absence of raw row values in the report.
- Registry status now records that a schema-only inspector exists. It does **not** claim that the live CSV was retrieved, inspected, normalized or routed. The export remains inaccessible to the current CSV retrieval tools; a permitted private intake is still required.


## FPL Lucho one-shot pre-deadline capture workflow (2026-11-21)

- Added manual workflow `.github/workflows/capture-fpl-lucho-benchmark.yml` for one explicitly selected season/Gameweek. It runs the existing raw intake against the live forecast page, CSV export and official FPL bootstrap; the capture fails closed if the provider page/model timestamps or any retrieval timestamp are at or after the official target deadline.
- The raw capture JSON, including exact CSV bytes and official bootstrap, exists only in the ephemeral Actions runner workspace. The workflow emits a sanitized metadata-only summary to the public job log; it does not upload a raw or normalized forecast artifact.
- Extended `summarize_provider_capture.py` with an FPL Lucho allow-list containing schema headers, row count, SHA-256, page-build/raw-model timestamps, capture/deadline timestamps and the explicit undisclosed served-CSV generation-time status. No player names, row values or raw payload fields are included.
- Added summary and workflow contract tests. A successful run would verify one live retrieval and exact CSV schema availability only. Because the served CSV generation timestamp is not separately disclosed, the resulting capture remains diagnostic-only for strict pre-deadline decision use; it does not authorize semantic column mapping or provider evaluation.
- The workflow has not yet been dispatched. A manual run before the target deadline is the single bounded live attempt; if it fails, preserve the diagnostic and do not enter repeated troubleshooting.


## FPL Lucho workflow correction (2026-11-21)

- The one-shot manual capture workflow now retains a 90-day metadata-only artifact containing verified schema headers, row count, source hash and separate page/model/capture/deadline timestamps. Raw CSV, page HTML and official bootstrap remain ephemeral runner files and are excluded from artifact upload.
- This supersedes the earlier statement that Lucho had no workflow/artifact. This is workflow plumbing only; no live run has been dispatched, and no provider forecast values are made public.


## Recommendation-boundary identity provenance (2026-11-21)

The shared recommendation adapter now fails closed unless coverage declares both identity_mapped_count equal to row_count and identity_resolution_status equal to VERIFIED. A row count or populated FPL ID alone is not evidence that a provider identity has been verified.

- FPL Cat: each provider players[].id must be an integer present in the contemporaneously archived official FPL bootstrap elements[].id set. The capture rejects duplicate IDs and IDs absent from that set, and records VERIFIED with direct-ID provenance. This is not a third-party crosswalk; it is an exact provider-ID-to-official-element-ID equality check.
- Sideline Quant: its player_id is checked as an exact integer member of the archived official FPL bootstrap elements[].id set. The canonical fixture snapshot and its documented player-Gameweek derivative carry VERIFIED with explicit direct-ID provenance.
- FPL Wildcard: the parser currently resolves normalized player name + club against official bootstrap names and club short names. This is a useful deterministic candidate join, but it is not an independently verified provider-ID crosswalk. It is explicitly marked UNVERIFIED_NAME_CLUB_MATCH; it remains diagnostic-only, and its absent provider-generation timestamp independently blocks decision use.
- Other providers must state their own source-backed identity-resolution method before recommendation routing. Do not mark provider-native IDs or heuristic name matches as verified merely because every row found a match.

This gate is independent of forecast timing, coverage completeness, and M2 forecast-performance validation. Passing it does not promote a provider or make a recommendation release-eligible.


## FPLRogue GW12 bounded capture (2026-11-21)

- The one-shot push-triggered capture completed successfully in workflow run 44929866200. It captured 672 CSV rows and 15 headers; the metadata-only artifact records SHA-256 `af1967699b67996d55462cedb4e61d9c3a5c1372e1af5d823afb93d1715f71dc`, target GW12, page release update 2026-11-21 16:59 UTC, model-trained timestamp 2026-11-21 05:00 UTC, capture 17:24 UTC, and official deadline 2026-11-27 18:30 UTC.
- Headers include `player_id`, `player`, `team`, `position`, `price`, `three_gw_xpts`, `next_gw_xpts`, `floor`, `ceiling`, `expected_minutes`, `start_probability`, `ownership_percent`, `gameweek`, `captured_at`, and `model_version`.
- This confirms the live CSV schema and pre-deadline release/capture provenance only. The provider's distinct forecast-generation timestamp remains undisclosed, and the meaning of `player_id` has not been verified against official FPL element IDs. Therefore no normalized forecast or verified identity status is created; FPLRogue remains diagnostic-only. The single bounded capture is complete; do not repeat retrieval merely to troubleshoot this blocker.
- Public artifact: `fplrogue-summary-2026-27-gw12-44929866200` (metadata-only; 90-day retention). Workflow run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44929866200


## FPL Lucho GW12 bounded capture (2026-11-21)

- The one-shot workflow completed successfully in run 44929998742. It captured 672 CSV rows and 18 headers. The metadata-only artifact records SHA-256 `10a0ce426f60bbcb01b0ebda6bfcc21941aa82e02922d44bd32fceecfd32c623`, page build 2026-11-21 17:17 UTC, raw-model last-calculated time 14:41 UTC, CSV capture 17:25 UTC, and official GW12 deadline 2026-11-27 18:30 UTC.
- Headers include `id`, `name`, `team`, `position`, `price`, `status`, `chance_next_round`, `news`, `ownership_pct`, `xp_gw12` through `xp_gw15`, matching fixture columns, and `xp_total_4_gws`.

- Additional adapter blocker: the captured Lucho CSV has no expected-minutes column. Do not infer minutes from `status`, `chance_next_round`, or another provider's forecast. A provider-native minutes source or documented derivation would be required before this feed can satisfy the recommendation adapter.
- The served CSV's own forecast-generation timestamp is not separately disclosed. Page-build and raw-model calculation timestamps are not silently substituted for it. The `id` column is observed, but its equality to official FPL element IDs has not been verified. Therefore the capture remains diagnostic-only and no canonical player forecasts or verified identity status are created.
- This completes the single bounded live capture. Do not repeat retrieval to work around the undisclosed served-CSV timestamp or unresolved ID semantics. Public artifact: `fpl-lucho-summary-2026-27-gw12-44929998742` (metadata-only; 90-day retention). Workflow run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44929998742

## Bounded three-provider resolution decision (2026-11-21)

A focused follow-up review was completed after the GW12 live captures. The three unresolved providers remain in the five-provider architecture, but no further acquisition or schema work is justified until a specific blocker can be resolved from provider evidence.

- **FPLRogue:** the live release documents xPts, xMins, model engine, an Updated time and a Model trained time. The live CSV has a `player_id` column, but the provider does not document that field as the official FPL element ID. The two displayed timestamps are not defined as the forecast-generation time. Existing GW12 capture already established the live schema; do not repeat it. Status: diagnostic-only; identity and strict point-in-time provenance unresolved.
- **FPL Lucho:** the provider's methodology states that the served odds-anchored xP includes the provider's minutes model, but the exported CSV does not contain expected minutes. The current shared recommendation contract requires expected minutes and uses them as a deterministic ranking tie-breaker. Do not borrow minutes from FPL Cat, FPL bootstrap, or another provider, and do not silently treat the CSV's `chance_next_round` as minutes. Supporting this source would require a separately specified xP-only recommendation contract and a provider-documented identity/timestamp route. Its single GW12 live capture is complete; do not repeat it. Status: diagnostic-only.
- **FPL Wildcard:** the public schema documents xPts, xMins, a permanent profile URL and model version, but no provider FPL-element ID. The existing name-plus-club join is only a candidate identity match and remains explicitly unverified. The site states that no redistribution licence is granted; any future intake must remain private and comply with the provider's terms. The published projection-update time is retained as update metadata, not silently treated as forecast-generation time. Status: private diagnostic intake only; identity and strict point-in-time provenance unresolved.

**Working decision:** proceed with the two providers that currently satisfy the direct-ID and generation-time requirements (FPL Cat and Sideline Quant). Keep the other three registered as diagnostic/pending providers; do not fabricate mappings, weaken shared validation, or blend provider-specific fields. Reopen an individual blocker only when new provider documentation, a permitted private artifact, or an explicit provider response supplies the missing evidence. This is a bounded-effort stop, not a change to the five-provider architecture or a claim of forecast-performance validation.


## Bounded disposition of the remaining three providers — 2026-11-21

A final bounded evidence check was made against the live publisher pages after the GW12 captures. The five-provider architecture is retained, but only FPL Cat and Sideline Quant are currently eligible for the shared conventional recommendation path.

### FPLRogue

- The live research page now explicitly describes the dataset as exposing a capture time and labels the release timestamp as `Updated`. Preserve this as provider-declared release/capture provenance; do not relabel it as model-generation time.
- The page separately labels `Model trained`; this is training provenance, not proof of when the forecast rows were generated.
- The live schema has `next_gw_xpts`, `three_gw_xpts`, `expected_minutes`, `start_probability`, and `player_id`. If a future source-backed identity crosswalk is established, the one-GW forecast candidate is `next_gw_xpts`; the three-GW horizon must remain a distinct horizon, not be substituted for the target-GW forecast.
- The publisher does not document `player_id` as the official FPL element ID. Do not infer its semantics from its name, numeric shape, row count, or apparent overlap with official IDs.
- Disposition: keep the accepted-release capture and schema inspection; no canonical decision adapter or recommendation handoff until the ID crosswalk is independently verified. Provider release capture time is retained separately from forecast-generation time.

### FPL Lucho

- Rechecked the live glossary: the served forecast is odds-anchored xP, distinct from raw model xP and the separately displayed Odds xP series. Keep the current registry variant `served_odds_anchored_xp`; do not relabel it as raw model xP.
- The live page's `xP model last calculated` timestamp is not documented as the generation timestamp of the served odds-anchored CSV. Page build, raw-model calculation, CSV retrieval and official metadata retrieval remain separate timestamps.
- The captured CSV has no expected-minutes field. Do not inject minutes from FPL Cat, Sideline Quant or any other provider. The existing recommendation adapter requires provider-native expected minutes or a separately justified metadata source; no such source is established for this export.
- The CSV `id` field is not documented as an official FPL element ID. Do not promote it based on its header or numeric overlap.
- Disposition: keep the bounded raw capture and exact schema record as diagnostic evidence. No shared recommendation handoff until identity, served-forecast timing and the minutes contract are independently resolved. No second live capture is warranted for this blocker.

### FPL Wildcard

- The live data page confirms the documented player-Gameweek schema, including `xpts`, `xmins`, optional probability fields, model version and a separate `Projections updated` timestamp.
- The CSV endpoint is not readable by the current web text reader because it is served as `text/csv`; the previously implemented parser remains a private local-file intake path. Do not use this reader limitation as a reason to scrape or redistribute the payload.
- `profile_url` is documented as a permanent player page, but no provider documentation found in this bounded check establishes that it contains or resolves to the official FPL element ID.
- The existing exact name+club join remains explicitly `UNVERIFIED_NAME_CLUB_MATCH`; it is not accepted by the strict recommendation identity gate. Do not weaken the gate or relabel this heuristic as verified.
- The provider states that no redistribution licence is granted. Keep all raw rows and provider-specific derived values in private, access-controlled storage; do not place them in public repository files, public CI logs or public workflow artifacts.
- Disposition: retain the private parser and manual/private intake option. Do not automate repeated retrieval or publish provider rows. No shared recommendation handoff until a source-backed identity crosswalk and a compliant private acquisition route are established.

### M3 operating decision

- Proceed with FPL Cat and Sideline Quant as the two eligible external forecast sources. This is a practical integration fallback, not a provider-quality ranking or permanent exclusion of the other three.
- Keep FPLRogue, FPL Lucho and FPL Wildcard in the five-provider registry as diagnostic/research candidates with their blockers explicit.
- Do not blend provider outputs, substitute one provider's minutes into another provider's forecast, or weaken identity/timing requirements to increase the provider count.
- Do not repeat the bounded live captures solely to obtain the same fields. Revisit a blocked provider only when new provider documentation, a genuine identity crosswalk, a disclosed served-forecast timestamp, or a permitted private data-access route becomes available.
- Forecast accuracy and recommendation-value evaluation remain deferred until the upcoming Gameweek's official scores are available.


## Pre-deadline field exposure refinement — 2026-11-21

- The official manager picks capture now retains `active_chip` and marks whether that value was present in the captured official picks response. A fallback based on prior-GW picks and user-confirmed squad identity explicitly records chip state as not captured; it does not infer a target-GW chip from historical chips.
- Personal captain exposure is 200% with a verified ordinary active-chip state and 300% when the captured official `active_chip` is `3xc`. If active-chip state is unavailable, the captain's personal EO and EO delta are left unknown rather than guessed. The field exposure calculation remains descriptive and does not change EV, captaincy, transfer selection or release eligibility.
- The field CSV validator bounds owned, starting, captain, Triple Captain and scoring-exposure rates to 0–100%. Effective ownership and its confidence interval are allowed above 100%, up to the 300% theoretical ceiling, because captaincy and Triple Captain multipliers can produce EO above 100%.
- Regression coverage includes official Triple Captain capture, 300% personal captain exposure, unknown-chip fail-closed behavior, and field-rate bounds.
- CI run [44931550873](https://github.com/uasir/CTA-FPL-Model/actions/runs/44931550873) passed on commit `40b24645a199924b911de6d9a1dd1f8482778bc0`: 544 tests passed, 3 subtests passed, and all four identity-crosswalk validators passed.


### Current GW12 availability decision — 2026-11-21

- FPL Cat now has a verified pre-deadline GW12 snapshot: 672 provider rows, 672 official FPL metadata rows, documented provider generation timestamp and direct official FPL element-ID semantics. It is the currently available decision-eligible provider snapshot.
- Sideline Quant's GW12 endpoint returned HTTP 404 in the one bounded attempt (run [#44931321831](https://github.com/uasir/CTA-FPL-Model/actions/runs/44931321831)); the publisher's latest pointer remained on the GW11 release. The parser and provider-native fixture-to-Gameweek transformation are implemented and tested, but there is no current GW12 artifact. Do not reuse GW11 as a GW12 forecast or repeat the request until the publisher releases GW12.
- Therefore, retain the two-provider integration architecture and continue M3 engineering, but do not claim that two current GW12 snapshots are available. FPL Cat is the only currently captured GW12 decision-eligible forecast; Sideline Quant becomes the second live input when its GW12 feed is published.
- The one-shot FPL Cat push trigger and marker were removed after the successful capture. The ordinary manual workflow remains. No recurring capture automation was added.


## Historical CoVar overlay — research-only handoff

- The pre-deadline M3 decision and replay workflow accept an optional `covar_capture_run_id`. When supplied, the workflow downloads the artifact from the separate Onside covariance run and passes its report and pairwise covariance CSV into the M3 overlay. Omitting the input leaves the conventional decision path unchanged.
- The overlay accepts only the Onside artifact marked `EXPLORATORY_ONSIDE_ACTUALS_ONLY`, `production_use: false`, and `model_trained: false`. It now checks the HTTPS source URL, SHA-256, retrieval timestamp with timezone, attribution, actual-points-only source-panel declaration, complete-case sample-covariance method, and internally consistent diagonal-shrinkage metadata. Negative diagonal covariance and duplicate pair keys are rejected.
- It uses conventional provider xP as the mean and Onside historical realized-points covariance as a separate descriptive risk proxy. It does not train a forecast, calibrate a forward joint distribution, or alter the frozen EV decision. `decision_weight=0` and `production_eligible=false` remain mandatory.
- When a valid provisional pre-deadline field exposure sample is also supplied and covariance coverage supports the required player pairs, the overlay computes a *representative field-average exposure portfolio proxy* and the variance of the personal XI relative to that representative exposure portfolio. This is not the average of sampled managers' individual portfolio variances and does not reconstruct their joint portfolios. It remains a marginal-exposure approximation; manager-level joint CoVar is still unavailable.
- If covariance coverage is incomplete, the field-average proxy and relative variance remain unavailable rather than filling missing player covariance with zero. If the field sample is absent, the output explicitly reports `NOT_AVAILABLE_NO_FIELD_EXPOSURE_CAPTURE`.
- Latest verified full CI before the provenance-hardening patch: run [#44932689482](https://github.com/uasir/CTA-FPL-Model/actions/runs/44932689482), 549 tests passed, 3 subtests passed, and all four identity-crosswalk validators passed. The subsequent provenance-hardening change is under CI validation; do not treat it as verified until its run completes.

- Bounded live Onside covariance capture completed 21 Nov 2026 at 17:58:17Z in run [#44932906400](https://github.com/uasir/CTA-FPL-Model/actions/runs/44932906400), artifact `cta-onside-covariance-44932906400`. It used realized actual points only for completed GW1–GW10; GW11 and GW12 were excluded as unfinished. The source SHA-256 is `f762b7c380758f7a282fa2ac82c6d27ae1b7801df1c6cb89861a1c5c0a1afc48`. The window contained 605 players, 350 complete-panel players, 296 non-zero-variance covariance players, 255 incomplete-panel exclusions and 54 zero-variance exclusions. The covariance report explicitly marks `point_in_time_status: NOT_VERIFIED`.
- The split-window stability diagnostic is a strong caution: correlation-of-correlations between GW1–GW5 and GW6–GW10 was `0.00779916`, with median absolute pairwise correlation change `0.50044957` (mean `0.5779996`). This is not a formal stationarity test, but it provides no evidence that the estimated player dependence is stable across the season's first ten Gameweeks. Treat this artifact as a research fixture and integration test only; do not use it to rank live transfers or make field-relative claims. Keep CoVar decision weight at zero and production eligibility false.
- The one-shot feature-branch trigger and marker were removed after capture; the workflow is back to its normal scheduled/manual triggers. No recurring capture was added.
