# M3 Execution Charter — Benchmark-First Decision Engine

**Status:** M3 ACTIVE — first provider-contract slice implemented; validation pending  
**Started:** 2026-11-20  
**Execution relationship:** M2 model validation continues independently in parallel. M3 does not wait for ABC/2PM promotion because its initial forecast inputs are the agreed external FPL benchmark providers.

## 1. Agreed execution decision

The downstream recommendation system will be built using the actual external FPL benchmark forecasts first. Once the project's own model passes M2's validation and promotion gates, it will enter through the same canonical forecast interface and can replace or supplement benchmark inputs.

This execution decision supersedes the earlier architecture wording that deferred all M3 implementation until M2 was complete. The five milestones remain distinct and controlled:
- M1 verification continues on its separate schedule.
- M2 model-layer validation continues independently.
- M3 implementation starts now and must pass its own acceptance gates.
- M4 begins after M3 is accepted.
- M5 begins after M4 is accepted.

M3 does not consume unvalidated ABC/CTA or 2PM outputs. M2 research status is carried as metadata and cannot affect benchmark forecast eligibility.

## 2. Existing assets reused

The repository already contains exploratory v0.1 Python and JavaScript engines:
- `scripts/recommendation_contracts.py`
- `scripts/general_market_engine.py`
- `scripts/personal_squad_engine.py`
- `src/js/recommendation_contracts.mjs`
- `src/js/general_market_engine.mjs`
- `src/js/personal_squad_engine.mjs`

These engines are not replaced. M3 extends them with the canonical external-provider input boundary and stronger decision validation. Existing Python/JavaScript parity and squad-legality tests remain regression requirements.

## 3. M3 first implementation slice

Added:
- `scripts/canonical_provider_forecast_contract.py`
- `tests/test_canonical_provider_forecast_contract.py`

The contract:
- requires explicit provider, product and variant identity;
- preserves season, target GW, forecast grain, snapshot ID, source URL, raw hash and source snapshot ID;
- validates provider-generation, retrieval and official deadline timestamps;
- rejects captures at/after deadline and provider generation at/after deadline;
- marks snapshots without a disclosed provider-generation timestamp diagnostic-only and not decision-eligible;
- preserves player-fixture rows and refuses implicit DGW aggregation;
- validates unique forecast keys, finite numeric values, probability bounds and row-count coverage;
- preserves coverage and missingness instead of inventing values.

This means FPL Lucho served xP cannot silently become Odds xP, and Sideline Quant fixture rows cannot be treated as player-GW values without a separately specified aggregation step.

## 4. M3 work packages

### M3.1 — Provider-neutral forecast contract
- Complete Python contract and regression tests.
- Add equivalent JavaScript schema/parity handling only after the Python contract is stable.
- Add provider adapters that map captured raw snapshots into the canonical contract without changing the source values.
- Support each provider variant as a distinct input.

### M3.2 — Benchmark-backed decision runs
- Connect eligible provider snapshots to the existing general-market and personal-squad engines.
- Keep each provider/variant as a separately addressable decision run.
- Do not create an arbitrary average or consensus. A consensus requires its own chronological validation and documented inclusion/weighting policy.
- Ensure a snapshot without provider generation time is excluded from strict deadline recommendations, while retained for diagnostic comparison.

### M3.3 — Personal squad decision integrity
- Validate timestamped 15-player squad state, bank, free transfers, selling prices, positions, team limits, formation and bench rules.
- Produce legal transfers, hold/roll, XI, bench, captain and vice-captain.
- Add deterministic replay, boundary tests and decision explanations.
- Extend beyond one transfer only after single-transfer correctness is accepted.

### M3.4 — Decision evaluation
- Use only forecast snapshots actually captured before each deadline.
- Score exact matched player-GW and decision cohorts.
- Evaluate realized squad points, transfer opportunity cost and decision regret.
- Record provider-specific results; no provider is promoted by website visibility or isolated headline metrics.

## 5. M3 acceptance gates

M3 is not accepted until:
1. Canonical input records preserve provider/variant/source/time/grain provenance.
2. Only deadline-eligible snapshots can enter strict decision runs.
3. Forecast coverage and missingness are visible; no missing value becomes zero.
4. Personal-squad actions pass FPL legality tests, including budget, selling price, position, three-per-team, formation and bench constraints.
5. General-market outputs are invariant to personal squad data.
6. Identical frozen inputs produce deterministic outputs and exact source traceability.
7. Provider-specific decision runs and backtests use the same eligible cohort rules.
8. M3 limitations and non-validated fields are carried into outputs.

Passing software tests alone does not establish forecast accuracy or guarantee rank improvement.

## 6. Interfaces to M4 and M5

M3 output must expose a versioned decision object with:
- chosen provider and exact variant;
- immutable forecast snapshot IDs and hashes;
- target GW and deadline;
- manager squad snapshot ID when personal mode is used;
- legal transfers, hold/roll, XI, bench, captain and vice-captain;
- expected-points basis and limitations;
- validation/eligibility state and warnings.

M4 will later enrich this decision with the existing LiveFPL EO field reference and validated portfolio context. M5 will publish the three separate recommendation products. Neither M4 nor M5 is implemented in this M3 branch.

## 7. Model transition

When M2 approves ABC/CTA or 2PM, it is registered as another provider under the same canonical schema. Benchmark and project-model runs remain side-by-side during a shadow period. Replacement or supplementation requires recorded evidence and a rollback path; historical releases are never rewritten.
