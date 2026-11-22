# M4 — Conventional personal-squad recommendation

Status: **FIRST M4 PRODUCT ADAPTER IMPLEMENTED — EXPLORATORY PREVIEW ONLY**

## Scope

Deliver the conventional squad-specific recommendation first. It is based on one eligible, provider-labelled expected-points snapshot and the manager's explicit 15-player squad, bank, free transfers and lineup constraints.

The first product exposes:
- Hold versus one-transfer decision and ranked legal alternatives.
- Current and proposed starting XI, legal formation, captain, vice-captain and bench order.
- Expected starting points and transfer EV delta/hit-cost accounting.
- Exact forecast provider, snapshot, timestamps, source hashes and player-metadata provenance.
- Forecast quality and limitations, with exploratory status preserved.

## Reusable M3-to-M4 forecast contract

M4 must not be hard-wired to one forecast provider. Each forecast source must be converted into the same player-level forecast input and then passed through the same personal-squad decision engine. The source identity, model version, snapshot, as-of time, quality and raw provenance remain attached to the run.

The initial source is the eligible conventional external benchmark. When CTA-FPL forecasts are ready, a CTA forecast adapter must emit the same personal-squad run contract (CTA_MODEL_PERSONAL_SQUAD) and invoke the same M4 decision engine. The M4 product adapter accepts either source-labelled run type but preserves the source label. This does not certify CTA forecasts or make them release-eligible.

The decision rules, squad state, budget, free-transfer count, formation constraints and evaluation horizon must be held constant when comparing conventional and CTA runs. Separate output labels and provenance prevent accidental blending.

## Decision isolation

The conventional product uses **expected points only**. Field-relative ownership/EO, poll-implied EO, CoVar and CTA model adjustments are explicitly excluded from its score. They may appear in separate products or contextual views later, but cannot change this product's transfer action, XI or captaincy.

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

The live execution remains EXPLORATORY_PREVIEW and release-ineligible. It is a one-Gameweek provider-xP decision, not a validated multi-week strategy or a CTA-informed recommendation.