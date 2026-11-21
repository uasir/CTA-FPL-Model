# M5 Execution Charter — Conventional FPL Recommendation Delivery

**Status:** M5-T1 complete; M5-T2/T4/T5/T6 engineering implementation CI-tested; GW11 live evidence archived; exact archive-to-report acceptance passed in historical replay run `44937997402`.
**Base:** M4 handoff commit `4da03390b293ea114376a03096c7ecdab9abd98e`.
**Branch:** `feat/m5-conventional-delivery`.
**Release posture:** engineering-only until the live-data and M3 acceptance gates are met.

## 1. Delivery scope

M5's first deliverable is the conventional FPL recommendation product only:

- One manager-specific recommendation using the actual, timestamped 15-player squad and manager constraints.
- External benchmark forecasts through the provider-neutral M3 contract; initially FPL Cat where the provider-generation timestamp is disclosed and the snapshot passes the strict pre-deadline checks.
- Hold versus transfer/roll, transfer-in/out, legal post-transfer squad, starting XI, formation, bench order, captain and vice-captain.
- Provider xP preserved unchanged and shown in points; source, product/variant, generation/capture timestamps, raw hashes, coverage and limitations remain attached.
- M4 field-relative exposure may appear as an optional descriptive sidecar only when a valid pre-decision field snapshot exists. It cannot alter M3 expected points, legality, transfer choice or frozen decision.
- Manager preferences remain binding: one strong starting XI, no routine rotation, one starting goalkeeper, reserve goalkeeper retained, and no bench-to-bench transfers that do not improve the starting XI.

This is a benchmark-backed conventional FPL recommendation, not a CTA-trained forecast or a claim that the project's internal player model is validated.

## 2. Products explicitly withheld

The architecture retains three logically distinct products, but this first M5 release does **not** deliver all three:

1. **Conventional personal-squad recommendations:** in scope for M5 initial delivery.
2. **CTA-informed personal-squad recommendations:** withheld until the internal CTA/ABC/2PM forecasting system passes its independent validation and promotion gates.
3. **Squad-independent CTA player rankings:** withheld until the same model-readiness gates pass and the general-market service has its own acceptance evidence.

Do not use a placeholder CTA score, unvalidated CTA features, or a synthetic combined score to make either withheld product appear available. CoVar remains disabled with zero decision weight.

## 3. Output separation

The initial product may contain two clearly separated sections:

- **Conventional decision:** the M3 provider-backed decision and its EV/legality/provenance.
- **Field context:** optional M4 EO/exposure, cohort, sample, uncertainty and coverage diagnostics.

Expected points are points. EO/exposure are percentages or percentage-point differences. They are not combined into one score. Missing EO remains missing; official selected-by ownership is not EO. A provisional pre-deadline sample is not final locked EO or a whole-field census.

If M4 is absent, stale, invalid or unavailable, the conventional M3 result must still be reproducible and unchanged; the field-context section is withheld with a reason.

## 4. M5 work sequence

### M5-T1 — Product scope and release boundary
Define the initial conventional-only product, withheld products, output separation and user constraints. **This charter completes T1.**

### M5-T2 — Input and output acceptance contract
**Completed and CI-tested.** `m5_conventional_delivery_contract.py` validates the frozen M3 conventional output, provider identity, strict decision/deadline timing, frozen-decision hash and embedded candidate, alternatives suppression, original and post-transfer 15-player squads, XI/bench/reserve goalkeeper, formation and captaincy, plus explicit release blockers. It preserves non-release status and does not recalculate EV or depend on M4.

### M5-T3 — Live benchmark decision evidence
Run a real pre-deadline FPL Cat capture and manager-backed decision for the target Gameweek. Verify provider generation time, capture time, metadata time, manager squad, bank, free transfers, purchase prices, and deadline. Inspect the complete post-transfer squad plan. A successful capture alone is not a recommendation acceptance.

### M5-T4 — Field-context optionality
Where a genuine pre-decision EO artifact exists, attach M4 descriptively and verify that M3 EV, legality, recommendation and frozen decision hash are unchanged. If no valid field artifact exists, deliver conventional output without EO and state the limitation.

### M5-T5 — User-facing recommendation report
Produce a readable decision report with HOLD/TRANSFER rationale, alternatives, full squad/lineup/bench/captaincy, budget and transfer consequences, forecast provenance, field-context limitations and explicit non-CTA status.

### M5-T6 — Reproducibility, regression and acceptance
Replay the exact archived inputs; verify deterministic output, Python/JavaScript contract parity, legal squad constraints, optional M4 isolation and fail-closed degraded modes. **Exact GW11 replay completed:** Actions run `44937997402` downloaded the original artifact from run `44809552413`, passed the conventional delivery contract and report builder, and uploaded artifact `conventional-m4-replay-source-run-44809552413` (artifact ID `14719429674`) containing acceptance, delivery report and source/output SHA-256 manifest. The report action is `TRANSFER`; optional field context is `NOT_SUPPLIED`; release eligibility remains false.

## 5. Hard release gates

No initial M5 recommendation is release-approved until all of the following hold:

- M3's benchmark-backed decision path is accepted and a real live manager-backed run is verified after the post-transfer plan correction.
- Provider generation, capture, FPL metadata and manager-state timestamps are all strictly pre-deadline and provenance hashes replay correctly.
- All 15 player IDs, purchase prices, bank and free transfers are verified against the user-confirmed manager state; no missing values are silently substituted.
- The returned post-transfer squad contains the incoming player and excludes the outgoing player; the original squad remains separately recorded.
- The proposed action respects budget, position, team limits, legal formation, bench order, reserve goalkeeper and captaincy constraints.
- Optional M4 context cannot alter the frozen M3 result.
- Full CI and exact-input replay pass.
- M3 post-Gameweek validation remains tracked independently; it is not silently declared complete by M4 or M5.

A CI pass over deterministic fixtures does not prove a live data capture. A live capture does not by itself prove recommendation quality or production readiness.

## 6. Current known blockers

- M4's pre-deadline field acquisition has not yet produced a verified live artifact. Conventional M5 can proceed without EO; it must not invent or relabel EO.
- A verified GW11 FPL Cat capture is archived in Actions run `44809552413` (artifact `predeadline-decision-evidence-manager-421025-gw11`). It was captured at `2026-11-20T20:14:42.975478Z`, before the official `2026-11-21T11:00:00Z` deadline; provider generation/capture and official metadata/manager-state archives are timestamped and hashed. Its deterministic replay passed, and the frozen recommendation explicitly records `squad_plan_state=POST_TRANSFER`, preserving the original plan separately from the recommended post-transfer plan. The capture code commit descends from the post-transfer engine fixes, so the earlier statement that this run predates that correction is superseded. The exact archive has now passed the conventional delivery contract and report builder in replay run `44937997402`. Acceptance summary: `PASS_CONVENTIONAL_M5_DELIVERY_CONTRACT`; manager `421025`; GW11; action `TRANSFER`; formation `4-3-3`; 15-player squad; XI 11; bench 3; captain 411; vice-captain 115; frozen decision SHA-256 `25286ed37076d247a0839190394ec5d8258119bb669362b2aa5c5cba1195d49f`. Report status `PASS_CONVENTIONAL_DELIVERY_WITH_OPTIONAL_FIELD_CONTEXT`; field context `NOT_SUPPLIED`; report SHA-256 `55fb9564b4b647a2a50048b87d03c4222fb7e68d413a28309e46cc80e6fbf561`. The source manifest verifies the exact recommendation, evidence bundle and replay-report hashes. The historical run remains exploratory and does not authorize release.
- CTA/ABC/2PM model validation and CoVar utility validation are not complete.
- PR #58 remains draft and unmerged. This M5 branch is stacked on the exact M4 handoff commit; it does not merge or release M4.

## 7. Non-negotiable architecture rules

- Keep general-market and personal-squad contexts separate.
- Do not let personal squad, bank, rank or transfer state influence any future squad-independent ranking.
- Do not rebuild the recovered engine or replace source lineage.
- Do not average providers or create a consensus without separate chronological validation and an explicit weighting policy.
- Do not change provider xP values in the adapter.
- Do not blend EV, EO, covariance, risk preference or speculative CTA metrics into an unvalidated score.
- Do not claim production readiness from structural tests alone.
