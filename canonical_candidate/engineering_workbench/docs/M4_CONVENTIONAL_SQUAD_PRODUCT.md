# M4 — Conventional personal-squad recommendation

Status: **FIRST M4 PRODUCT ADAPTER IMPLEMENTED — EXPLORATORY PREVIEW ONLY**

## Scope

Deliver the conventional squad-specific recommendation first. It is based on one eligible, provider-labelled expected-points snapshot and the manager's explicit 15-player squad, bank, free transfers and lineup constraints.

The product exposes:
- Hold versus one-transfer decision and ranked legal alternatives.
- Current and proposed starting XI, legal formation, captain, vice-captain and bench order.
- Expected starting points and transfer EV delta/hit-cost accounting.
- Exact forecast provider, snapshot, timestamps, source hashes and player-metadata provenance.
- Forecast quality and limitations, with exploratory status preserved.
- Optional Team Exposure & Correlation Model (TECM) diagnostics, bound to the same forecast snapshot and covering at least five consecutive Gameweeks.

## Reusable M3-to-M4 forecast contract

M4 must not be hard-wired to one forecast provider. Each forecast source must be converted into the same player-level forecast input and then passed through the same personal-squad decision engine. The source identity, model version, snapshot, as-of time, quality and raw provenance remain attached to the run.

The initial source is the eligible conventional external benchmark. When CTA-FPL forecasts are ready, a CTA forecast adapter must emit the same personal-squad run contract (CTA_MODEL_PERSONAL_SQUAD) and invoke the same M4 decision engine. The M4 product adapter accepts either source-labelled run type but preserves the source label. This does not certify CTA forecasts or make them release-eligible.

The decision rules, squad state, budget, free-transfer count, formation constraints and evaluation horizon must be held constant when comparing conventional and CTA runs. Separate output labels and provenance prevent accidental blending.

## Decision isolation

The conventional product's transfer action, XI and captaincy remain **expected-points-only**. Field-relative ownership/EO, poll-implied EO, CoVar and TECM are separate context layers and cannot change the canonical EV decision.

### Team Exposure & Correlation Model (TECM)

The script `scripts/team_exposure_correlation.py` computes squad club/position exposure over a minimum five consecutive Gameweeks and, only when coherent joint player-point scenarios are supplied, estimates within-Gameweek player covariance. It reports defensive clean-sheet stacking (GK/DEF), attacking stacking (MID/FWD) and mixed club exposure. Club identity alone never implies a correlation coefficient.

Expected points remain additive across players; a double-up is not awarded an artificial EV bonus. Stacking changes concentration and the distribution of outcomes. The TECM output is attached to M4 as diagnostic-only, must bind to the exact forecast snapshot, and is fail-closed unless `decision_weight=0`, `production_eligible=false` and additive expected-points accounting is explicit. It cannot change transfer ranking, starting XI, captaincy or hit decisions.

Joint scenarios must be genuinely joint forecasts for the same Gameweek, not reconstructed from marginal xP or EO. The current horizon covariance sums within-Gameweek covariance across weeks and explicitly assumes Gameweek outcomes are independent. If joint scenarios are unavailable, M4 still reports team exposure but marks player covariance unavailable; it does not invent correlations.

The engine retains its existing rules: one transfer at a time, legal budget/position/team constraints, starting-XI-first evaluation, no goalkeeper rotation transfers, and no routine bench-to-bench upgrades. The recorded risk profile is not applied because player-level variance is not validated.

## Release boundary

The shared `build_personal_squad_product` adapter (with a backwards-compatible legacy function alias) consumes a source-labelled personal-squad run; it does not create new forecasts or promote a provider. It emits `conventional_personal_squad` for an external-benchmark run and `cta_informed_personal_squad` for a CTA-model run, preserving distinct labels and provenance. It preserves the source run's release blockers and always reports EXPLORATORY_PREVIEW until the relevant forecast and decision-evaluation gates allow release. A passing contract test is not evidence of live decision readiness.

## Entry point

scripts/build_conventional_squad_product.py (`build_personal_squad_product`; legacy `build_conventional_squad_product` alias retained)

Input is the complete JSON output of a conforming personal-squad run. The output is a versioned conventional_personal_squad product object suitable for a delivery/API layer.

## Acceptance coverage

tests/test_build_conventional_squad_product.py checks EV-only decision content, provenance preservation, exclusion of field/CoVar context, rejection of incomplete or unsupported runs, and a CTA-model-shaped run that retains the separate `cta_informed_personal_squad` identity without becoming release-eligible.
## Live manager execution path

The FPL Cat capture workflow also supports a real-manager conventional M3-to-M4 execution:
- Capture the official previous-Gameweek picks, manager history, transfer log and FPL bootstrap metadata for the confirmed public manager ID.
- Carry the previous official starting XI, outfield bench order, reserve goalkeeper and captaincy forward only as the initial hold-plan baseline. The personal-squad engine may optimize the XI and captaincy for the target Gameweek.
- Derive free transfers from official event transfer counts, hit costs and Wildcard/Free Hit history. A chip consumes the new transfer for that Gameweek while preserving banked transfers, consistent with the official FPL rules.
- Reuse the previous deadline bank only when the target-Gameweek transfer log is empty. If target-Gameweek transfers exist, stop and require a refreshed bank/state rather than guessing.
- Capture provider, metadata and manager evidence before the target deadline; run the frozen M3 conventional decision and the same personal-squad engine through the M4 adapter; require their action and transfer candidate to agree.
- Public previous-Gameweek picks cannot reveal an unsaved target-Gameweek chip selection. The initial workflow therefore records chip_state: NONE as an explicit assumption, not as an independently verified fact; a planned chip requires a rerun with the correct manager state.

Entry points:
- scripts/capture_public_fpl_manager_snapshot.py — public manager state and transfer-history snapshot
- scripts/run_fplcat_live_m4_recommendation.py — FT reconstruction, strict pre-deadline capture, frozen M3 decision and M4 conventional product
- .github/workflows/capture-fplcat-benchmark.yml — capture, synthetic contract replay and live-manager execution

The live execution remains EXPLORATORY_PREVIEW and release-ineligible. The current live provider-xP decision path remains single-Gameweek until a valid five-plus-Gameweek forecast bundle is supplied; TECM is not fabricated from a one-Gameweek snapshot and remains diagnostic-only.

## Multi-Gameweek transfer policy (M4)

A transfer is an investment across at least five upcoming Gameweeks, not a one-week xP reaction. The product must compare incoming and outgoing players across the same five-plus-GW horizon, include fixture sequence and expected minutes where available, and report cumulative expected-points delta and transfer cost. A player is not sold solely because of low expected points in the immediate Gameweek or one difficult fixture. The one-Gameweek live path must not be described as satisfying this policy.

## TECM implementation boundary

The TECM module provides a reusable analytical contract and M4 attachment guard. Its output is optional until complete multi-Gameweek forecasts and coherent joint scenarios are captured. No forward covariance, player correlation, field joint portfolio, or transfer benefit is claimed from club stacking alone. The existing conventional and CTA-informed product identities remain separate and use the same squad constraints.


## Five-plus-Gameweek forecast bundle and transfer evaluator — 22 Nov 2026

Two isolated engineering components now define and consume the required multi-Gameweek inputs:

- `scripts/multi_gameweek_forecast_contract.py` validates a bundle of at least five consecutive, immutable provider snapshots. Each panel must be fixture-grain (`player_fixture`), retain the same provider/product/variant/version and season, carry pre-deadline provenance, be no more than 24 hours old at the decision as-of time, and include player metadata and fixture schedule. The bundle binds the per-Gameweek source snapshot IDs under one `forecast_bundle_id`. It fails closed for missing player metadata, missing scheduled player-fixture forecasts, duplicate snapshots, mismatched provider identity, stale panels or incomplete horizons. A blank Gameweek is represented as zero only when the supplied fixture schedule confirms that the player's club has no fixture.
- `scripts/multi_gameweek_transfer_evaluator.py` consumes that bundle and compares HOLD with one affordable, position-legal transfer over the same five-plus-Gameweek horizon. It reconciles fixture-level xP/minutes to player-Gameweek totals, checks full squad/starting-XI composition and club limits, reports per-GW starting-XI deltas and incoming/outgoing fixture detail, and subtracts a hit once. A bench transfer only adds starting-XI value if the incoming player displaces a starter on the full-horizon comparison.

Both components are exploratory and have decision weight zero / production eligibility disabled. They are not wired into `personal_squad_engine.py`, the provider capture workflows or the live recommendation path. The existing production path remains one-Gameweek until genuine provider snapshots for the required future Gameweeks are obtained and validated. No one-week value is extrapolated to fill the horizon.

### Joint scenario provenance hardening

`scripts/team_exposure_correlation.py` now requires a provenance envelope when joint scenarios are supplied: scenario-set ID, matching forecast bundle/snapshot ID, matching model version, generation/capture timestamps, source URL, raw SHA-256 and exact row count. Every scenario row must bind to the same scenario set, forecast snapshot and model version and contain a complete player-point vector for the requested squad. Every Gameweek must have at least two scenarios, with consistent scenario counts across the horizon. Missing or mismatched scenario evidence fails closed; no covariance is inferred from club membership or marginal xP/EO.

The current explicit cross-Gameweek independence assumption remains: within-Gameweek covariance estimates are summed across Gameweeks. TECM remains diagnostic-only with zero decision weight and production eligibility disabled. This contract does not establish scenario calibration or statistical validation.
