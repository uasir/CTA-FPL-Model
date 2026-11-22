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

The shared product adapter consumes a source-labelled personal-squad run; it does not create new forecasts or promote a provider. It emits `conventional_personal_squad` for an external-benchmark run and `cta_informed_personal_squad` for a CTA-model run, preserving distinct labels and provenance. It preserves the source run's release blockers and always reports EXPLORATORY_PREVIEW until the relevant forecast and decision-evaluation gates allow release. A passing contract test is not evidence of live decision readiness.

## Entry point

scripts/build_conventional_squad_product.py

Input is the complete JSON output of a conforming personal-squad run. The output is a versioned conventional_personal_squad product object suitable for a delivery/API layer.

## Acceptance coverage

tests/test_build_conventional_squad_product.py checks EV-only decision content, provenance preservation, exclusion of field/CoVar context, rejection of incomplete or unsupported runs, and a CTA-model-shaped run that retains the separate `cta_informed_personal_squad` identity without becoming release-eligible.
