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

### Verification status — not yet confirmed
The GitHub connector's commit-status endpoint returned an empty status list for the recent recommendation commits, including the latest CI-workflow update. Its workflow-run lookup only returns pull-request-triggered runs, and no tool is exposed here to list push-triggered workflow runs or dispatch a workflow. Therefore this report does **not** claim that the latest CI passed.

To obtain a definitive run:
1. Open https://github.com/uasir/CTA-FPL-Model/actions
2. Select **CTA FPL engineering CI**.
3. Choose **Run workflow**, branch `main`, then run it.
4. Share the resulting run URL. With its run ID, job summaries and logs can be retrieved and any failures fixed.

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
**Candidate accepted for evaluation as an external forecast benchmark only; ingestion is gated.**

Do not use Onside forecasts as training targets or silently blend them into CTA forecasts. Preserve provider forecasts as a separately named benchmark arm. Compare against FPL `ep_next` and our own baselines on identical player-gameweek rows, with explicit minutes-qualified and all-player cohorts.

### Remaining checks before ingestion
The downloadable CSV and DOI record have not yet been retrieved and inspected in this environment. Consequently, do not assume or invent:
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
