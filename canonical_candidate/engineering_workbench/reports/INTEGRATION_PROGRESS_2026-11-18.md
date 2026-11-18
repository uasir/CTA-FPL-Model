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

## 2. External FPL forecast benchmark: Onside Arena — source and target reconciliation passed

Candidate dataset:
- Dataset: Fantasy Premier League — Graded Predictions Dataset, 2026/27.
- CSV: https://onsidearena.com/data/graded-predictions.csv
- DOI: https://doi.org/10.5281/zenodo.22746985
- Provider-stated licence: CC BY 4.0; attribution to Onside Arena with a link to onsidearena.com.
- The provider describes one player-gameweek row with a pre-deadline forecast, official FPL `ep_next`, actual FPL points, recent-form and season-average baselines, and a minutes-qualified flag.

### Real-source audit — passed

The source was fetched and inspected by the new GitHub Actions workflow:
- Latest run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44257909685
- Artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44257909685/artifacts/14407050697
- Artifact ID: `14407050697`; retained until 2027-02-16.
- Source SHA-256: `dd51366a5f71d5f0bf26b4265b17188f04774d584c4444172be3f307aaf02a81`.

Verified:
- 5,450 rows and 14 columns.
- 5,450/5,450 rows have `captured_at < deadline_utc`.
- 5,450/5,450 row deadlines exactly match the official FPL event deadlines.
- 608 unique `player_id` values; 608/608 match official FPL `element` IDs, not `player_code`.
- Zero duplicate player-gameweek keys.
- 4,954 populated actual-points rows match official FPL event-live `total_points` exactly; zero mismatches.
- The other 496 rows have blank actual points and belong to gameweeks the official API still marks unfinished. No finished gameweek has an ungraded row.

### Independently recomputed exploratory benchmark

On the same 4,954 scored rows:
- All scored rows: Onside MAE 1.681 / RMSE 2.577; provider-supplied frozen FPL `ep_next` MAE 1.600 / RMSE 2.651.
- Minutes-qualified cohort (2,045 rows): Onside MAE 2.515 / RMSE 3.530; FPL `ep_next` MAE 2.685 / RMSE 3.765.

These are project calculations from the downloaded ledger, not an endorsement of the provider's wider four-season accuracy claims. All-player and minutes-qualified cohorts answer different questions and must remain separate. The historical `fpl_ep_next` values are supplied by Onside; the current official FPL API cannot independently recreate their exact historical vintages.

### Integration decision and guardrails

**Approved as a separate external FPL forecast benchmark only.** It is not a source of event-derived CTA features and does not clear the StatsBomb/Wyscout/Opta player-event integration blockers.

- Preserve Onside forecasts as a separate benchmark arm.
- Do not train CTA on Onside predictions or blend them into CTA forecasts.
- Compare Onside and official FPL `ep_next` on identical player-gameweek rows and identical eligibility cohorts.
- Preserve CC BY 4.0 attribution in any published report.
- Keep the raw CSV in the workflow artifact, not the public Git history.
- Do not treat this result as CTA predictive validation or as proof that the project's own FPL forecast is calibrated.

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

The scheduler checks twice per hour at minutes 25 and 55, matching the current :30 and :00 deadline cadence without launching 288 scheduled runs per day. It proceeds only when the official deadline is within seven minutes, then waits through the lock grace period. Manual dispatch follows the same safety checks; the legacy `force` keyword remains accepted for compatibility but cannot bypass the lock policy.

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


## 7. Live official FPL → baseline forecast → general-market integration

A full live ingestion and baseline ranking run completed successfully:

- Latest full Actions run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44255361502
- Commit: `8d1c4e42f6529cd9886fa781a7be3bacfac4ae5d`
- Artifact: `cta-fpl-official-44255361502` (ID `14405672773`)
- Artifact download: https://github.com/uasir/CTA-FPL-Model/actions/runs/44255361502/artifacts/14405672773
- Artifact expiry: 2027-02-16 06:59:09 UTC.
- Forecast snapshot ID: `eba3236337a3288221a0b22aa90bf7a48f8633e09cb973c1eefadd221fae1f82`.
- Captured at 2026-11-18 07:00:47 UTC.

### Official feed integrity
- Season: 2026/27; target GW11.
- 672 players; 380 fixtures; 6,562 player-fixture rows.
- All 672 player summary requests succeeded; zero summary fetch errors.
- All 672 players have official `ep_next` and `ep_this` values.
- 459 players have positive season minutes.
- No orphan fixtures, unknown IDs, minute reconciliation mismatches or total-points reconciliation mismatches.

### Forecast snapshot
- 672/672 player forecasts built; no missing `ep_next`, invalid player rows or missing minutes history.
- 10 target-GW fixtures counted; target fixture counts are used to scale latest completed-GW minutes per fixture.
- The snapshot was captured **75.987 hours before the GW11 deadline**. It is marked `STALE_OVER_24H`; the recommendation status remains `EXPLORATORY_ONLY`. The scheduled daily ingestion should produce a fresh pre-deadline snapshot on deadline day.

### General-market engine live smoke test and Python–JavaScript parity
- Python and JavaScript general-market outputs are **exactly numerically equal** across the full 672-player pool and all output categories.
- Parity report: `PASS_PYTHON_JAVASCRIPT_PARITY`; artifact contains the Python output, JS output and comparison report.
- Status: `PASS_EXPLORATORY_GENERAL_MARKET`.
- All 672 players ranked.
- The current official `ep_next` top five were N. Jackson (11.0), Konsa (10.7), Gabriel (10.3), Barry (9.0) and Evanilson (8.0).
- Top value by expected points per £m began with Konsa, Barry and N. Jackson.
- No EO was present in this snapshot, so no differential ranking was produced.
- CoVar was not used.

This is the first verified end-to-end FPL data-to-general-market execution. It is **not** a validated CTA prediction: the points baseline is FPL's own `ep_next`, minutes are a proxy, the snapshot is stale, and the historical lagged training report remains `PASS_STRUCTURAL_ONLY` with `point_in_time_status: NOT_VERIFIED`.

The live EO capture remains outstanding for GW11. Its scheduler now checks five minutes before both `:00` and `:30` deadlines, based on the actual FPL deadline calendar, and only fetches picks after the deadline lock.


## 8. Live-pool personal-squad scale test

The personal-squad engine was also executed against the same 672-player official forecast pool using a clearly labelled synthetic legal 15-player squad:

- Actions run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44255361502
- Artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44255361502/artifacts/14405672773
- Status: `PASS_SYNTHETIC_PERSONAL_SQUAD_SCALE_SMOKE_TEST`.
- 672 forecast players; 15-player synthetic squad; £62.1m squad cost; £37.9m bank; maximum two players per team.
- Built a legal 4-3-3, 11-player starting XI, captain, vice-captain and bench.
- Evaluated 2,914 legal one-transfer candidates.
- The smoke test deliberately used a synthetic squad and is **not** a real manager recommendation.
- Risk profile and CoVar remained unapplied; recommendation status remained exploratory.

The user's current manager-specific squad has not been supplied to this run, so no real personal-squad advice has been generated.


## 7. Standard effective-ownership definition corrected

PR #5 was merged on 2026-11-18 (merge commit `090cb01f5a3bf6668612e589ebad3f28ae5da4cd`).

A review found that the previous estimator counted bench picks as owned only during Bench Boost. This understated standard ownership and EO. The estimator now separates:
- `owned_by_pct`: all 15 squad selections, including the bench.
- `starting_pct`: positions 1–11.
- `effective_ownership_pct`: all 15 squad selections plus one captain extra and one additional Triple Captain extra.
- `scoring_exposure_pct`: starting XI, Bench Boost bench players, captain extra and Triple Captain extra.

The existing captain and Triple Captain multipliers remain. Bench Boost affects scoring exposure, not squad ownership or standard EO.

CI: https://github.com/uasir/CTA-FPL-Model/actions/runs/44259359716 — success; 165 Python tests and 3 subtests passed. This corrects the metric definition; it does not establish a live rank-tier EO capture.

## 8. FPL workflow execution mode and data-source caveats

PR #6 originally added a repository Actions variable gate. Following the user's explicit engineering instruction not to wait for permission unless it is a genuine technical prerequisite, PR #9 removed that gate on 2026-11-18 (merge commit `68df00ae83eb6eb7129fbe7ac7834a5751e73794`).

The following workflows are now schedule/dispatch eligible without `FPL_DATA_PERMISSION_CONFIRMED`:
- Official FPL ingestion and Python–JavaScript general-market parity.
- Pre-deadline ranked-manager EO capture, with its deadline/lock checks unchanged.
- Onside benchmark audit and its official-FPL reconciliation step.

This is an execution-policy change, not a finding that the data terms grant permission. Public API availability and private/non-commercial use do not by themselves establish a licence. Continue with low request rates, preserve source/provenance records, and treat any concrete technical denial, throttling, or access failure as a technical blocker to diagnose—not as a reason to disable unrelated engineering.

### Verification after PR #9
- Main CI: https://github.com/uasir/CTA-FPL-Model/actions/runs/44288397079 — **success** on commit `68df00ae83eb6eb7129fbe7ac7834a5751e73794`.
- JavaScript contract tests: **37 passed, 0 failed**.
- Python engineering tests: **172 passed**, plus 3 subtests.
- StatsBomb, Wyscout and Opta/PulseLive validators all executed; Wyscout and Opta/PulseLive remain `EMPTY_NOT_READY` with `join_ready: false`.
- The CI test run produced no workflow artifacts; it validates the merged code and contracts, not a new live FPL ingestion or EO capture.

The Actions connector available in this engineering session exposes run inspection and rerun operations but no workflow-dispatch operation. Therefore, no manual dispatch is claimed here. The workflows remain scheduled: official ingestion daily at 05:30 UTC, EO checks at minutes 5 and 35 each hour with a 35-minute pre-deadline window and 45-minute timeout, and Onside audit Sundays at 12:17 UTC. The scheduled ingestion and both live-pool parity checks are verified in run 44324401400; a successful deadline-locked EO capture remains outstanding.

### Live official FPL ingestion and Python–JavaScript parity — verified 2026-11-18

Scheduled run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44324401400  
Artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44324401400/artifacts/14436735723  
Artifact ID: `14436735723`; SHA-256: `a4a2a8b8deae2009e80958e79b8ee38a4392a7397da7436f54ff1fab2608269f`.  
Commit: `d9f3f4a61525ae4b3bacd358f50a3c7cec5ce4e3`; fetched at 2026-11-18 14:28:47 UTC.

**Official feed integrity**
- 2026/27 season; target GW11; 672 unique players and 380 fixtures.
- 672/672 element-summary requests succeeded; zero summary fetch errors.
- 6,562 player-fixture rows; no orphan fixtures, unknown player IDs, minute mismatches or total-points mismatches.
- All 672 players have official `ep_next` and `ep_this` values.
- 459 players have positive season minutes.

**Engine execution**
- Python and JavaScript general-market outputs matched exactly over all 672 forecast players: `PASS_PYTHON_JAVASCRIPT_PARITY`.
- Python and JavaScript personal-squad outputs matched exactly on the same 672-player forecast pool: `PASS_PERSONAL_SQUAD_PYTHON_JAVASCRIPT_PARITY`.
- The personal-squad test used a synthetic legal 15-player roster, built an 11-player XI, and evaluated 2,914 legal one-transfer candidates. It is a scale/parity test, not the user's actual squad.
- Both engines remain `EXPLORATORY_ONLY`; CoVar was not used.

**Model and data limitations**
- Official `ep_next` is the points baseline, not a CTA-trained prediction.
- Expected minutes are a proxy based on latest completed-GW minutes per fixture, scaled to target fixture count.
- EO coverage in the GW11 snapshot is zero; no differential ranking is available.
- The historical lagged table has 6,562 rows for GW1–GW10 but point-in-time status remains `NOT_VERIFIED` because current API history may contain retrospective revisions.
- Ridge exploratory holdout: points MAE 1.2016 versus 1.1855 for the baseline (worse); RMSE 2.0157 versus 2.1513 (better). Minutes MAE 15.375 versus 11.099 (worse). Decision remains `DO_NOT_PROMOTE`; the model is not connected to either recommendation engine.
- The covariance run used 10 gameweeks, with 420 players in its complete-case, non-zero-variance matrix; the point-in-time caveat remains. CoVar stays disabled.

### Live EO scheduler verification — no capture yet

Run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44342865582  
Artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44342865582/artifacts/14444142532

The scheduled job itself completed successfully, but the collector returned `SKIPPED_OUTSIDE_DEADLINE_WINDOW`: GW11 deadline was 2026-11-21 11:00 UTC and the run began roughly 4,015.77 minutes beforehand. The 324-byte artifact contains only the skip report; **no manager cohort, picks or EO rows were captured**.

To improve the chance of a real near-deadline run despite GitHub's best-effort scheduler, the EO workflow is now scheduled about 20 minutes before the observed :00/:30 deadline cadence, accepts a 35-minute pre-deadline window, and allows a 45-minute job timeout. The collector's safeguards remain: cohort capture must finish before deadline; picks are requested only after the deadline plus 60 seconds and a fresh official bootstrap confirmation.

## 10. Exploratory CoVar baseline from Onside actual points

PR #7 was merged on 2026-11-18 (merge commit `0299f37139d2ef39c1da63de2470e1f2e92e1075`).

A reproducible workflow now uses only the provider's realized `actual_points` field from its CC BY 4.0 graded-predictions ledger. It ignores both Onside and official FPL forecast columns, excludes unfinished/partially graded gameweeks, and never zero-fills missing player-gameweek rows.

Latest successful run:
- CoVar calculation: https://github.com/uasir/CTA-FPL-Model/actions/runs/44259763220
- Artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44259763220/artifacts/14407138593
- Source SHA-256: `dd51366a5f71d5f0bf26b4265b17188f04774d584c4444172be3f307aaf02a81`.

Results for GW1–GW10:
- 605 players appear in the ledger.
- 350 have a complete 10-GW panel.
- 255 are excluded for incomplete panels; no missing score is filled with zero.
- 54 complete-panel players have zero variance and are excluded from the covariance matrix.
- 296 players remain in the covariance matrix, producing 43,956 pairwise estimates including the diagonal.
- With 50% off-diagonal shrinkage, the resulting matrix is positive definite in this sample; the unshrunk rank upper bound is 9 for 296 players.

This is a useful first real-data CoVar diagnostic, not a stable risk model. Ten rounds are too few for reliable dependence estimates, and the complete-case cohort is selected toward players with repeated appearances in the provider ledger. The provider-stated CC BY 4.0 licence is recorded, but the underlying rights chain for FPL-derived data has not been independently cleared. Do not enable CoVar in `personal_squad`; wait for longer data history, source permission, and time-ordered/out-of-sample validation.

CoVar workflow CI: https://github.com/uasir/CTA-FPL-Model/actions/runs/44259735610 — success.


### CoVar stability diagnostic — failed stability screen

PR #8 was merged on 2026-11-18 (merge commit `db7eed7241ef91319630e705edbff64e8dc5e3e6`). The workflow now compares pairwise player correlations across GW1–GW5 and GW6–GW10 for players with non-zero variance in both halves.

Run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44260264105  
Artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44260264105/artifacts/14407094178

On the same 260-player, 33,670-pair comparison:
- Correlation between the first-half and second-half pairwise correlation vectors: **0.0078**.
- Median absolute pairwise-correlation change: **0.5004**.
- Mean absolute pairwise-correlation change: **0.5780**.

This is not a formal stationarity test (each half contains only five gameweeks), but it is a strong warning that the observed pairwise relationships are not stable enough to drive team selection. The covariance matrix being positive definite after shrinkage is a mathematical property, not evidence that its estimates are reliable. CoVar remains disabled in `personal_squad`.


## 11. Original source archive recovery

The five original recovery archives are present locally, pass ZIP integrity checks, and match the hashes recorded in the 2026-11-15 project state:

| Archive | SHA-256 | Entries |
|---|---|---:|
| `CTA_FPL_reconstruction_scaffold_v0_1.zip` | `b96b6e3c3ef04b4e12d5d153f4f381843f4ecc2e48f0ae54d41d4ec14c1d6dc1` | 20 |
| `CTA-FPL-Engineering-Workbench.zip` | `b7e62bec4299a63fb06d72e7bc38f54f2726ea68f366a29b4e3f64607f6e4630` | 44 |
| `CTA_FPL_Model_v1_0_2_Engineering_Build.zip` | `7c8960ef250472eb2bb57b3d82f4ebec8dec00096482307470aedecb40cf5a73` | 15 |
| `CTA_FPL_Model_v1_0_1_Engineering_Fix.zip` | `2c000b3c3f84bf1197303013d0d21e402b01d8ebfbddef3aa6558cfc50ab7553` | 21 |
| `CTA_FPL_Model_v1_0_Experimental.zip` | `2d8278b593165b2bad7d55ee50969d166070e8872288a7fc59d07976ae17d749` | 11 |

The 2026-11-17 independent workspace and 2026-11-15 candidate bundle are additional working snapshots, not replacements for those five originals. Their ZIP hashes are respectively `c482a282466e36d6eaa8f42f724e0103a29390954b2342d64a855714b6abb7c4` and `ad4334228574ccfcc4bdfb6d3d4f7160a680837d58b92147d63b88ecda8b6305`; both also pass ZIP integrity checks.

The v1.0.2 source and Workbench are separate components. The later independent workspace contains additional experimental changes, including match-scoped 360 UUID auditing. The current repository's v1.0.3 engine is not byte-identical to that later local snapshot. Preserve all archives unchanged; port improvements selectively with tests rather than replacing the canonical engine wholesale.
