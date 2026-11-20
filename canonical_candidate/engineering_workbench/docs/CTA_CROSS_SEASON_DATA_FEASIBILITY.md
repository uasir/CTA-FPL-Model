# CTA Cross-Season Data Feasibility Assessment

**Milestone:** M2 — Model layer  
**Status:** FEASIBILITY AUDIT / NO MULTI-SEASON CTA PROMOTION  
**Assessment date:** 2026-11-20  
**Purpose:** Determine whether the current event-data and identity sources support defensible multi-season CTA/ABC validation, and specify what must change before cross-season claims are made.

## 1. Executive decision

**Current decision: a defensible multi-season CTA-to-FPL panel is not yet available.**

The repository contains:
- a research-eligible, verified Wyscout/11footy/FPL identity cohort for 2017/18;
- a current-season 11footy-to-FPL identity panel for 2026/27;
- a current-season Opta/PulseLive technical identity bridge, but not player-level match event metrics;
- multi-season conventional FPL history, but not a multi-season CTA event panel and not verified historical deadline-time vintages.

These sources do not currently form a continuous, verified CTA panel across seasons. The 2017/18 and 2026/27 endpoints cannot be treated as a multi-season time series merely because both contain player identities. The intervening seasons, season-scoped identity continuity, event-feature availability, historical FPL target rights and point-in-time provenance remain unresolved.

Therefore:
- retain the completed 2017/18 ABC/2PM matched experiment as a restricted single-season research result;
- keep CTA/ABC at `RESEARCH_ONLY / DO_NOT_PROMOTE` and zero recommendation weight;
- do not claim cross-season CTA generalization;
- continue to compare ABC/CTA and 2PM against the agreed external FPL benchmark providers on exact common player-GW cohorts, independently of this CTA-source feasibility work;
- use the 2026/27 prospective pipeline to accumulate future deadline-frozen observations, provided source terms and retention permissions permit it.

## 2. Evidence inventory

| Source / season | What is evidenced | What is not established | Current use decision |
|---|---|---|---|
| Wyscout EPL 2017/18 | Public event release; 380/380 fixtures mapped; 91 strict Wyscout–11footy–FPL identities verified; 2,693 verified player-fixture rows in the strict panel. Wyscout source items display CC BY 4.0. | No second Wyscout EPL season is currently integrated. Historical FPL target-data reuse rights are unresolved. Exact historical pre-deadline source vintages are unavailable. | Restricted 2017/18 research only. |
| 11footy historical EPL 2017/18 | 602 canonical provider players; 12,291 player-match rows joined to historical FPL fixture history; candidate identity evidence. | Historical candidate mappings are not independently verified by that process; retrospective FPL data is used for identity corroboration, not PIT prediction training. | Identity research only; do not treat all candidate rows as verified. |
| 11footy current EPL 2026/27 | Current-season match history; 416 exact identities verified against current FPL in the latest integration report; 3,011 verified player-match rows; 100/100 provider matches mapped to FPL fixtures. | Does not bridge the missing seasons. Current source snapshot is not a historical archive. 11footy is labelled CC BY-NC 4.0; use and retention must respect its non-commercial terms. | Prospective current-season research only, with provenance and retention controls. |
| 11footy cross-season identity corroboration | 49 canonical 11footy IDs overlap between the historical 2017/18 catalogue and current 2026/27 candidates; 30 are P1 review candidates. | These 30 are not verified identities; only candidate-level corroboration exists. | Manual-review queue only; no automatic promotion to verified cross-season identity. |
| Opta/PulseLive 2026/27 | 511 shared numeric player IDs and matching team IDs in the inspected season snapshot; a separate provider namespace. | No player-level per-match event metrics in the inspected repository snapshot; cumulative season files are not archived deadline vintages; underlying data rights unresolved. | Team/context research only if permissions and PIT controls are resolved; not a player-level CTA substitute. |
| StatsBomb | Existing CTA engine and provider-specific event schema; a Bundesliga pilot. | Canonical StatsBomb-to-FPL crosswalk is empty; no verified EPL player-match CTA training panel established. | Keep separate; no inferred ID equivalence or EPL CTA coverage claim. |
| Conventional FPL history, 2016/17–2025/26 | Multi-season player-fixture history can support conventional FPL model research. | It is not event-derived CTA data. Historical exports are retrospective and not proven to be exact pre-deadline vintages; underlying data rights remain distinct from repository code licence. | Conventional model input/research, not evidence of multi-season CTA coverage. |

## 3. Identity continuity is not the same as feature continuity

A provider ID appearing in two seasons is useful identity evidence, but it does not by itself establish:
- that the same player identity has been independently verified in each season;
- that the provider recorded the same event fields and definitions in each season;
- that the player had sufficient match coverage in each season;
- that the provider's event records were available before the relevant FPL deadline;
- that the corresponding FPL target data can lawfully be used;
- or that a model can be evaluated on a comparable common player-GW cohort.

All event-provider mappings must remain season-scoped and provider-specific. A cross-season canonical person link may be stored as a separate reviewed relationship, but it must never overwrite the original provider ID or FPL season element ID. No name-only or fuzzy-name match may become a verified join.

## 4. Main blockers

### 4.1 Missing historical CTA seasons

The current integrated event-data evidence is concentrated in 2017/18 and 2026/27. There is no verified continuous multi-season CTA panel covering the intervening seasons. Current-season Opta/PulseLive team aggregates do not fill this gap because they are not player-level event features and do not have historical deadline vintages.

### 4.2 Historical FPL target-data rights

The Vaastav repository's MIT software licence does not grant rights to the underlying FPL data. The Wyscout event release's CC BY 4.0 status does not grant rights to the FPL target data joined to it. The 11footy CC BY-NC 4.0 label also carries a non-commercial restriction. Preserve attribution and provenance, and do not infer a broader permission from the repository's code licence.

Before a joined historical CTA/FPL panel is used beyond permitted internal research, document the applicable terms or obtain authorization for the FPL target source and each event source. Do not redistribute raw provider or player-level data.

### 4.3 Historical point-in-time provenance

Retrospective player histories and cumulative season aggregates cannot prove what was available at a past deadline. Lagging a retrospectively corrected value prevents target-match leakage but does not prove that the historical value existed in that form at the time.

A strict prospective dataset must freeze raw inputs before each deadline, retain timestamps, source versions and hashes, and never overwrite earlier snapshots. Historical seasons without those vintages must remain explicitly `NOT_VERIFIED_RETROSPECTIVE_SOURCE_VINTAGES`.

### 4.4 Event-feature comparability

Wyscout, 11footy, Opta/PulseLive and StatsBomb have different schemas and coverage. Similar labels do not imply equivalent measurements. Maintain provider-specific feature families, definitions, missingness and provenance. Do not pool them as if they were one homogeneous event feed without an explicit mapping and measurement validation.

## 5. Feasible paths

### Path A — Prospective multi-season accumulation (preferred for defensible PIT evidence)

1. Continue capturing 11footy current-season player-match data at defined pre-deadline cutoffs.
2. Verify player and fixture mappings independently, preserving provider namespaces and season-specific FPL IDs.
3. Freeze raw source snapshots, normalized panels, source URLs/versions, UTC capture times and SHA-256 hashes.
4. Archive immutable per-deadline feature snapshots and later join official FPL outcomes only after the deadline.
5. Repeat each season. A second season of prospective capture is required before making multi-season generalization claims.
6. Confirm source terms permit the intended collection, retention and research use; do not publish raw player-level files.

This path gives strong point-in-time integrity but takes time to accumulate multiple seasons.

### Path B — Authorized historical event seasons

1. Identify event providers with EPL player-match coverage for additional completed seasons.
2. Verify the actual season files, event schema, fixture universe, player IDs and source versions—not just a provider's general availability.
3. Obtain or identify an authorized historical FPL target source for the same seasons.
4. Build season-scoped identity crosswalks with independent evidence and one-to-one constraints.
5. Record retrospective-vintage limitations honestly. These seasons can expand exploratory temporal robustness but cannot be described as deadline-frozen PIT evidence unless archived vintages exist.
6. Evaluate provider-specific feature families separately before considering any harmonized cross-provider features.

This path may expand season coverage sooner, but retrospective source limitations remain.

### Path C — Current-season Opta/PulseLive extension

This path is supplementary only. First resolve underlying data permissions and durable source capture. It can provide team-match context from the inspected files, but cannot be represented as player-level match event CTA unless actual player-match event metrics are obtained and verified. It does not replace Wyscout player-event data or StatsBomb.

## 6. Required readiness gates for each additional season

A season is CTA-panel eligible only when all gates below have explicit evidence:

1. **Source identity:** exact provider, competition, season, dataset version and source URL.
2. **Rights and terms:** documented permission/terms for the event data and the FPL targets; non-commercial restrictions and attribution retained.
3. **Fixture mapping:** exact fixture-level reconciliation, including dates, opponents, home/away and postponed/rescheduled matches.
4. **Player identity:** independently reviewed, season-scoped, one-to-one provider-to-FPL mappings; unresolved rows excluded.
5. **Coverage:** player-match and player-GW coverage, missingness and selection effects reported.
6. **Feature semantics:** provider-specific event definitions, coordinate conventions, nulls and unsupported fields documented.
7. **Point-in-time status:** deadline-frozen historical source vintages or an explicit retrospective-only label.
8. **Leakage controls:** target-match events and outcomes excluded from predictors; features use only data available before the target deadline.
9. **Reproducibility:** raw-source hashes, normalized-output hashes, builder version, crosswalk version and deterministic cohort manifest.
10. **Validation:** chronological folds and exact common player-GW cohorts against the agreed external FPL benchmark sources, with paired uncertainty and per-season stability.

A season failing any critical gate remains excluded from strict CTA promotion. A structural join or identity pass alone is not predictive validation.

## 7. Required validation design once coverage exists

- Preserve the 2017/18 experiment as a separately labelled historical cohort.
- Add each new season only after the readiness gates pass; do not silently combine incompatible providers.
- Use expanding-season / rolling-origin folds. A validation season must not contribute to fitting, feature selection, calibration or identity-rule tuning for that fold.
- Compare conventional FPL model tracks, standalone CTA/ABC and any CTA-augmented model on the exact same eligible player-GW cohort and deadlines.
- In parallel, compare each eligible project model with the agreed external FPL benchmarks (FPL Review tiers separately, FPL Forecaster, FPL Lucho variants separately, Sideline Quant, FPL Cat, FPLRogue and FPL Wildcard where actual pre-deadline captures exist).
- Preserve missing provider forecasts as missing; publish source coverage and common-cohort sizes. Do not score a source on a different cohort and call it a paired comparison.
- Report MAE, RMSE, signed error, tail-error rates, probability/distribution scores where genuinely available, ranking/top-K selection and decision utility.
- Use dependence-aware paired uncertainty (player-season clusters for forecast errors and appropriate deadline/season clusters for rankings/decisions).
- Report season-by-season results and source-vintage status. No pooled score alone is a promotion decision.

## 8. Immediate M2 actions

1. Keep the current 2017/18 CTA evidence restricted and research-only.
2. Do not promote the 30 11footy P1 cross-season candidates without independent review.
3. Audit candidate event providers by exact EPL season coverage, schema, rights, fixture/player IDs and historical snapshot availability.
4. Establish a prospective immutable 2026/27 CTA capture ledger, subject to source terms and durable archive controls.
5. Keep the external FPL benchmark capture/evaluation track active; it is a separate M2 requirement and must not be replaced by FPL-history-only baselines.
6. Revisit cross-season model validation only when at least one additional season passes the identity, rights, coverage and provenance gates.

## 9. References in this repository

- `docs/FPL_MULTI_SEASON_DATA_READINESS.md`
- `docs/11FOOTY_HISTORICAL_FPL_IDENTITY.md`
- `docs/WYSCOUT_CTA_INTEGRATION.md`
- `docs/CTA_FPL_DECISION_INTEGRATION_STATUS.md`
- `reports/WYSCOUNT_FPL_SOURCE_AUDIT_2026-11-17.md`
- `reports/PROVIDER_SPECIFIC_IDENTITY_CROSSWALKS_2026-11-18.md`
- `reports/OPTA_PULSE_FPL_SOURCE_AUDIT_2026-11-17.md`
- `docs/EXTERNAL_FPL_BENCHMARK_PROTOCOL.md`

This assessment is a feasibility decision, not a claim that additional data have been obtained or that CTA is validated.