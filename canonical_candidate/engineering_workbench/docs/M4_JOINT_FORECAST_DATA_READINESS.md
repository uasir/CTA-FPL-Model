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

The builder enforces season-scoped FPL element/fixture IDs, known player and fixture references, unique player-fixture keys, fixture/Gameweek consistency, finished fixtures, explicit numeric outcome fields, minutes bounds, and official fixture home/away team mapping. It preserves the official `finished_provisional` flag instead of silently dropping completed fixtures marked provisional. It preserves an observed zero-minute/zero-point row, never synthesizes a missing player-fixture as zero, and sums fixture outcomes for double/triple Gameweeks.

Important limitations: the builder's structural output is **not** a completeness certification. It cannot prove that the current API history contains every historical player-fixture row, and it labels source vintage `NOT_VERIFIED_RETROSPECTIVE_OFFICIAL_API_HISTORY`. If any fixture is marked `finished_provisional`, the manifest sets `outcome_finality_status=REQUIRES_FINALITY_RECONCILIATION`; those outcomes must be checked against later official final scoring before being treated as ground truth. It rejects an ingestion report that is not PASS or has summary fetch errors. Its archive is designed for a new private directory outside the repository; it does not upload manager picks or personal squads.



#### Existing official ingestion artifact assessed (2026-11-18)

The successful official ingestion artifact from [Actions run 44357649202](https://github.com/uasir/CTA-FPL-Model/actions/runs/44357649202) was inspected. Its ingestion report is `PASS`: 672/672 element summaries fetched, 380 fixtures in the season feed, 100 completed fixtures across GW1–GW10, 6,562 player-fixture rows, no orphan fixture rows, no missing summaries for players with minutes, and zero player season-total minutes/points reconciliation mismatches. Independent structural inspection found 6,562 unique player-Gameweek keys (no repeated player-GW keys in GW1–GW10), 52–79 player rows per completed fixture, both home/away sides represented in all 100 fixtures, and all 672 players represented by GW10.

The artifact's 100 completed fixtures all have `finished_provisional=true`. The builder therefore retains those rows but flags `outcome_finality_status=REQUIRES_FINALITY_RECONCILIATION`; this dataset is **not yet accepted as final ground truth**. The existing Onside cross-audit (run 44357104115) independently matched 4,954/4,954 overlapping player-Gameweek points rows exactly, but 1,608 official rows have no Onside counterpart. This supports point accuracy for the overlap only; it does not settle finality for all rows or establish point-in-time vintage.

The artifact is a retrospective 2026/27 snapshot retrieved 2026-11-18 17:22:33 UTC. It contains no historical pre-deadline M3 forecast snapshots and cannot be used to reconstruct those forecasts.

A separate reconciliation adapter is now implemented:
- `scripts/m4_covar_realized_fpl_finality_audit.py`
- `tests/test_m4_covar_realized_fpl_finality_audit.py`

It compares each supplied player-Gameweek aggregate against the corresponding official `event/{event_id}/live` response across minutes, points, goals, assists, clean sheets, goals conceded, own goals, penalties, cards, saves and bonus/BPS. It requires the exact event, official endpoint provenance, capture timestamp and raw SHA-256. It fails on missing/duplicate players, missing stats or any mismatch; it never zero-fills absent history rows. A passing result establishes agreement with that captured final-scoring response only, not historical point-in-time integrity or fixture-level dependence.


### Batch finality reconciliation runner

The event-by-event reconciliation can now be executed reproducibly from the private capture archives:
- `scripts/m4_covar_realized_fpl_finality_batch.py`
- `tests/test_m4_covar_realized_fpl_finality_batch.py`

Expected private layout:
- realized dataset directory containing `fpl_realized_player_gameweek.csv`
- capture root containing `event_1/`, `event_2/`, etc., each created by `m4_covar_point_in_time_source_capture.py --event <GW>`
- each event archive must include `capture_manifest.json`, `event_live.json`, and `fixtures.json`

The batch runner verifies the captured manifest, event IDs, official endpoint URLs, raw SHA-256 values, and that every fixture in each target Gameweek is marked finished before auditing the realized player-GW rows. It records the `finished_provisional` count rather than rejecting provisional fixtures: the later official event-live comparison is the required reconciliation step. It writes a private report and refuses to overwrite an existing output directory. It never fills missing history rows.

Example (paths are placeholders and must be absolute, outside the repository):
```bash
python scripts/m4_covar_realized_fpl_finality_batch.py \
  --dataset-csv /private/realized/fpl_realized_player_gameweek.csv \
  --capture-root /private/event-captures \
  --output-dir /private/finality-audit-run-001
```

#### Actual GW1–GW10 retrospective reconciliation — 2026-11-21

The cloud workflow [run 44876601508](https://github.com/uasir/CTA-FPL-Model/actions/runs/44876601508) completed successfully using the official ingestion artifact from run 44357649202 and the M4 feature branch. Its artifact (`cta-fpl-retrospective-finality-1-10-44876601508`) contains the realized panels, ten official event-live/fixture capture archives, and the batch report. The result is `PASS_ALL_EVENTS`: all 10 Gameweeks reconciled, all 6,562 player-Gameweek rows matched, 91,868 stat values were compared, and there were zero mismatches. No missing history rows were zero-filled. Per-Gameweek compared rows were GW1 610, GW2 626, GW3 654, GW4 659, GW5 667, GW6 667, GW7 668, GW8 669, GW9 670 and GW10 672.

All 100 fixtures in the original ingestion snapshot were marked `finished_provisional`; the workflow retained them and reconciled the player-Gameweek outcomes against official event-live responses captured on 2026-11-21. This establishes exact agreement with those captured official responses for the supplied rows. It does **not** prove historical point-in-time availability, completeness of absent player-fixture rows, irreversibility of later score revisions, fixture-level joint dependence, or predictive validity. The archive remains retrospective, and the dataset is not yet sufficient to train or validate a joint forecaster. The workflow artifact is public-source evidence with finite retention, not a durable private archive.

The user's workflow remains cloud/GitHub-based; no local execution is required or assumed.

### Exact M3 forecast snapshot bridge

A manager-free extraction adapter is also implemented:
- `scripts/m3_covar_forecast_snapshot_adapter.py`
- `tests/test_m3_covar_forecast_snapshot_adapter.py`

It takes the sealed one-Gameweek M3 evidence bundle and M3 decision result, verifies provider and official bootstrap source bytes against SHA-256/source IDs/timestamps, confirms the M3 forecast snapshot ID and model version, and rebuilds the same conventional player-forecast payload using the M3 provider contract and recommendation adapter. The output contains only the forecast snapshot, player metadata, player forecasts and provider/metadata source archives. It excludes manager identity, squad, bank, transfer state, frozen decision and evaluation candidate.

This separation is necessary because the existing manual M3 evidence workflow uploads an artifact containing manager-specific decision evidence. CoVar must not consume or republish that full artifact in a public workflow. The extraction adapter is a code-level bridge only: no real prospective M3 forecast bundle has yet been captured and archived for CoVar. A private durable archive destination and a live pre-deadline M3 capture are still required.

This is a realized-outcome target archive, not a forecast archive. Keep the two roles separate. The realized panel has now been built and reconciled retrospectively for GW1–GW10. The next data blocker is a safe, durable archive of the exact conventional M3 forecast snapshot and FPL metadata captured before each deadline. Until those forecast vintages are paired with outcomes across enough independent Gameweeks, do not estimate or claim calibrated conditional dependence from this panel.

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
