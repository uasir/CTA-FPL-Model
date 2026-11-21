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
- Existing capture preserves raw provider and official FPL bootstrap payloads, hashes, capture times, provider-declared `computed_at`, expected points and expected minutes.
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
- The manual capture workflow now runs the parser after raw capture. A target Gameweek must be supplied explicitly; there is no stale default to a Gameweek whose deadline has passed.
- Engineering tests have been added for raw capture, fixture parser, double-Gameweek sum, native-field retention, identity mapping, duplicate keys and invalid Gameweek data. The M3 feature-branch CI run at commit `6427d3351d37d9715ca8d30219f7d678becc78fb` passed the full engineering test suite (433 tests and 3 subtests). This verifies software behavior, not forecast accuracy.

### FPLRogue — source verified

- Research page: `https://www.fplrogue.com/research/projections`
- Current CSV link: `https://www.fplrogue.com/research/projections.csv`
- Page identifies the current accepted release, target Gameweek, player count, projection engine (`xpts_v1`), update time and model-training time.
- Page exposes xPts, xMins, floor/ceiling and start probability, and states that floor/ceiling are indicative display ranges rather than calibrated probability intervals.
- Implemented first-stage accepted-release capture: archives the HTML page, CSV and official FPL bootstrap with independent SHA-256 hashes; records the exact CSV headers and row count; and cross-checks page Gameweek, player count and official deadline.
- The page's `Updated` timestamp and `Model trained` timestamp are retained separately. Because the page does not explicitly define `Updated` as the forecast-generation timestamp, the capture leaves canonical `generated_at_utc` unset and is diagnostic-only for strict point-in-time decision use until the provider's timestamp semantics are verified.
- Added a manual capture workflow and tests for page metadata, CSV shape, hashes, row-count checks and post-deadline rejection. The same M3 feature-branch CI run passed the full engineering test suite (433 tests and 3 subtests). This does not mean a live provider capture has yet been executed.
- CSV column mapping and canonical normalization remain pending inspection of an actual captured CSV payload.
- Attribution: FPLRogue. The source states it is independent and not affiliated with the Premier League.

### FPL Lucho — source verified

- Forecast page: `https://fpllucho.pythonanywhere.com/forecast`
- Current CSV link: `https://fpllucho.pythonanywhere.com/export/predictions.csv`
- The CSV export covers every player, xP and fixtures for the next four Gameweeks.
- The served forecast is odds-anchored xP. Since GW9, the site says the served values use a bookmaker-odds / archived-odds / fallback ladder for team goals, while minutes and player allocation remain model-derived.
- Preserve the product variant as **served odds-anchored xP**. Do not silently substitute the raw model xP or relabel it as the separately reported Odds xP performance series.
- The page reports an xP model calculation timestamp separately from the page build timestamp. The capture adapter must identify and retain the authoritative forecast-generation timestamp and its scope; if it cannot verify it from the exported payload/source metadata, mark the snapshot diagnostic-only.
- CSV content and exact column names must be verified from the downloaded raw payload before mapping.

### FPL Wildcard — source verified

- Projection dataset page: `https://fplwildcard.com/data/projections/`
- Current CSV link: `https://fplwildcard.com/data/projections/current.csv`
- Published grain: one row per selectable player in one projected Gameweek.
- Displayed forecast field: `xpts`; minutes: `xmins`; optional start, appearance, sixty-plus, blank and haul probabilities.
- Page exposes model version and projection update time; the adapter must preserve these values and their timestamp provenance.
- The site states that no redistribution licence is granted. **FPL Wildcard remains an active fifth provider; lack of redistribution permission is not a reason to drop it.** Do not republish raw rows, redistribute provider data, or place its raw/derived provider values in public repository files, public CI logs, or public workflow artifacts.
- Use a compliant acquisition route: prefer a user-initiated download or other provider-permitted access, then process the file in private, access-controlled project storage. Do not automate scraping or repeated downloads unless the provider's terms or written permission clearly allow that access method. If automated retrieval is not permitted, keep the provider active through the manual/private intake path rather than excluding it.
- Keep provider-specific values private and use only outputs/aggregates that are permitted for internal decision support. Re-check the applicable terms before any external display or sharing.
- CSV content and exact column names must be verified from the downloaded raw payload before mapping. The current public page documents the schema, but the live CSV bytes have not yet been inspected.

## 4. Provider-specific implementation gates

A provider is not marked integrated merely because its URL is known. Each adapter must pass:

1. Successful retrieval with HTTP status, content type, source URL and retrieval timestamp recorded.
2. Raw response retention in an access-controlled artifact and SHA-256 verification.
3. Exact schema/column verification against the actual downloaded payload.
4. Provider identity, product/variant and target Gameweek verification.
5. Provider-generation timestamp provenance and strict deadline eligibility handling.
6. FPL element identity mapping and duplicate/coverage checks.
7. Canonical contract normalization with source grain preserved.
8. Deterministic parser tests using captured, sanitized fixtures that respect source terms.
9. A provider-specific capture workflow or an explicitly documented compliant manual/private intake route where automation is not permitted. Restricted sources must not be forced into public artifact storage just to satisfy automation parity.

Do not create synthetic forecasts to fill gaps. A provider with unresolved access, terms or schema remains explicitly blocked/pending rather than being represented as integrated.

## 5. Evaluation boundary

The five providers are integrated as independent forecast sources. Formal provider-by-provider performance evaluation is deferred until the upcoming Gameweek's official scores are available. When evaluation begins, compare providers on matched player/Gameweek populations and common outcome/finality evidence, while retaining provider-specific native fields and separate scorecards. Do not infer that one provider is superior from unmatched coverage or a single Gameweek.

M4 recommendation-product performance evaluation is also deferred until the upcoming Gameweek's official scores. These evaluation deferrals do not stop independent M3 adapter and decision-engine engineering.
