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
