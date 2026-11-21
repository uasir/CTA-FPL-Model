# M4 Joint Gameweek Forecast Producer — Engineering Specification

## Status

**NOT IMPLEMENTED — BLOCKING EMPIRICAL CoVar VALIDATION.**

The repository currently has a joint fixture-scenario composer and a fixture-to-Gameweek aggregator. These are deterministic adapters: they consume explicit fixture outcome catalogues and explicit joint scenario assignments/probabilities. They do not estimate probabilities, sample outcomes, fit dependence, or generate a Cartesian product.

The official FPL `ep_next` snapshot is an exploratory expected-points baseline. The lagged ridge work is an exploratory player-level points/minutes model with point-in-time and validation limitations. The descriptive Onside covariance panel is not a predictive joint-outcome model. None of these artifacts may be relabelled as a joint forecast producer.

## Forecasting approach selected by project owner (2026-11-21)

The current CoVar workstream will use **the exact conventional forecast snapshot consumed by the M3 decision run** as its player-level expected-points/minutes foundation. The M3 path is `run_predeadline_m3_decision.py` → `run_external_benchmark_personal_squad.py` → `canonical_provider_forecast_contract.py` → `canonical_forecast_recommendation_adapter.py` → `personal_squad_engine.py`. Provider expected-points values are preserved unchanged; expected minutes are taken from the provider record when supplied, otherwise from the explicit FPL metadata join. CoVar must bind to the same M3 `forecast_snapshot_id` and `model_version`, not substitute a different forecast source.

CTA-derived features, predictions, covariance and provider panels are not CoVar forecast inputs at this stage. This decision is specific to the current CoVar workstream and does not remove or suspend CTA research elsewhere in the repository.

CoVar extends the M3 forecast from player-level expected points to portfolio-level outcomes. Conventional player expected-points estimates alone do not define a calibrated joint probability distribution. The research implementation must therefore derive scenario uncertainty and dependence from eligible realized FPL outcomes and validated residual/dependence methods, while retaining the M3 conventional forecast as the expected-points anchor. Until this is implemented and empirically validated, joint scenario probabilities must be treated as supplied research inputs, not as model predictions.

The existing downstream composer, Gameweek aggregator, scorer, calibration evaluator, bootstrap and archive tooling remain reusable. Data-readiness work for this path should prioritize immutable archives of the exact M3 provider forecast snapshots and their joined FPL metadata, plus realized FPL outcomes. The separate exploratory `build_fpl_baseline_forecast_snapshot.py` adapter (official `ep_next` plus a minutes proxy) must not be silently substituted for the M3 decision forecast.

## Required producer boundary

A future producer must emit a versioned, immutable forecast bundle with:

1. Forecast identity: forecast ID, season, target Gameweek, mode (`REGULAR_GW` by default; `FREE_HIT` only as an explicitly requested evaluation mode), generation timestamp, as-of timestamp, first kickoff, training-data cutoff, model/config versions and SHA-256 hashes.
2. Complete source provenance: source identifiers, exact captured-byte hashes, availability/retrieval timestamps and archive references. Every source used must have been observed no later than forecast generation and must be eligible as of the declared forecast timestamp.
3. Fixture outcome catalogues: for every target fixture, a finite, versioned set of mutually exclusive fixture states. Each state must include complete outcomes for the declared player universe in that fixture, including minutes, played status, cards and FPL points (or sufficient events to derive official points).
4. Explicit joint scenario rows: each row maps every target fixture to exactly one fixture-state ID and supplies a strictly positive probability. Joint probabilities must sum to one. The row must preserve dependencies across fixtures and across players within fixtures.
5. Full Gameweek outcomes: use the existing composer and aggregator to materialize complete Gameweek outcomes, then the existing full-Gameweek contract/scorer to score candidate and sampled field portfolios against the exact same scenarios and probabilities.
6. Reproducibility: deterministic serialization, stable scenario IDs, hashes for the full forecast payload and all model/config/source artifacts, and an archive manifest verified by the existing archive verifier.

## Statistical requirements

- The producer must be trained/evaluated on time-ordered data with complete Gameweek clusters as the independent temporal unit. Repeated snapshots of one Gameweek are not independent observations.
- Training cutoffs must precede every forecast as-of timestamp; each forecast as-of must precede the earliest fixture kickoff.
- Any dependence structure must be learned from observed joint outcomes or supplied by a separately justified, externally validated model. Do not infer joint manager portfolios from marginal EO.
- Do not multiply fixture marginal probabilities, assume fixture independence, or form a Cartesian product unless an independently validated dependence model explicitly justifies that construction. The existing composer intentionally requires explicit joint assignments.
- The producer must document how fixture states are defined, how player minutes/appearance and FPL points are generated, how promoted/injured/transferred players and missing data are handled, and how double/triple Gameweeks are aggregated.
- Probability calibration must be evaluated against a predeclared reference on chronologically held-out Gameweeks using multiclass Brier score, log loss, reliability diagnostics and Gameweek-clustered uncertainty intervals. Include sharpness and state-catalogue coverage diagnostics.
- Compare against meaningful baselines, including historical-frequency and appropriate independent/marginal baselines, but never use a baseline that leaks target outcomes or information unavailable at forecast time.
- Require prospective captures and immutable forecast bundles. Retrospective API responses or current snapshots of historical rows are not point-in-time evidence.

## Minimum acceptance gates

1. A complete producer implementation with unit and property tests for fixture and player coverage, probabilities, timestamps, leakage, missingness, reproducibility and deterministic output.
2. A documented model card and data card, including licensing/source constraints and limitations.
3. Chronological train/validation/test separation by entire Gameweek, with no overlapping Gameweeks and no tuning on the final test split.
4. A sufficiently broad multi-season or otherwise defensible independent Gameweek sample; report actual cluster count and uncertainty rather than asserting a fixed adequacy threshold.
5. Held-out calibration and sharpness results against predeclared reference models, including cluster-bootstrap intervals and per-season/per-regime diagnostics.
6. Prospective pre-deadline forecasts archived with complete source/model/config/payload bytes and verifiable provenance.
7. Independent review of forecast construction and a real FPL scoring replay before any production eligibility discussion.

## Existing components to reuse

- `m4_covar_joint_fixture_scenario_composer.py`: validates explicit cross-fixture assignments and probabilities; no independence assumption.
- `m4_covar_fixture_to_gameweek_aggregator.py`: aggregates fixture outcomes into full-Gameweek player outcomes.
- `m4_covar_full_gameweek_contract.py` and `m4_covar_full_gameweek_scoring.py`: validate and score candidate/field portfolios on identical scenarios.
- `m4_covar_joint_probability_calibration.py`, `m4_covar_gameweek_cluster_bootstrap.py`, `m4_covar_historical_frequency_benchmark.py`, and `m4_covar_historical_frequency_backtest.py`: held-out evaluation and reference comparisons.
- `m4_covar_point_in_time_source_capture.py` and `m4_covar_forecast_archive_packager.py`: prospective source capture and complete private forecast archive packaging.

## Non-negotiable safeguards

- CoVar remains research-only: `decision_weight=0`, `production_eligible=false`.
- No changes to M3 EV, legality, transfer logic, frozen decisions, decision hashes, or conventional M5 recommendations.
- Do not allow CoVar to alter transfer rankings/actions, starting XI, captaincy or squad-independent market rankings.
- Manager-level field portfolios and personal squad combinations remain private. Never commit them or upload them to public GitHub Actions artifacts.
- Marginal EO is descriptive exposure only; it is not a joint manager portfolio distribution.
- Free Hit is never assumed. The default is regular Gameweek analysis.
- No PR merge without explicit approval.

## Immediate implementation sequence

1. Inventory eligible historical fixture/player event data and establish whether it can legally and reliably support the target state definitions.
2. Build a point-in-time dataset constructor with complete fixture-level and player-level outcome coverage and provenance checks.
3. Define and implement a simple, auditable fixture-state probability baseline.
4. Define and fit an explicit dependence model from historical joint observations; retain the historical-frequency reference as a benchmark, not as a substitute for a calibrated dependence model.
5. Emit the producer bundle described above and connect it to the existing composer, aggregator, scorer, archive packager and calibration/backtest harness.
6. Keep all output research-only until prospective and held-out evidence passes the acceptance gates.

## Current conclusion

The repository has enough downstream contracts, scoring, archive and evaluation infrastructure to consume a real joint forecast. It does **not** yet contain a validated upstream producer. The next work must be data and statistical model construction, not another adapter that invents joint probabilities.
