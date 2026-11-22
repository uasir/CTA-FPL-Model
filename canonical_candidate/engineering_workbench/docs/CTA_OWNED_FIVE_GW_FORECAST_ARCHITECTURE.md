# CTA-Owned Five-Gameweek Forecast Engine — Audit and Architecture Decision

**Status:** Engineering direction approved; implementation not yet production-ready  
**Scope:** M4 conventional forecast foundation  
**Decision:** CTA-FPL owns the primary five-Gameweek forecast pipeline. Import Dastan's released expected-minutes component as the minutes model; CTA retains ownership of the feature/data adapter, fixture-level points model, forecast snapshots, and validation. No paid forecast provider is a required runtime dependency.

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

- MIT-licensed code and published model weights; retain the MIT copyright and licence notice when importing code or substantial portions.
- Six-season training frame described as 163,072 player-fixture rows and 286 features.
- The released predictor returns `p60`, `p_any`, and `expected_minutes`. The minutes output is derived by applying the packaged, position-specific `minutes_calibration.json` curve to the position-specific `p60` classifier.
- The minutes component is separable from Dastan's points heads: CTA needs the four `p60_{GKP,DEF,MID,FWD}` model artifacts, the minutes calibration curves, the ordered 286-feature contract, and the small inference adapter. CTA will not import Dastan's `xpts`, bucket, or direct-points heads as its primary points model.
- Dastan's reported minutes/availability evaluation and point forecasts are model-reported evidence, not independent CTA validation. Its headline objective is a ranking score, not a literal forecast-accuracy percentage.

**Adoption decision — minutes only:** Import Dastan's released minutes predictor as CTA's initial minutes component. Do not build a competing minutes model in parallel at this stage. Preserve the upstream model version, commit, artifact hashes, MIT attribution, and calibration metadata. CTA must provide a compatible feature frame and validate the model on its own deadline-safe evaluation windows before production use.

Important integration constraints:

- The `p60` heads require Dastan's exact ordered 286-feature input contract. CTA's current lagged builder does not produce that schema, so a compatibility feature adapter is a prerequisite; never pass CTA's smaller feature frame directly to the released weights.
- The released model was trained through 2025-26 GW30. Its current-roster mapping manifest is dated 2026-09-07 and reports 52 unmapped players and one shared Understat ID; refresh and audit current-season mappings before relying on any Understat-derived feature.
- The training frame combines FPL, Understat, and OpenFPL-derived features. MIT licensing of the code and weights does not grant rights to upstream source data. Review upstream terms, attribution, redistribution and operational access independently; do not redistribute restricted raw data.
- Missing features must follow Dastan's documented missing-value convention and exact column order. Do not silently substitute zeros for missing source observations unless that is the upstream model's defined inference behavior.
- The released minutes calibration is fitted on a 2025-26 GW31-38 packaging holdout. Preserve that fact in provenance and test calibration drift on current-season data; do not present it as a newly calibrated CTA model.
- Dastan's 2026-27 roster mapping is not itself proof that every active player can be scored. Report unmapped/missing-feature coverage explicitly and fail closed for unsupported rows.

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

1. **Expected minutes / appearance probabilities:** Dastan `p60` classifier plus its packaged calibration curve, exposed as `expected_minutes`, `p60`, and `p_any`.
2. **Conditional points production:** CTA-owned fixture-level points model using minutes as an input, with opponent, venue and fixture context.
3. **Combined fixture expected points:** CTA-owned combination of expected minutes and conditional production, with coherent uncertainty outputs only where calibrated and empirically supported.

Do not train a parallel CTA minutes model unless Dastan integration fails a predeclared validation or coverage gate. Keep a transparent recent-form and official-`ep_next` benchmark where point-in-time coverage permits.

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
3. Build the Dastan compatibility adapter: refresh player identity mappings; reproduce the ordered 286-feature input contract with deadline-safe sources; import only the four `p60` heads and minutes calibration; record upstream commit and artifact hashes.
4. Validate Dastan expected-minutes outputs against CTA's chronological, deadline-aware holdouts, including calibration, player coverage, positions and double-GW invariance. Keep the current CTA minutes heuristic as a benchmark only.
5. Build CTA's fixture-level conditional points model and combine it with the imported minutes output; then add the five-GW snapshot builder and completeness/provenance validator.
6. Run chronological backtests and challenger comparisons; keep the product exploratory until it passes the gates above.

**Non-goal:** This decision does not import Dastan's points model or require FPL Cat. Importing Dastan's minutes component is approved as an engineering direction, not a claim that it is already integrated, validated, or production-approved. This document does not authorize merging existing PRs.
