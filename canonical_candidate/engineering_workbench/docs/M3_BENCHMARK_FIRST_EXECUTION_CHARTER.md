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


### M3.2 — First end-to-end personal-squad execution slice

Added:
- `scripts/canonical_forecast_recommendation_adapter.py`
- `scripts/run_external_benchmark_personal_squad.py`
- `tests/test_canonical_forecast_recommendation_adapter.py`
- `tests/test_run_external_benchmark_personal_squad.py`

The runner accepts one raw provider snapshot, a separately captured FPL player-metadata table, and explicit manager context. It normalizes and checks the provider snapshot, joins metadata by FPL element ID, then calls the existing `recommend_personal_squad` engine. It emits one provenance-bearing personal-squad decision object with transfer recommendation, legal formation/XI, bench, captain and vice-captain, plus explicit release blockers.

Additional time controls require provider generation no later than capture, capture before deadline, and the decision timestamp strictly before deadline. Diagnostic-only snapshots are rejected. Fixture-grain forecasts are not silently aggregated. Provider xP values are passed through unchanged.

**CI evidence:** run [44754038796](https://github.com/uasir/CTA-FPL-Model/actions/runs/44754038796) passed on the current branch head: 272 Python tests passed, 3 subtests passed, JavaScript contract tests passed, and all four identity-crosswalk validation steps passed.

This is a tested execution interface, not yet a live provider integration or a release-ready recommendation. The integration tests use deterministic synthetic provider fixtures. A real decision run still requires a captured, eligible provider snapshot, current FPL metadata and the manager's timestamped 15-player squad state. The output is deliberately marked not release-eligible until M3 acceptance and decision backtesting are complete.


### M3.2a — FPL Cat live-capture adapter

Added:
- `scripts/capture_fpl_cat_snapshot.py`
- `tests/test_capture_fpl_cat_snapshot.py`

The collector requests FPL Cat's documented public next-gameweek JSON endpoint and the official FPL bootstrap-static endpoint. It records the raw response hashes and capture timestamps independently, maps FPL Cat element IDs to the matching FPL bootstrap player metadata, checks that both sources agree on the target GW deadline, and refuses post-deadline captures, missing expected minutes, duplicate IDs or unmapped player IDs. Provider xP and expected minutes remain sourced from FPL Cat; price, position and team ID remain sourced from the separate FPL metadata snapshot.

The decision runner now requires and carries metadata-source provenance as well as provider-source provenance, and rejects metadata snapshots captured at or after the deadline. The collector is invoked with `python scripts/capture_fpl_cat_snapshot.py --season 2026-27 --output <path>`; its output can be combined with the timestamped manager context for the decision runner.
The capture bundle now includes base64-preserved raw provider and FPL bootstrap response bytes, allowing exact byte-for-byte hash verification after archival. A manual GitHub Actions workflow, `.github/workflows/capture-fplcat-benchmark.yml`, captures the bundle and uploads it as a 90-day artifact for inspection and replay. If FPL Cat does not disclose `computed_at`, the collector now retains the snapshot with a null generation timestamp and explicit `NOT_DISCLOSED_DIAGNOSTIC_ONLY` status; the canonical contract then prevents it from entering a strict recommendation run. The collector also rejects official FPL metadata retrieved at or after the deadline.

Regression tests cover missing generation timestamps and post-deadline metadata capture. The live capture has produced a real 672-row GW11 FPL Cat snapshot; a successful manager-backed recommendation run remains pending.

### M3.3b — GW1 purchase-price fallback hardening

The first live manager-history attempt confirmed that the GW11 picks endpoint returns HTTP 404 before the deadline and exposed a real data-shape gap: the GW1 picks response did not contain a usable `purchase_price` for player ID 496. The implementation now falls back only for missing GW1 purchase prices to the official bootstrap's season-start cost, calculated as `now_cost - cost_change_start`. That bootstrap response is archived with the other raw manager-history inputs. If neither source yields a positive integer cost, capture still fails closed.

Regression coverage now includes missing GW1 purchase-price fallback, full raw-source archive integrity and the previous transfer-history cases. CI run [44762964953](https://github.com/uasir/CTA-FPL-Model/actions/runs/44762964953) passed: 39 JavaScript tests, 301 engineering pytest tests, 3 subtests, canonical Python tests and all four identity crosswalk checks.

This is code-level verification only. The live manager capture has not yet succeeded; the workflow needs another run to validate the fallback against team 421025's actual bootstrap and transfer data.

### M3.3c — Prior-gameweek purchase-price preference

To avoid relying on season-start prices when an exact prior snapshot exists, the pre-deadline fallback now first fetches the immediately preceding GW picks endpoint. It uses those recorded purchase prices only when all 15 player IDs exactly match the user-confirmed GW11 squad and the previous gameweek was not a Free Hit. The previous-GW raw response and manager history are archived. If the identity check fails, the capture falls back to the GW1/transfer-history reconstruction with bootstrap-derived prices only for missing initial values. This uses the GW10 record corresponding to the manager-history URL supplied by the user, without assuming that GW10 and GW11 squads match.

CI run [44763403031](https://github.com/uasir/CTA-FPL-Model/actions/runs/44763403031) passed: 39 JavaScript tests, 302 engineering pytest tests, 3 subtests, canonical Python tests and all four identity crosswalk checks. The live manager capture for team 421025 still needs to be rerun to confirm which source path is selected and validate all 15 prices.

### M3.3a — Manager context and purchase-price reconstruction

The GW11 public picks endpoint can return HTTP 404 before the deadline. The pre-deadline path now preserves the user's confirmed GW11 15-player IDs, bank and free-transfer count while reconstructing the purchase prices independently from the season record:
- GW1 official manager picks provide the initial 15 holdings and their recorded purchase prices.
- The public season transfer log provides each transfer's incoming player and recorded incoming cost.
- Transfers are applied chronologically; a sold-and-rebought player receives the later transfer-in cost.
- Transfers made in a free-hit gameweek are excluded from the permanent squad state.
- The reconstructed 15 IDs must exactly match the user-confirmed GW11 squad. Missing, malformed or inconsistent history is a hard failure.
- The GW11 bank and free transfers remain explicitly user-confirmed inputs; historical GW1/GW10 bank values are never substituted.
- The raw GW1 picks, transfer log and manager history are archived together, hashed and carried into the assembled decision input as manager-context provenance.
- The assembler now rejects missing purchase prices instead of substituting current market prices, and it preserves the purchase-price source metadata.

LiveFPL's save-history page is useful for an independent week-by-week history cross-check, but the page currently advertises a 2025/26 Excel history export. It is not treated as a machine-readable 2026/27 purchase-price endpoint. For the current 2026/27 GW11 price reconstruction, the implementation uses the documented public FPL season-start picks and transfer-history records. A LiveFPL export can be added as a separate cross-check when a current-season file is available.

**Verification:** CI run [44762298925](https://github.com/uasir/CTA-FPL-Model/actions/runs/44762298925) passed after the JSON-list transfer-history parser fix: 300 engineering pytest tests passed, 3 subtests passed, 39 JavaScript tests passed, and all four identity crosswalk checks passed. This verifies the code and fixtures, not yet the live manager-history response for team 421025.


### M3.3d — User-confirmed GW11 squad snapshot

On 2026-11-20, the manager explicitly supplied and confirmed the GW11 squad for team 421025, including the distinction between starters and bench. The authoritative 15-player identity set is:
- Goalkeepers: Rushworth (110), Dubravka (497).
- Defenders: Konsa (31), Calafiori (8), De Cuyper (115), Tarkowski (229), Giles (282).
- Midfielders: Palmer (154), Groß (124), B. Fernandes (426), Rudoni (183), Olusesi (524).
- Forwards: N. Jackson (166), Evanilson (79), Haaland (411).

The user's baseline selection is 4-3-3: starters Rushworth; Konsa, Calafiori, De Cuyper, Tarkowski; Palmer, Groß, B. Fernandes; N. Jackson, Evanilson, Haaland. Bench order: Dubravka, Giles, Rudoni, Olusesi. Haaland is captain and Palmer vice-captain. Bank is £0.9m and free transfers are 1.

This is a user-confirmed current squad/lineup snapshot, not a claim that the pre-deadline official GW11 picks endpoint is accessible. The workflow's expected 15 FPL element IDs already match this confirmation. Prior-GW picks and transfer history may supply purchase-price evidence only; they do not override the user-confirmed current squad. The engine's recommended XI, bench and captaincy remain decision outputs and must not be confused with this baseline selection. No recommendation is released by recording this input.



### M3.3e — First live decision run and post-transfer squad-plan correction

Live workflow run [44764165317](https://github.com/uasir/CTA-FPL-Model/actions/runs/44764165317) completed successfully before the GW11 deadline:
- FPL Cat snapshot: 672 forecast rows and 672 official FPL metadata rows; provider generation 2026-11-20T15:25:07.256Z, capture 2026-11-20T15:31:50.686Z, deadline 2026-11-21T11:00:00Z.
- Manager context: 15 rows; user-confirmed GW11 IDs exactly matched the official GW10 picks IDs. The GW10 picks response contained no purchase_price fields, so the implementation correctly used the season-history reconstruction path instead of treating GW10 as price evidence.
- Purchase-price reconstruction: the current squad's 15 costs were populated from official transfer-in costs where available and season-start costs for initial holdings; Free Hit GW9 transfers were excluded. The archived manager source bundle decoded successfully and its SHA-256 matched the recorded hash.
- Decision input assembled and one conventional FPL Cat personal-squad run completed. The output remains exploratory-only and release-ineligible.

The first output exposed an integration defect: the transfer optimiser selected a transfer but the returned squad plan still described the pre-transfer 15-player squad. In this live run it recommended Callum Olusesi (524) out for Diego Gómez (127), but the original bench still contained Olusesi. The output was therefore not coherent enough to deliver as an actionable recommendation.

The Python and JavaScript personal-squad engines have now been corrected in commit series ending at [689fe6b](https://github.com/uasir/CTA-FPL-Model/commit/689fe6be180631576a4039514d466390bca8b89d). Outputs now preserve `current_squad_plan` as the pre-transfer baseline and set `squad_plan` to a re-optimised legal plan for the post-transfer 15-player squad when action is TRANSFER. HOLD retains the current squad plan. A regression test asserts the outgoing player is absent and incoming player present in the recommended plan.

**CI verification:** [run 44764930307](https://github.com/uasir/CTA-FPL-Model/actions/runs/44764930307) passed: 39 JavaScript tests, 302 Python engineering tests, 3 subtests, and all four identity crosswalk checks.

A fresh live workflow execution is still required to generate the corrected post-transfer recommendation artifact. No recommendation is released until the updated live output and remaining M3 acceptance gates are checked.


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
