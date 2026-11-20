# External FPL benchmark coverage and capture feasibility audit

Date: 2026-11-20  
Status: **M2 IN PROGRESS — CAPTURE INFRASTRUCTURE PARTLY IMPLEMENTED — NO BENCHMARK PROMOTION**

## Scope and decision rule

This audit distinguishes (a) the approved external FPL benchmark providers, (b) actual captured observations, and (c) sources that are merely visible or documented. A website, forecast page, scorecard, or collector implementation is not itself a valid benchmark observation.

The original comparison set remains FPL Review (Free and Premium/Massive Data as separate variants), FPL Forecaster, FPL Lucho (served xP and Odds xP as separate variants), Sideline Quant, FPL Cat, FPLRogue, and FPL Wildcard. FPL Wildcard is subject to its source-specific non-redistribution and retention restrictions. Official FPL ep_next remains a native reference, not an independent provider. evmax is recorded as a subsequently verified additional provider, not a replacement for the approved market-derived sources.

## Provider coverage matrix

| Provider / variant | Verified output and grain | Point-in-time / archive evidence | Current eligibility |
|---|---|---|---|
| FPL Cat published xP | Public JSON/CSV API; player-GW rows with official FPL player ID, xP, gameweek, deadline and computed_at | API documentation permits research benchmarking with attribution. Included in the lifecycle collector; generated timestamp is required by lifecycle validation. | **Capture candidate / strict timestamp candidate.** Need verified lifecycle captures and complete per-GW archive ledger. |
| Sideline Quant published xP | GW-specific JSON; player-fixture rows, FPL player/fixture IDs, xP and probability/distribution fields | GW11 output reported 672 fixture rows, generated_at and 10,000 simulations. Included in collector. Preserve fixture grain; aggregate only under a declared rule. | **Capture candidate.** Need verified archived lifecycle captures, coverage and strict per-source timestamp validation. |
| FPLRogue accepted xPts | Published accepted CSV; player-GW rows, player_id, next_gw_xpts, gameweek, captured_at and model_version | Current GW11 CSV was reported as 672 rows with a provider capture timestamp; included in collector. | **Capture candidate.** Validate provider timestamp values against deadline and verify archived per-GW releases. Keep model versions separate. |
| FPL Lucho served xP | Published all-player CSV; player ID and per-GW xp column | Collector captures served xP. Export does not disclose a generation timestamp. | **Unverified-timestamp cohort only** until provider generation time can be established. Do not label as Odds xP. |
| FPL Lucho Odds xP | Performance page exposes a distinct series | No player-level export/capture path verified. | **Not captured / not eligible.** Do not infer from served xP CSV. |
| FPL Forecaster | Public player-level pages and individual expected-points outputs; page lists 672 projected players over GW11–15 | No complete bulk CSV/API capture path verified. | **Visible, not machine-capturable yet.** Remains a priority market-derived benchmark blocker. |
| FPL Review Free | Provider documentation describes free product | No verified player-level pre-deadline export for Free in this audit. | **Not yet eligible.** Keep distinct from Premium. |
| FPL Review Premium / Massive Data | Documented CSV export with FPL ID, EV and xMins | Access is Premium; no archived project capture verified in this audit. | **Access-dependent candidate.** No benchmark observation claimed. |
| FPL Wildcard published xPts | Published player-GW CSV with xPts/xMins and optional probabilities | Private GW11 capture: 566 rows, 566 identities resolved, captured before deadline; private archive also records GW1–10 frozen top-50 pages (500 rows, 497 resolved). No redistribution licence; historical pages are selected top-50, not full-player coverage. | **Private research capture exists.** GW11 full-player cohort is eligible for post-deadline scoring subject to retention/terms review; GW1–10 top-50 cohort is conditional-only and must be compared on identical selected rows. |
| evmax published xPoints | Full-player forecasts with official FPL IDs and distributions | Private archive captures GW4–GW7: 2,648 rows, all IDs resolved, provider-generated timestamps and hashes. Provider states forecasts frozen before deadline and data CC BY 4.0. | **Strong additional external benchmark.** Captured evidence exists; scoring was reproduced against provider scorecard. Not one of the originally named providers and does not replace FPL Forecaster/Lucho. |
| Football Meets Data Fantasy Forecasts | Public accuracy page describes pre-deadline forecasts; GW11 cohort shown as 514 predictions | Complete downloadable/retrievable player-level frozen snapshot not verified. | **Not yet eligible.** |
| FPL Vault xPts | Public xPts table/export; 459 players visible | Complete player-GW timestamped frozen capture not verified. | **Not yet eligible.** |
| FPL Form | Documentation describes CSV predicted-points export and appearance probabilities | Account/access, timestamp, complete coverage and immutable archive not verified. | **Not yet eligible.** |
| Official FPL ep_next | Official API native expected-points reference | Current snapshots can be captured prospectively; historical pre-deadline vintages cannot be reconstructed reliably. | **Native reference only**, not an independent provider. |

## Implemented capture infrastructure

Public model repository:
- `scripts/capture_external_fpl_forecasts.py` captures FPL Cat, Sideline Quant, FPLRogue and FPL Lucho served-xP raw outputs.
- It retains raw response bytes, hashes, retrieval metadata, row counts, grain and explicit variant labels.
- The public workflow was corrected to publish only a non-player-level manifest; raw third-party forecasts must not be uploaded as public artifacts.
- FPL Wildcard is excluded from the public capture workflow and is handled separately in the private archive.

Private archive:
- `scripts/capture_forecast_lifecycle.py` wraps the pinned collector with gameweek discovery, pre-deadline checks, immutable timestamped captures, hash-based change detection and a poll log.
- The lifecycle contract distinguishes provider generation time from archive capture time. FPL Lucho served xP is explicitly marked as having no disclosed generation timestamp.
- The lifecycle protocol defines T-7d, T-72h and T-24h checkpoints plus a latest-valid-before-deadline view. The checkpoint selector and common-cohort scoring remain outstanding.

## Reliability defect found and corrected

The private lifecycle protocol claimed a three-hour polling schedule, but the actual workflow file had only manual and push triggers. On 2026-11-20 the workflow was updated in commit `fe81c27b898b5248c3d7cba5df3d54eb81c36be3` to add a UTC cron trigger at minute 17 every three hours.

**This is a configuration correction, not proof that scheduled capture is now operational.** A successful scheduled run and resulting poll-log entry must be verified before the recurring process is marked active.

## Validation gaps requiring closure

1. The lifecycle wrapper currently requires the FPL Cat generated timestamp to precede the deadline, but does not apply the same explicit generation-time check to every provider.
2. FPLRogue's row-level `captured_at` values are recorded as metadata but are not yet enforced as pre-deadline timestamps.
3. FPL Lucho served xP has no disclosed generation timestamp; capture time alone cannot prove when the provider generated the forecast. Keep it outside the strict point-in-time cohort unless additional provider evidence is obtained.
4. CSV schema checks currently establish required columns and target gameweek for some sources, but need explicit duplicate-player, numeric forecast, null/missingness, and complete-universe checks before normalized scoring.
5. Sideline Quant is fixture-grain. Any player-GW score must use a declared fixture aggregation and retain the original fixture rows.
6. The private archive's FPL Wildcard historical top-50 subset must never be compared as if it were an all-player cohort.
7. The public collector's ephemeral runner and 90-day manifest retention are not durable raw retention. Restricted raw data must remain in the approved private archive, with provider-specific terms reviewed.

## Next M2 engineering sequence

1. Verify the new scheduled workflow actually runs and writes a poll-log record; do not infer success from the YAML change.
2. Strengthen provider-specific timestamp, schema, duplicate, numeric and coverage validation; add tests for every failure mode.
3. Produce a provider-by-GW immutable capture ledger containing source variant, generation timestamp disclosure, capture time, deadline, raw hash, row count, grain, identity coverage, retention location and eligibility state.
4. Implement T-7d/T-72h/T-24h and best-available-before-deadline snapshot selection.
5. Normalize provider outputs only after preserving raw snapshots; keep fixture-grain and player-GW data typed.
6. Join official actuals only after the event is finished and produce common-cohort point-error, deadline-local ranking and probabilistic scorecards.
7. Keep CTA/2PM research-only until the external benchmark comparisons, point-in-time validation, multi-season robustness and rights gates are satisfied.

## Decision

External benchmark capture is **partly implemented**, not complete. evmax and FPL Wildcard have concrete private capture evidence with different cohort/rights qualifications. FPL Cat, Sideline Quant and FPLRogue have defined capture surfaces and collector support but still require verified lifecycle-ledger evidence. FPL Lucho served xP is timestamp-unverified; its Odds xP variant is not captured. FPL Forecaster and FPL Review remain important unresolved approved-provider access paths.

No external benchmark winner, production forecast weight, or model promotion is claimed by this audit.


## Collector validation hardening — 20 November 2026

The public capture collector was strengthened in commits `eeb3929f24f076806f6c26d1c8218ddb9172c9cf` and `eb14e3353d23f5155d9c4d3b760cde1bcc400cfa`:

- Enforces timezone-aware provider timestamps and checks FPL Cat and Sideline Quant generation times plus FPLRogue's provider-reported captured_at against the official deadline.
- Checks unique player IDs for player-GW CSV/JSON outputs and unique player-fixture keys for Sideline Quant.
- Checks numeric finite expected-points values, provider row/player counts, FPLRogue timestamp/version consistency, and the FPL Cat deadline field.
- Explicitly labels FPL Lucho served xP as timestamp-unverified rather than treating collector retrieval time as provider generation time.
- Adds regression tests for duplicate IDs, non-finite forecasts, timezone-less timestamps, row-count mismatches and post-deadline provider timestamps.

CI run [44749895158](https://github.com/uasir/CTA-FPL-Model/actions/runs/44749895158) completed successfully. The private archive lifecycle workflow was then pinned to the validated public collector commit `eb14e3353d23f5155d9c4d3b760cde1bcc400cfa` in private commit `b58334f82b12f856bbc66ddfb2799a57a9e2eb90`.

The schedule is now configured and the collector is validated in CI. **A successful scheduled private-archive run and a new poll-log record are still required before declaring recurring capture operational.**
