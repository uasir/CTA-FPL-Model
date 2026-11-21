# M4 Joint Forecast Data Readiness Audit

## Decision

**NO CURRENT DATASET IS READY TO TRAIN OR VALIDATE A JOINT FIXTURE/Gameweek OUTCOME FORECASTER.**

The repository has useful partial sources, but none currently satisfies all of: multi-season coverage, fixture-level/player-level FPL outcome completeness, independently verified player/fixture identity, point-in-time source vintages, suitable usage rights, and enough independent Gameweeks for chronological validation.

This is a data-readiness decision, not a claim that no future data source can satisfy the requirement.

## Project-owner scope decision — 2026-11-21

The CoVar forecast path will continue using **the exact conventional forecast snapshot consumed by the M3 decision run** as its player-level expected-points/minutes anchor. M3 normalizes the external provider snapshot, preserves provider expected-points values unchanged, joins FPL metadata, and passes the resulting forecast records into the existing personal-squad engine. CoVar must bind to that same M3 `forecast_snapshot_id` and `model_version`. It must not substitute the separate exploratory official-`ep_next` baseline snapshot builder.

CTA-derived player features, predictions, covariance and provider panels are out of scope as CoVar forecast inputs for now. This does not remove or suspend the separate CTA research elsewhere in the repository.

CoVar adds portfolio-level uncertainty/dependence analysis using eligible realized FPL outcomes and independently validated statistical methods. Marginal expected points or marginal player probabilities alone do not determine a joint distribution. Until a joint scenario probability method is implemented and validated, scenario inputs remain research-only and must not be represented as calibrated model forecasts.

Accordingly, the 11footy, Wyscout and StatsBomb provider datasets are not priorities for this CoVar forecast work. The immediate data priority is a reliable realized FPL outcome panel and immutable point-in-time archives of the exact M3 provider forecast snapshots plus the FPL metadata used in each M3 decision.

## Source-by-source assessment

| Source | What it provides | Material limitation for M4 | Current permitted role |
|---|---|---|---|
| Official FPL API | Current bootstrap, fixtures, live event points/minutes, historical player summaries | Prospective source captures are only now being established; historical API rows are mutable/retrospective and do not reconstruct historical as-of forecasts. It does not provide a complete historical joint event-state archive. | Current point-in-time source capture and realized FPL scoring/replay where available |
| Existing lagged FPL panel / ridge experiments | Player-GW points/minutes targets and exploratory lagged features | Historical vintages are not fully point-in-time verified; ridge experiment is exploratory and not a calibrated joint outcome model. | Research baseline only; not a joint probability producer |
| Onside graded-predictions ledger | Actual player-GW points and an exploratory complete-case covariance panel | Player-GW aggregate outcomes do not reveal fixture-level event states; limited window and no complete pre-deadline feature/model provenance. The resulting covariance is descriptive, not a calibrated conditional joint forecast. | Descriptive covariance/stability diagnostics and a benchmark input only |
| 11footy 2026/27 | Current-season match/player stats and provisional lagged research sidecar | CC BY-NC 4.0; provisional identities remain pending; prediction-training eligibility is explicitly false; current coverage is not a multi-season verified panel. | Isolated non-commercial research and manual identity review only |
| Wyscout 2017/18 EPL | Event-level data for 380 matches, 643,150 events, plus match/player metadata | One historical season; 356 candidate FPL identities remain pending; FPL target mapping is not verified; it is not a point-in-time FPL target archive. | Provider-native CTA feature research; no FPL outcome training until identity/target mapping is independently verified |
| StatsBomb 360 pilot | One match with event/frame context | One pilot match only; not a representative historical training sample or complete FPL target panel. | Feature-pipeline engineering and human-review pilot only |
| Vaastav historical FPL archive | Historical FPL player-fixture/Gameweek rows | Retrospective data may contain revisions; code licence does not license underlying FPL data; unsuitable as proof of historical pre-deadline information. | Identity corroboration and explicitly retrospective descriptive analysis, not point-in-time forecast training |

## Consequences

1. Do not train a joint fixture-state forecaster from the current data and present it as validated.
2. Do not treat the Onside covariance matrix as a substitute for joint scenario probabilities. Covariance of aggregate player-GW points is not a complete distribution over fixture states.
3. Do not use pending 11footy/Wyscout identity candidates as verified FPL training labels.
4. Do not combine provider data across seasons until season-scoped player and fixture identity is independently verified and source-use terms are respected.
5. Do not reconstruct historical as-of forecasts from today's mutable API responses.
6. Continue prospective official FPL source capture, but recognize that a few deadline snapshots are not enough for robust model validation.
7. Keep the historical-frequency benchmark and all CoVar outputs research-only. A benchmark is not itself a learned dependency model.

## Data acquisition priorities

### Priority 1 — Preserve prospective FPL vintages

Keep capturing official public FPL source bytes before each deadline, with source hashes, observed retrieval timestamps, workflow identity and complete private archive packaging. Capture model/config/forecast bytes only when a real forecast producer has actually generated them. Never backdate source availability.

The existing public Actions artifact retention is finite and public. A durable archive requires a private user-controlled storage destination and an explicit retention/access policy. Do not place manager picks or personal squad data in public artifacts.

### Priority 2 — Establish complete realized outcome panels

A first structural builder is now implemented:
- `scripts/m4_covar_realized_fpl_dataset.py`
- `tests/test_m4_covar_realized_fpl_dataset.py`

It consumes the existing official ingestion outputs (`fpl_players.csv`, `fpl_fixtures.csv`, `fpl_player_fixture.csv`, `ingestion_report.json`, `source_metadata.json`) and emits separate player-fixture and player-Gameweek realized panels plus a manifest with hashes of all five inputs and both outputs.

The builder enforces season-scoped FPL element/fixture IDs, known player and fixture references, unique player-fixture keys, fixture/Gameweek consistency, finished non-provisional fixtures, explicit numeric outcome fields, minutes bounds, and official fixture home/away team mapping. It preserves an observed zero-minute/zero-point row, never synthesizes a missing player-fixture as zero, and sums fixture outcomes for double/triple Gameweeks.

Important limitations: the builder's structural output is **not** a completeness certification. It cannot prove that the current API history contains every historical player-fixture row, and it labels source vintage `NOT_VERIFIED_RETROSPECTIVE_OFFICIAL_API_HISTORY`. It rejects an ingestion report that is not PASS or has summary fetch errors. Its archive is designed for a new private directory outside the repository; it does not upload manager picks or personal squads.

This is a realized-outcome target archive, not a forecast archive. Keep the two roles separate. The next step is to test it in CI, then use an actual successful official ingestion artifact to assess row coverage, season/GW counts, and reconciliation against the official ingestion report before using it for dependence estimation.

### Priority 3 — Resolve CTA data rights and identity

For each non-FPL source, record source licence, permitted use, season, source hashes, identity verification status and reviewer. The 11footy CC BY-NC 4.0 restriction and pending identity records must remain explicit. Wyscout historical FPL crosswalk candidates must not be promoted automatically.

### Priority 4 — Build only after evidence coverage exists

Once eligible data exists, construct the chronological dataset by whole Gameweek clusters, then implement a transparent baseline joint distribution and an explicitly fitted dependence model. Evaluate against held-out Gameweeks with Brier/log loss, calibration, sharpness and cluster uncertainty.

## Exit criteria for this blocker

The blocker can be reconsidered only when the project can point to:
- a named, versioned dataset with permitted usage;
- complete fixture and player outcome coverage across a defensible number of independent Gameweeks;
- verified FPL identities and stable fixture mappings;
- documented point-in-time source vintages for training features;
- a separate pre-deadline forecast archive for prospective validation; and
- a chronological split and evaluation report that does not leak Gameweeks or source revisions.

## Safeguards

CoVar remains `decision_weight=0` and `production_eligible=false`. No changes are authorized to canonical recommendations, M3 EV, legality, transfer logic, frozen decisions, decision hashes or conventional M5 outputs. Free Hit remains opt-in; regular Gameweek is the default.
