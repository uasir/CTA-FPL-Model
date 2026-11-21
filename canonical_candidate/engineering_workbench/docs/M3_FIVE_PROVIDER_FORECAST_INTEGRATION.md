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
- The canonical snapshot remains at player-fixture grain. A separate derived player-Gameweek view explicitly sums fixture `xP` by `player_id`, with fixture count and aggregation provenance. It does not aggregate start probabilities, sigma or other distribution fields.
- The manual capture workflow now runs the parser after raw capture. A target Gameweek must be supplied explicitly; there is no stale default to a Gameweek whose deadline has passed. The workflow publishes only a sanitized metadata summary; raw provider rows and the official FPL bootstrap are not uploaded to the public repository's workflow artifacts.
- Engineering tests have been added for raw capture, fixture parser, double-Gameweek sum, native-field retention, identity mapping, duplicate keys and invalid Gameweek data. The M3 feature-branch CI run at commit `6427d3351d37d9715ca8d30219f7d678becc78fb` passed the full engineering test suite (433 tests and 3 subtests). This verifies software behavior, not forecast accuracy.

### FPLRogue — source verified

- Research page: `https://www.fplrogue.com/research/projections`
- Current CSV link: `https://www.fplrogue.com/research/projections.csv`
- Page identifies the current accepted release, target Gameweek, player count, projection engine (`xpts_v1`), update time and model-training time.
- Page exposes xPts, xMins, floor/ceiling and start probability, and states that floor/ceiling are indicative display ranges rather than calibrated probability intervals.
- Implemented first-stage accepted-release capture: archives the HTML page, CSV and official FPL bootstrap with independent SHA-256 hashes; records the exact CSV headers and row count; and cross-checks page Gameweek, player count and official deadline.
- The page's `Updated` timestamp and `Model trained` timestamp are retained separately. Because the page does not explicitly define `Updated` as the forecast-generation timestamp, the capture leaves canonical `generated_at_utc` unset and is diagnostic-only for strict point-in-time decision use until the provider's timestamp semantics are verified.
- Added a manual capture workflow and tests for page metadata, CSV shape, hashes, row-count checks and post-deadline rejection. The workflow publishes only a sanitized metadata/schema summary, never CSV forecast rows or raw page/bootstrap payloads. The same M3 feature-branch CI run passed the full engineering test suite (433 tests and 3 subtests). This does not mean a live provider capture has yet been executed.
- CSV column mapping and canonical normalization remain pending inspection of an actual captured CSV payload.
- Attribution: FPLRogue. The source states it is independent and not affiliated with the Premier League.

### FPL Lucho — source verified

- Forecast page: `https://fpllucho.pythonanywhere.com/forecast`
- Current CSV link: `https://fpllucho.pythonanywhere.com/export/predictions.csv`
- The CSV export covers every player, xP and fixtures for the next four Gameweeks.
- The page reports an xP model calculation timestamp separately from the page build timestamp. A first-stage raw intake script now captures the page, CSV and official FPL bootstrap, preserving exact CSV bytes, headers and SHA-256 while recording page-build and raw-model calculation timestamps separately.
- The CSV export URL is verified from the live page's download link, but the actual CSV response remains unavailable to the current web reader (`text/csv`). Exact headers and values must be inspected from a permitted downloaded payload before mapping; no guessed column mapping is present.
- The served product is explicitly **odds-anchored xP**. Keep it distinct from raw model xP and the separately reported Odds xP series. The raw-model calculation time is not treated as the generation time of the served odds-anchored CSV; `generated_at_utc` remains null and strict point-in-time eligibility is withheld until the served forecast's timestamp semantics are established.
- Synthetic fixture tests cover timestamp provenance, raw-byte preservation, schema inspection, target Gameweek and deadline rejection. No live Lucho CSV capture or normalization has yet been verified. The capture script is a one-shot intake utility; it does not add a scheduled workflow or publish provider data as a GitHub artifact. Keep resulting payloads in private, access-controlled storage and do not commit them.

### FPL Wildcard — source verified

- Projection dataset page: `https://fplwildcard.com/data/projections/`
- Current CSV link: `https://fplwildcard.com/data/projections/current.csv`
- Published grain: one row per selectable player in one projected Gameweek.
- Displayed forecast field: `xpts`; minutes: `xmins`; optional start, appearance, sixty-plus, blank and haul probabilities.
- Page exposes model version and projection update time; the adapter must preserve these values and their timestamp provenance.
- The site states that no redistribution licence is granted. **FPL Wildcard remains an active fifth provider; lack of redistribution permission is not a reason to drop it.** Do not republish raw rows, redistribute provider data, or place its raw/derived provider values in public repository files, public CI logs, or public workflow artifacts.
- Use a compliant acquisition route: prefer a user-initiated download or other provider-permitted access, then process the file in private, access-controlled project storage. Do not automate scraping or repeated downloads unless the provider's terms or written permission clearly allow that access method. If automated retrieval is not permitted, keep the provider active through the manual/private intake path rather than excluding it.
- Keep provider-specific values private and use only outputs/aggregates that are permitted for internal decision support. Re-check the applicable terms before any external display or sharing.
- A local/private parser has been added against the page's documented CSV schema. It verifies required/optional headers, target Gameweek, SHA-256, exact player-plus-club identity mapping against official FPL bootstrap data, duplicates and numeric/probability ranges; it preserves all original CSV rows separately and leaves provider generation time unset.
- The parser's synthetic-fixture tests pass in CI (included in the 437 passing tests on the M3 feature branch). This verifies parser logic only: the live CSV bytes and exact headers have not yet been inspected, and no live Wildcard capture has been performed.

## 4. Current engineering verification

- M3 feature-branch CI at commit `573b0bcca3c8543b72319f745b943b373f4de5ae` completed successfully: **437 tests passed, 3 subtests passed**.
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
