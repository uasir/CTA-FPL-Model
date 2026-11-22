# M4-T2 — Conventional recommendation input/output contract

The initial M4 conventional product consumes exactly one frozen M3 conventional personal-squad
recommendation. It does not call a second optimizer or recalculate provider xP.
The validator is a presentation/delivery boundary over the M3 output, not a
substitute for M3's legality engine or statistical acceptance.

The implementation currently retains the legacy module name `m5_conventional_delivery_contract.py`; it verifies:
- conventional personal-squad run type and explicit exploratory/non-release status;
- provider identity and snapshot identity;
- decision and deadline timestamps;
- one frozen HOLD/TRANSFER action with suppressed alternative candidates;
- frozen-decision SHA-256 and exact embedded candidate binding;
- original 15-player squad and complete post-decision 15-player squad;
- transfer-out/in consistency, legal formation label, XI, outfield bench,
  reserve goalkeeper, captain and vice-captain coverage;
- explicit release blockers.

The contract deliberately does not claim provider forecast quality, transfer
utility, a validated CTA model, or production eligibility. M4 EO context is
not required and cannot change the M3 output. If a valid M4 artifact is
available, it remains a separate optional sidecar under the M4 adapter.

Run:

```bash
PYTHONPATH=scripts python scripts/m5_conventional_delivery_contract.py \
  --input frozen_m3_decision.json --output m5_delivery_acceptance.json
```
