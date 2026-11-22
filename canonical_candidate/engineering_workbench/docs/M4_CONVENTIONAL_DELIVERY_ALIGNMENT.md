# Conventional M4 delivery alignment on the current M3 branch

## Scope

This branch is based directly on the current M3 implementation branch, `feat/m3-external-benchmark-decision-engine`, rather than the older M3/M4 integration base used by the earlier delivery branch.

It ports only the conventional delivery boundary:
- the M3-output acceptance contract;
- the optional, descriptive M3/M4 context adapter;
- independent verification of the frozen M3 replay evidence;
- the conventional delivery report and focused regression tests.

It does not replace or modify M3 decision logic, forecast values, transfer legality, the frozen decision, or the current M3 replay implementation.

## Source and product boundaries

- Conventional personal-squad delivery consumes only the M3 conventional FPL Cat or Sideline Quant output.
- CTA-informed personal-squad recommendations and squad-independent CTA rankings remain withheld pending M2 validation.
- LiveFPL EO/field context is optional and descriptive. Missing, stale, or invalid context is withheld.
- EO is never blended into expected points.
- CoVar remains research-only: `decision_weight=0`, `production_eligible=false`, `covar_used=false`.

## Real M3 evidence replay

The first real integration target is the successful GW11 M3 capture:
- source workflow run: `44809552413`;
- artifact: `predeadline-decision-evidence-manager-421025-gw11`;
- snapshot: `fplcat-gw11-20261120T201442368955Z`.

The artifact contains the frozen conventional recommendation, the sealed decision evidence, and the deterministic M3 replay report. The replay workflow verifies these exact files and hashes before building the conventional M4 report. This is delivery-contract verification, not a forecast-performance or production-release claim.

## Privacy

The full conventional M4 report is manager-specific. It is generated only in the ephemeral Actions runner and is not uploaded as a public artifact. The workflow publishes only a hash/provenance validation manifest with no player IDs, squad, bank, transfer, or recommendation payload.

A durable downloadable manager-specific report requires a separately approved private destination; the manager-free CoVar archive is not used for that purpose.

## Acceptance boundary

A successful workflow run proves that the current M3 frozen output can be consumed by the conventional M4 delivery contract without changing the frozen decision. It does not approve production release, CTA recommendations, CoVar weighting, or M2/M4 performance evaluation.
