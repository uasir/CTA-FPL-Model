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

## Decision isolation

The conventional product uses **expected points only**. Field-relative ownership/EO, poll-implied EO, CoVar and CTA model adjustments are explicitly excluded from its score. They may appear in separate products or contextual views later, but cannot change this product's transfer action, XI or captaincy.

The engine retains its existing rules: one transfer at a time, legal budget/position/team constraints, starting-XI-first evaluation, no goalkeeper rotation transfers, and no routine bench-to-bench upgrades. The recorded risk profile is not applied because player-level variance is not validated.

## Release boundary

The adapter consumes the existing M3 external-benchmark personal-squad run; it does not create new forecasts or promote a provider. It preserves the source run's release blockers and always reports EXPLORATORY_PREVIEW until the M3 evidence gates and forecast validation allow release. A passing contract test is not evidence of live decision readiness.

## Entry point

scripts/build_conventional_squad_product.py

Input is the complete JSON output from scripts/run_external_benchmark_personal_squad.py. The output is a versioned conventional_personal_squad product object suitable for a delivery/API layer.

## Acceptance coverage

tests/test_build_conventional_squad_product.py checks EV-only decision content, provenance preservation, exclusion of field/CoVar context, and rejection of incomplete or wrong-system runs.
