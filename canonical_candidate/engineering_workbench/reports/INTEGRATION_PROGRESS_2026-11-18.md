# CTA-FPL-Model integration progress — 2026-11-18

## 1. Recommendation-system test verification

The project retains two independent recommendation systems:
- `general_market`: squad-independent market rankings. Personal squad, budget, transfer, chip, formation, rank and manager context are rejected recursively.
- `personal_squad`: manager-specific squad optimisation, with the user's squad, bank, transfers, risk profile and preferences.

Python and JavaScript boundary validators are implemented. Their shared request fixture is:
`tests/fixtures/recommendation_requests.json`.

### New parity gate
- Added `tests/js/emit_recommendation_contract_outputs.mjs`, which emits both validated request objects from the shared fixture.
- Added a Python pytest that invokes this Node runner and compares the complete Python and JavaScript outputs.
- Added a JavaScript test for the fixture's 15-player identity and FPL 2/5/5/3 composition.
- Added `workflow_dispatch` to `.github/workflows/cta-fpl-ci.yml` so the workflow can be manually started from GitHub Actions.

### Verification status — passed
Manually dispatched GitHub Actions run **44249934156** completed successfully on 2026-11-18, checking out commit `4605077618ab50151d17c74b627d24ff0eef15dd` on `main`.

Verified job and log results:
- JavaScript recommendation and engineering tests: **19 passed, 0 failed**.
- Python engineering suite: **115 passed, plus 3 subtests**. This includes the cross-language test that compares complete Python and JavaScript validated outputs from the same fixture.
- Player-identity crosswalk validator executed without errors, but returned `EMPTY_NOT_READY`, with zero verified rows and `join_ready: false`.
- Overall Actions job conclusion: **success**.

Run URL: https://github.com/uasir/CTA-FPL-Model/actions/runs/44249934156

This verifies the current recommendation request contracts and Python–JavaScript boundary parity. It does not verify production scoring parity, predictive accuracy, or a populated StatsBomb/FPL identity crosswalk.

The workflow executes Node.js recommendation tests, the complete Python pytest suite (including Python–JavaScript output parity), and the verified player-identity crosswalk validator.

Latest commits:
- Cross-language parity test: `47e841f3727fe4ce9d8b125212a37041fe197572`
- Manual dispatch enabled: `dbb273273ec6a0813904534e41be2e1f2fc0bf98`

## 2. External FPL forecast benchmark candidate: Onside Arena

Candidate dataset:
- Dataset: Fantasy Premier League — Graded Predictions Dataset, 2026/27
- CSV: https://onsidearena.com/data/graded-predictions.csv
- Dataset landing page: https://onsidearena.com/data
- DOI: https://doi.org/10.5281/zenodo.22746985
- Provider-stated licence: CC BY 4.0; attribution to Onside Arena and a link back are required.
- Provider describes one row per player per gameweek and 14 columns.
- Documented fields include `captured_at`, `deadline_utc`, Onside forecast, actual FPL points, FPL `ep_next`, recent-form and season-average baselines, and `minutes_qualified`.
- Provider states forecasts are frozen before the deadline and paired with post-deadline outcomes.

Sources inspected on 2026-11-18:
- https://onsidearena.com/data
- https://onsidearena.com/accuracy

### Integration decision
**Candidate remains unverified; ingestion is gated and it is not yet an approved benchmark input.**

Do not use Onside forecasts as training targets or silently blend them into CTA forecasts. Preserve provider forecasts as a separately named benchmark arm. Compare against FPL `ep_next` and our own baselines on identical player-gameweek rows, with explicit minutes-qualified and all-player cohorts.

### Remaining checks before ingestion
A retrieval inconsistency was found on 2026-11-18: the current search index describes the FPL graded-predictions CSV and links DOI 10.5281/zenodo.22746985, but the opened /data page currently renders a World Cup 2026 catalogue and does not expose that FPL CSV. The Zenodo record and CSV endpoints could not be retrieved through the available research tools. The public accuracy page still displays provider-reported FPL accuracy figures, but those claims do not substitute for the raw row-level ledger. Therefore the dataset's current availability, exact version and DOI contents remain unresolved. Do not assume or invent:
- the exact 14-column header and data types;
- the player identity key or whether it is the official FPL element ID;
- exact row count, gameweek coverage, historical season coverage, or current freshness;
- whether the Zenodo deposit file matches the live CSV byte-for-byte.

Next adapter gate:
1. Retrieve the CSV and Zenodo metadata; record file name, version, byte size, SHA-256, licence and retrieval timestamp.
2. Inspect exact header, nullability, numeric domains, duplicate keys and coverage.
3. Verify `captured_at < deadline_utc` for every row and exclude any invalid rows from leakage-safe scoring.
4. Resolve a stable FPL player key. Never fuzzy-join names.
5. Verify actual points and FPL `ep_next` against the official FPL source for matching player-gameweek keys.
6. Compute MAE, RMSE, calibration and rank/captain metrics on identical eligible cohorts. Keep the provider's published historical claims separate from metrics independently reproduced by this project.

## 3. Existing integration blockers remain

- Official FPL API ingestion works for all 672 rostered players and 380 fixtures; the latest verified full fetch was run 44147764850.
- Historical lagged feature outputs are structurally complete but are not point-in-time verified.
- Effective-ownership collection is implemented but still needs a live near-deadline capture and validation.
- The StatsBomb/FPL crosswalk is empty; no verified player joins exist.
- Licensed, season-aligned event features and target labels remain unresolved.
- 90-day GitHub artifacts are not durable full-season storage. A private persistent archive is still required.

No full FPL predictive integration or production recommendation engine is claimed complete.


## 4. Deadline-locked effective-ownership capture correction

A code review found that the original EO collector fetched manager picks immediately after sampling the pre-deadline rank cohort. That meant late captain, transfer and chip changes could be missed.

The collector has now been changed to a two-stage, single-run design:
1. Sample the top-10k rank cohort from official overall-league standings before the deadline.
2. Refuse to continue if the rank sampling starts or finishes after the deadline.
3. Wait until 60 seconds after the official deadline.
4. Re-fetch official bootstrap data and verify the event deadline has passed.
5. Fetch the sampled managers' picks only after that lock check.
6. Emit `CAPTURED_POST_DEADLINE_PICKS` and `picks_lock_verified: true` only on that path.

The scheduler now checks once per hour at minute 55, rather than launching 288 scheduled runs per day. It proceeds only when the official deadline is within seven minutes, then waits through the lock grace period. Manual dispatch follows the same safety checks; the legacy `force` keyword remains accepted for compatibility but cannot bypass the lock policy.

New tests cover pre-deadline rank sampling, post-deadline pick retrieval, lock timing, weighted cohort output, and out-of-window skipping.

### CI verification of this correction
- Run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44251036635
- Commit: `09d7ad1714da34a0d7a916826efa61a42e2d4c6f`
- Result: **success** (includes the scheduler change and the full test suite)
- Earlier focused run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44250932574 — **success**
- JavaScript tests: **19 passed**
- Python tests: **117 passed, plus 3 subtests**
- Crosswalk validator: executed successfully, but `EMPTY_NOT_READY`; no verified identity rows exist.

This verifies the collector's logic against mocked API responses. It is **not yet a live GW11 lock capture**. The next scheduled run near the 2026-11-21 11:00 UTC deadline is the first live validation opportunity. The capture remains a top-10k weighted sample, not whole-game EO.


## 5. Official FPL forecast baseline fields

The official ingestion adapter now preserves `ep_next` and `ep_this` from each timestamped bootstrap snapshot, alongside current form, points-per-game, expected-goals/assists, ICT, starts, bonus and related season aggregates. The ingestion report records `ep_next` coverage and missing player IDs rather than silently assuming complete coverage.

This gives the shared forecast layer an auditable official FPL baseline for the next gameweek. It is not a CTA-trained prediction and must remain labelled as the official FPL baseline. The historical lagged dataset must not backfill past `ep_next` values from a later bootstrap snapshot.

Verification:
- CI run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44251388673
- Commit: `0a48115eb3982198087ac781b358f681cd5fad44`
- JavaScript tests: **19 passed**
- Python tests: **117 passed, plus 3 subtests**
- Crosswalk validator: no errors, but `EMPTY_NOT_READY` and `join_ready: false`.


## 6. Exploratory dual recommendation engines

Both recommendation products now have deterministic Python and JavaScript implementations:

### `general_market`
- `scripts/general_market_engine.py`
- `src/js/general_market_engine.mjs`
- Overall EV ranking, position rankings, points-per-price value ranking and captaincy shortlist.
- Differential ranking is available only when EO is supplied with verified pre-deadline cohort time, sample size, post-deadline picks time, lock status and a deadline matching the forecast snapshot.
- Rejects personal squad/manager context at the request boundary.
- Never reads the personal-squad store or uses CoVar.

### `personal_squad`
- `scripts/personal_squad_engine.py`
- `src/js/personal_squad_engine.mjs`
- One-transfer alternatives with selling-price calculation, bank check, same-position constraint and maximum-three-per-team rule.
- Legal formation, starting XI, captain, vice-captain, reserve goalkeeper and ordered outfield bench.
- Hit cost is configurable in `personal_preferences.hit_cost_points`; default is the standard four points when no free transfer remains.
- Risk profile is recorded but not applied because player variance is not validated. CoVar and chip simulation remain disabled.

### Shared official FPL baseline adapter
- `scripts/build_fpl_baseline_forecast_snapshot.py` converts the timestamped official FPL player snapshot into the shared one-gameweek forecast schema.
- EV comes from official `ep_next`; expected minutes are latest completed-gameweek minutes per fixture scaled by the target gameweek's fixture count, including double gameweeks.
- Snapshot IDs hash the complete player forecast records and quality/provenance envelope, not only the bootstrap and fixture source hashes.
- `scripts/run_fpl_general_market_baseline.py` now runs the actual general-market engine on the generated official FPL snapshot and emits an exploratory ranked-market report.
- The adapter verifies the source snapshot predates the target deadline and hashes the source feeds.
- It accepts EO only when the collector report proves pre-deadline cohort selection and post-deadline picks capture for the same target deadline.
- This adapter is a baseline, not a trained CTA model.

### Latest verification
- Latest CI run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44253457191
- JavaScript: **33 passed, 0 failed**
- Python: **146 passed, plus 3 subtests**
- Crosswalk validator: **EMPTY_NOT_READY**, join_ready false.
- Live ingestion with fixture-scaled minutes and the general-market smoke test: run https://github.com/uasir/CTA-FPL-Model/actions/runs/44253510302 is currently executing; its actual forecast artifact has not yet been inspected.

These are exploratory v0.1 engines. Remaining work includes real FPL snapshot execution through the ingestion workflow, live GW11 locked EO capture, validated historical training data, multi-transfer/chip-aware planning, predictive accuracy testing and validated covariance. No production readiness is claimed.
