# CTA-Owned Five-Gameweek Forecast Engine — Audit and Architecture Decision

**Status:** Engineering direction approved; implementation not yet production-ready  
**Scope:** M4 conventional forecast foundation  
**Decision:** CTA-FPL owns the primary five-Gameweek forecast pipeline. External forecasts are benchmarks or optional fallbacks, never a required long-term runtime dependency.

## 1. Objective

Produce a reproducible, point-in-time, fixture-grain forecast for every eligible player across the next five consecutive Gameweeks. Each forecast row must identify its fixture, player, target Gameweek, deadline snapshot, source lineage, feature/model version, expected points, and forecast quality state.

For a player with multiple fixtures in one Gameweek, forecast each fixture separately using the same pre-deadline information snapshot, then aggregate fixture expectations to the player-Gameweek level. Do not split an aggregate Gameweek forecast into invented fixture values.

The five-GW panel is an input to M4's HOLD-versus-TRANSFER comparison. It does not by itself authorize transfer decisions, CoVar influence, or changes to frozen conventional recommendations.

## 2. CTA repository audit

Existing foundations found on `main`:

- `build_fpl_lagged_features.py` builds player-fixture rows from official FPL history and fixtures. It uses earlier Gameweeks only, checks target kickoffs against the target deadline, and shares one pre-deadline feature snapshot across a player's double-GW fixtures.
- `build_fpl_baseline_forecast_snapshot.py` creates a provenance-hashed one-GW exploratory baseline using official `ep_next`, fixture counts, and a latest-GW minutes proxy.
- The baseline explicitly labels itself exploratory, one-GW only, and not a CTA-trained predictive model. Its minutes proxy is not a trained minutes forecast.
- Existing tests cover point-in-time checks, source hashes, EO provenance, and the one-GW baseline.

Limitations to resolve before production:

1. The current baseline is one Gameweek and relies on official `ep_next`; it cannot satisfy the five-GW contract.
2. The current minutes proxy is a last-GW scaling heuristic, not a probability-calibrated availability/minutes model.
3. The lagged feature builder is a useful starting point, but its current feature set is much smaller than Dastan's and needs a formal schema, historical-source audit, and stronger rolling backtests.
4. Historical rows and current snapshots must have explicit point-in-time provenance. A current API response must never be treated as a historical pre-deadline snapshot.
5. Cross-season identity must use stable player codes with season-scoped FPL element IDs; never join careers on element ID alone.
6. Fixture-level expectations and player-Gameweek evaluation are distinct grains. Both must be retained and tested.

## 3. Dastan audit

Repository: https://github.com/qazybekb/smartplayfpl-dastan

Useful properties observed:

- MIT-licensed code and published model weights.
- Six-season training frame described as 163,072 player-fixture rows and 286 features.
- Published inference separates minutes/availability signals from points prediction and exposes scoring-band probabilities.
- Evaluation is deadline-anchored, chronological, per-Gameweek, and reports both all-player and 60+-minute cohorts.
- The methodology documents seed noise, multiple-comparison risk, leakage failures, and rejected feature families. This is a strong evaluation reference.

Reasons not to adopt it as the CTA production engine unchanged:

- Its model expects its exact 286-feature schema. CTA's current lagged builder does not produce that schema; the released weights cannot simply be pointed at CTA's current rows.
- The published model was trained through 2025-26 GW30. Its current-roster mapping manifest is dated 2026-09-07 and reports 52 unmapped players and one shared Understat ID; mappings need refresh and audit before current-season use.
- Its training frame combines FPL, Understat, and OpenFPL-derived features. The repository's MIT statement does not remove the need to review upstream source terms, attribution, redistribution, and operational data access independently.
- Its public accuracy figures are model-reported evidence, not independent CTA validation. The headline objective is a ranking score, not a literal forecast-accuracy percentage.

**Decision:** Use Dastan as a challenger/benchmark and a source of evaluation lessons. Do not make its model weights, 286-feature frame, or third-party data pipeline a runtime dependency. Reimplement only feature ideas that pass CTA's own provenance, usefulness, and validation tests.

## 4. Forecast architecture

### A. Data and identity layer

- Official FPL bootstrap, fixtures, player history, and event deadlines are the current-season core.
- Historical training sources must be pinned by source, revision/date, licence/terms, retrieval timestamp, and file hash.
- Preserve raw immutable snapshots and normalized tables separately.
- Use stable player code for cross-season identity; preserve season-specific element IDs as source identifiers.
- Keep fixture identity, team-at-fixture, opponent, venue, kickoff, and deadline explicit.
- Reject incomplete or ambiguous player/fixture joins rather than guessing.

### B. Point-in-time feature layer

- Build one feature vector per player-fixture, anchored to the target Gameweek deadline.
- All fixtures in the same player-Gameweek must share the same historical player/team state; fixture-specific opponent and venue context may differ.
- Feature families should begin with lagged FPL minutes, starts, points, goals, assists, xG/xA/xGI, BPS/bonus and defensive contribution; team/opponent form; venue; price; and verified pre-deadline availability.
- Missing data must remain distinguishable from genuine zero values.
- Exclude target-fixture outcomes and any post-deadline information.
- Treat official `ep_next` as a benchmark/input only when an archived pre-deadline vintage proves it was available at that deadline.

### C. Forecast model

Build and validate separate components:

1. Expected minutes / appearance probabilities.
2. Conditional points production given appearance/minutes, with fixture context.
3. Combined fixture expected points, with coherent uncertainty outputs only where calibrated and empirically supported.

A transparent statistical/gradient-boosted baseline should be established before adding complex model families. Keep a simple recent-form and official-`ep_next` benchmark where point-in-time coverage permits.

### D. Five-GW panel and snapshot

- Enumerate the next five consecutive Gameweeks from the official event/fixture schedule.
- Include every fixture, including blanks and double Gameweeks.
- Preserve fixture-grain rows and provide a player-Gameweek aggregation view.
- Store `forecast_snapshot_id`, `as_of_utc`, target deadline, source hashes, feature schema version, model version, and validation status.
- Do not silently carry a one-GW forecast forward or multiply a one-GW number across future Gameweeks.
- If the full five-GW panel is incomplete, mark it blocked/incomplete rather than fabricating coverage.

## 5. Validation gates

Before M4 production use:

- Chronological, deadline-aware rolling-origin backtests; no random train/test split.
- Same eligible rows and same scoring windows for every baseline comparison.
- Metrics by Gameweek, plus all-player and 60+-minute cohorts; report MAE/RMSE and ranking/top-10 metrics separately.
- Minutes/availability calibration and points calibration, not ranking alone.
- Double-GW leakage tests proving same-deadline history is shared across fixtures.
- Explicit coverage, missingness, stale-source, identity, and fixture-completeness reports.
- Compare against simple FPL baselines and Dastan where reproducible, source-compliant inputs exist.
- Record model/feature changes and require independent confirmation windows for feature promotion.

## 6. M4 and CoVar safeguards

- The five-GW forecast supplies expected points for conventional HOLD-versus-TRANSFER analysis.
- Transfer comparisons must use the same five-GW horizon, include hit/transfer costs and opportunity cost, and distinguish genuine cumulative value from points merely shifted between weeks.
- This forecast work does not validate CoVar.
- Do not infer player covariance from marginal expected points, club membership, or ownership. CoVar remains unavailable unless genuine paired joint player-point scenarios are built and validated.
- Do not let unvalidated CoVar alter EV, transfer logic, conventional rankings, XI, captaincy, or hits.

## 7. Immediate implementation sequence

1. Freeze this architecture and inventory the existing FPL ingestion artifacts, historical row schemas, source pins, and tests.
2. Define a versioned CTA player-fixture training/inference schema that can produce all five target Gameweeks from a single as-of snapshot.
3. Expand the existing lagged feature builder with tested, leakage-safe rolling features and stable cross-season identity.
4. Build transparent minutes and points baselines, then a trained fixture-level model.
5. Add a five-GW snapshot builder and completeness/provenance validator.
6. Run chronological backtests and challenger comparisons; keep the product exploratory until it passes the gates above.

**Non-goal:** This document does not adopt FPL Cat, Dastan, or any other external provider as the required production forecast source, and it does not authorize merging existing PRs.
