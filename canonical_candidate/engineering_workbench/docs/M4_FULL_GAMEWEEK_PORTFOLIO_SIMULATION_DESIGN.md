# M4 Full-Gameweek Portfolio Simulation: Design Contract

## Status

Design gate for the next M4 engineering increment. This document does not claim that full-Gameweek FPL scoring or automatic substitutions are implemented. The existing CoVar scorer remains a synthetic fixture-slice research prototype.

## Objective

Extend the existing sampled manager portfolio bridge so a candidate squad and sampled field portfolios can eventually be evaluated over the same complete Gameweek scenario distribution. The extension must preserve the current separation between regular Gameweek and explicitly activated Free Hit analysis.

## Current input gap

The manager-ID-stripped artifact currently retains the ordered 15 player IDs, captain, captain multiplier, chip, rank stratum, and normalized sample weight. That is not sufficient to reconstruct a legal FPL starting lineup or apply automatic substitutions. The capture rows already retain pick position and vice-captain flag, but the artifact currently discards vice-captain and does not encode player positions.

Do not infer starting XI, bench order, reserve goalkeeper, player position, or vice-captain from the unordered/projected fixture player set.

## Required portfolio lineup fields

For each sampled manager, preserve the following fields in the private manager-ID-stripped artifact:

- `player_ids`: all 15 players in official pick-position order.
- `starting_player_ids`: positions 1–11, in starting lineup order.
- `starting_goalkeeper_id`: the goalkeeper among positions 1–11; require exactly one.
- `reserve_goalkeeper_id`: the goalkeeper in bench position 12; require exactly one reserve goalkeeper.
- `bench_order`: outfield substitutes in positions 13–15, preserving official order.
- `player_positions`: mapping from player ID to one of `GK`, `DEF`, `MID`, `FWD`, sourced from the same FPL bootstrap-static element metadata used by capture.
- `captain_id` and `vice_captain_id`: both must be distinct members of the starting XI.
- `active_chip`: normalized chip or null.
- Existing field weight, rank stratum, and FIELD role.

The public GitHub Actions workflow must continue to publish aggregate EO only. Manager-level artifacts remain explicit local private exports outside the repository and outside the aggregate artifact directory. The artifact must not contain entry IDs, manager names, or exact ranks. Squad combinations may still identify managers and must be treated as sensitive.

## Full-Gameweek scenario contract

A full-Gameweek scenario must include explicit player outcomes for the scenario's modeled player universe. Outcomes must include minutes and enough event data to derive FPL points, or an explicitly supplied validated FPL points total. Missing player outcomes must fail validation; missing outcomes must never silently mean zero minutes or zero points.

The scenario universe must cover all players in each candidate and field squad, not merely players from one fixture. Candidate and field portfolios must be scored against exactly the same scenario IDs and probabilities.

## Deterministic lineup scoring rules

1. Start with the submitted starting XI and its formation.
2. A player who counts as having played is unavailable for autosubstitution. Positive minutes always count as played; a card-only appearance may also count as played even with zero minutes. A player who has played remains in the XI, even if substituted during the match.
3. If the starting goalkeeper has zero minutes, replace only with the reserve goalkeeper if that goalkeeper has positive minutes.
4. For outfield absences, process the three outfield substitutes in their submitted bench order. A substitute may enter only if the resulting XI remains a legal FPL formation: at least 3 DEF, 2 MID, and 1 FWD, with one goalkeeper.
5. The starting captain receives the normal additional captain multiplier only if they count as having played. Otherwise the vice-captain receives it only if they count as having played. A card-only appearance counts as played even when minutes are zero. If neither plays, there is no captain bonus.
6. Triple Captain applies the additional captain multiplier to the active captain (captain or vice-captain fallback), making the total player multiplier 3x rather than 2x.
7. Bench Boost scores all 15 players, including the reserve goalkeeper and all outfield substitutes; normal captaincy rules still apply.
8. Ordinary scoring includes only the final legal XI plus captain bonus. Bench players score nothing unless autosubstituted.
9. Free Hit uses the same lineup and scoring rules but is a separately labelled mode. It must never be inferred from the existence of a Free Hit chip in a hypothetical or field portfolio. The default mode remains `REGULAR_GW`.

The implementation encodes the declared rules as explicit deterministic functions and unit tests. The independently sourced FPL rules audit remains a separate acceptance gate; no live-data or production use is authorized by synthetic test success.

## Required validation and tests

- Valid lineup reconstruction from positions 1–15 and bootstrap player types.
- Reject missing/duplicate vice-captain, invalid starting goalkeeper, or invalid reserve goalkeeper.
- Goalkeeper autosubstitution only when the starting goalkeeper does not play.
- First eligible outfield substitute enters in bench order.
- A substitute is skipped when they would create an illegal formation; later eligible substitutes are considered.
- No autosubstitution for players who appear for at least one minute.
- Captain fallback to vice-captain only when the captain does not play.
- No captain bonus when neither captain nor vice-captain plays.
- Triple Captain multiplier on captain and vice-captain fallback.
- Bench Boost includes all 15 players and does not double-count players.
- Regular Gameweek default; Free Hit requires explicit mode.
- Candidate and field scores use identical scenario distributions.
- Existing fixture-slice tests remain unchanged and passing.
- Privacy tests confirm manager IDs, names, and exact ranks are absent from the exported artifact.

## Non-goals and safeguards

- No production recommendation or decision-weight changes: `decision_weight=0`, `production_eligible=false`.
- No changes to M3 EV, legality, transfer logic, frozen decisions, decision hashes, or conventional M5 recommendations.
- No inference of joint manager portfolios from marginal EO.
- No upload, commit, or workflow artifact of manager-level portfolios.
- No real-world scoring validation until synthetic rules tests pass and an independently sourced FPL rules audit is complete.
- No PR merge without explicit approval.

## Delivery sequence

1. Extend the private portfolio artifact with lineup semantics and bootstrap-derived player positions.
2. Add a standalone, pure automatic-substitution/lineup-resolution module with exhaustive edge-case tests.
3. Extend the synthetic scenario contract to carry full-Gameweek outcomes and validate player coverage.
4. Add full-Gameweek scoring that reuses the same scenario distribution for candidate and field portfolios.
5. Add integration fixtures, privacy checks, documentation, and CI validation.
6. Keep the full-Gameweek engine synthetic-only until private real-result replay validation, complete Gameweek scenario generation, and empirical field-sample representativeness/uncertainty work are complete. The written 2026/27 lineup-rules audit is complete, but no real replay batch has been validated.

## Standalone lineup resolver implementation

The deterministic resolver is implemented in `scripts/m4_covar_lineup_resolver.py`
and tested independently in `tests/test_m4_covar_lineup_resolver.py`.

Its input is one explicit 15-player squad, lineup/bench order, position map,
captain and vice-captain, plus complete per-player minutes, explicit Gameweek played-status booleans, and
FPL-points maps for one scenario. Missing outcomes fail closed; minutes must
be finite and nonnegative; fixture-level minutes are capped at 120, while the
aggregated Gameweek total may exceed 120 in a Double/Triple Gameweek. Points may
be negative. A player with positive
minutes must be marked as played, while a zero-minute player may still be
marked as played for a card-only appearance, consistent with current FPL guidance.

Resolution behavior:

- The starting goalkeeper is replaced only when they did not count as having
  played and the reserve goalkeeper did count as having played.
- Outfield substitutes are considered in submitted bench order. For each
  playing substitute, the resolver replaces the earliest still-unreplaced
  absent starting outfielder for which the resulting formation meets the
  minimum 3 DEF / 2 MID / 1 FWD constraints. An ineligible substitute is
  skipped and later bench players are still considered.
- Any starter who counts as having played remains in the XI, including a player
  substituted off during the match or a card-only appearance. Explicit played
  status, not minutes alone, governs autosubs and captain fallback.
- Captaincy falls back to the vice-captain only when the captain did not count
  as having played. No bonus is awarded if neither plays. The 3xc chip applies a 3x
  total multiplier; otherwise the active captain receives 2x.
- The bboost chip scores all 15 players exactly once, while retaining the
  normal captain/vice-captain bonus. Other recognized chips do not alter this
  resolver's scoring behavior.
- `mode` defaults to `REGULAR_GW`; `FREE_HIT` must be explicitly supplied.
  Mode is a label here, not an inferred chip effect.

The resolver returns the resolved XI, substitutions, active captain, player
contributions and total points. It remains synthetic research code with
`decision_weight=0` and `production_eligible=false`; it is not yet connected
to full-Gameweek scenario scoring.

## Full-Gameweek scenario contract implementation

A separate validator is implemented in
`scripts/m4_covar_full_gameweek_contract.py`, with tests in
`tests/test_m4_covar_full_gameweek_contract.py`. It is intentionally separate
from the existing fixture-slice contract and does not change that contract or
its scorer.

The full-Gameweek document must declare:

- `scenario_scope=FULL_GAMEWEEK` and `data_status=SYNTHETIC_FULL_GAMEWEEK_ONLY`.
- A player universe equal to the union of all complete candidate and field
  15-player squads. Every player has one authoritative position.
- Complete 15-player lineup semantics for every portfolio, with a legal
  starting XI, reserve goalkeeper, ordered outfield bench, distinct starting
  captain and vice-captain, and position metadata consistent with the player
  universe.
- For every scenario, exactly one outcome for every player in that full
  universe. Each outcome requires finite FPL points, minutes, and an explicit
  boolean `played` value. Positive minutes require `played=true`; zero-minute
  card-only appearances may also be marked played.
- Unique scenario and portfolio IDs, probabilities summing to one, pre-deadline
  as-of metadata, and normalized positive weights when FIELD portfolios exist.

This establishes a shared scenario distribution and prevents fixture-slice
outcome coverage from being mistaken for full-Gameweek coverage. The contract
accepts supplied synthetic FPL point totals; it does not derive points from
events or score portfolios. The resolver and scorer integration remain the
next engineering step. The contract remains synthetic-only with
`decision_weight=0` and `production_eligible=false`.

## Full-Gameweek scorer integration

`scripts/m4_covar_full_gameweek_scoring.py` now validates the full-Gameweek
contract and runs every candidate and field portfolio through the standalone
lineup resolver for every shared scenario. Tests are in
`tests/test_m4_covar_full_gameweek_scoring.py`.

The scorer:
- Uses the same ordered scenario IDs and probabilities for every portfolio.
- Resolves goalkeeper/outfield autosubs, played status, captain fallback,
  Triple Captain and Bench Boost before calculating each scenario score.
- Reports per-scenario resolved XI, substitutions, active captain and score,
  plus expected points, variance, standard deviation and weighted quantiles.
- Decomposes portfolio score variance into player-level variance/covariance
  contributions and checks that the decomposition reconciles to total variance.
- Compares candidates to explicitly supplied weighted FIELD portfolios using
  the same scenario, with scenario probability multiplied by explicit field
  portfolio weight. It does not infer manager-level joint portfolios from EO.
- Supports an optional explicit baseline portfolio ID; no baseline is inferred.

This is deterministic scoring of supplied synthetic outcomes, not a forecast
generator or production recommendation. REGULAR_GW remains the default;
FREE_HIT is accepted only when explicitly declared. Output remains
`decision_weight=0` and `production_eligible=false`.

## Full-Gameweek document builder

`scripts/m4_covar_full_gameweek_builder.py` composes candidate portfolios,
the existing private pre-deadline manager-portfolio adapter output, and explicit
full-Gameweek scenario outcomes into the validated full-Gameweek contract.
Tests are in `tests/test_m4_covar_full_gameweek_builder.py`.

The builder requires matching Gameweek, deadline and as-of identity; explicit
pre-deadline provisional field evidence; an attestation that manager entry IDs
were discarded; full 15-player field lineups; and consistent player-position
metadata. It rejects manager identifiers in adapted field rows and strips
rank-stratum labels from the scorer-facing portfolio payload. It does not
reconstruct joint portfolios from marginal EO. The full player universe is
derived from the union of candidate and adapted field squads, after which the
contract verifies complete outcome coverage in every scenario.

The builder is a local composition function only. It does not read or export
the private manager-level artifact, add private portfolio data to GitHub
Actions, or upload any manager-level data. The resulting document and all
manager-level source artifacts remain restricted to private local handling.

## Official-result replay validation

A private local comparison harness is implemented in
`scripts/m4_covar_fpl_replay_validation.py` and tested in
`tests/test_m4_covar_fpl_replay_validation.py`. It compares all 15 expected
player multipliers, active captain fallback and per-player points against a
normalized official final FPL picks snapshot. It also reconciles the team total
from official player points and pick multipliers and derives Gameweek played
status from minutes and yellow/red-card counts.

The harness is local-only, rejects manager identifiers, requires its input file
outside the repository, and never exports replay inputs. Synthetic tests passed
in CI; actual completed-Gameweek replay execution remains pending.


## Explicit joint fixture-scenario composition

A joint fixture-scenario composer is implemented in
`scripts/m4_covar_joint_fixture_scenario_composer.py`, with tests in
`tests/test_m4_covar_joint_fixture_scenario_composer.py`.

The composer accepts:
- A scenario catalog for each declared fixture. Every scenario in a fixture
  catalog must contain the same player universe and complete fixture-level
  minutes, card counts and supplied FPL point contributions.
- An explicit list of joint Gameweek scenario rows. Each row references exactly
  one catalog scenario for every fixture and supplies its own joint probability.

It resolves those references into the input shape consumed by the
fixture-to-Gameweek aggregator. It does not form a Cartesian product, multiply
marginal fixture probabilities, sample outcomes, or infer correlations. The
joint rows and their weights are supplied inputs; they are the explicit
representation of dependence between fixtures. Unknown/missing references,
inconsistent player coverage, invalid fixture outcomes, duplicate scenario IDs,
and joint probabilities that do not sum to one fail closed.

This closes the deterministic composition gap only. It does not estimate the
joint distribution from historical data, generate match forecasts, model
cross-fixture team/player dependencies, or calculate FPL points from raw events.
Until a defensible joint probability model and empirical calibration exist, all
outputs remain supplied-input research artifacts, not predictive evidence.


A thin integration function is also implemented in
`scripts/m4_covar_joint_fixture_gameweek_pipeline.py`, tested in
`tests/test_m4_covar_joint_fixture_gameweek_pipeline.py`. It composes the
explicit joint fixture references and passes the resulting rows directly to
the Gameweek aggregator. This verifies the interface between the two modules,
including a synthetic Double Gameweek example. It does not add any probability
or outcome-generation assumptions.


## Historical joint-probability calibration evaluator

A deterministic evaluation harness is implemented in
`scripts/m4_covar_joint_probability_calibration.py`, with tests in
`tests/test_m4_covar_joint_probability_calibration.py`.

Each historical forecast row must include:
- A unique forecast ID and Gameweek ID.
- A timezone-aware forecast as-of timestamp strictly before the earliest
  kickoff in that Gameweek.
- A training-data cutoff timestamp no later than the forecast as-of time.
- A complete probability distribution over mutually exclusive joint
  Gameweek states.
- A reference probability distribution over exactly the same state catalogue.
- The subsequently observed joint Gameweek state.

The evaluator reports multiclass Brier scores for the model and reference,
Brier skill relative to the reference, log loss, zero-probability misses,
Gameweek-level summaries, and equal-width one-vs-rest reliability bins for
joint-state probabilities. A zero probability assigned to the realized state
is not silently clipped: log loss is reported as unavailable for the aggregate
when any such miss occurs, with the count exposed separately.

The evaluator does not estimate probabilities, construct the joint state
catalogue, prove reference-model provenance, or establish statistical
independence between historical observations. Reference forecasts must be
generated using information available at the relevant forecast time and
their provenance must be independently audited. Evaluation should use
chronological, non-overlapping held-out Gameweeks; repeated forecasts for one
Gameweek are not independent temporal evidence. Report results by Gameweek
and across multiple seasons/cohorts before interpreting reliability.

This is an offline historical backtest evaluator only. No minimum sample-size
threshold, confidence interval, calibration acceptance threshold, or
production gate is asserted yet. Synthetic unit tests verify arithmetic and
leakage guards, not forecast quality. Outputs remain
`decision_weight=0` and `production_eligible=false`.


## Historical dataset and benchmark protocol

The chronological split validator is implemented in
`scripts/m4_covar_joint_forecast_dataset.py`, with synthetic contract tests in
`tests/test_m4_covar_joint_forecast_dataset.py`. It validates a manifest with
three non-empty, disjoint Gameweek cohorts (`train`, `validation`, `test`),
requires every declared Gameweek to have forecast records, enforces strictly
increasing kickoff windows across cohorts, and checks that each forecast's
training cutoff is no later than its as-of timestamp and that the as-of is
strictly before the first kickoff. Multiple snapshots for one Gameweek are
permitted but are explicitly clustered under the Gameweek independence unit.

### Data construction rules

1. A forecast record is an immutable point-in-time snapshot, keyed by a unique
   forecast ID and Gameweek ID. Preserve the source, source version/hash,
   retrieval timestamp, forecast as-of timestamp, first kickoff, training
   cutoff, model/config version, state-catalogue version and observed-outcome
   source/version.
2. Only inputs demonstrably available by the forecast as-of timestamp may be
   features. A current FPL bootstrap or retrospective API response is not
   historical point-in-time evidence merely because it contains old Gameweek
   fields. Older source vintages must be durably archived with timestamps and
   hashes before they can support a historical backtest.
3. The target is the realized full-Gameweek joint state from a declared,
   versioned state catalogue. Fixture aggregation must use complete observed
   fixture outcomes and an explicit joint Gameweek mapping; do not infer
   cross-fixture independence or multiply marginal fixture probabilities.
4. Store forecast and observed-result records separately. Join them only by
   immutable IDs after the deadline/results are final. Corrections to source
   data create a new version and an auditable rebuild, not silent mutation.
5. Keep private manager-level picks and portfolio combinations out of public
   datasets, commits and Actions artifacts. Public artifacts may contain only
   permitted aggregate EO. Private replay evidence stays local and access
   controlled.

### Temporal evaluation design

- Assign entire Gameweeks to one cohort; never split player rows, fixtures or
  repeated snapshots from the same Gameweek across cohorts.
- Use contiguous chronological blocks, not random row-level splits. The
  train block is for fitting and feature/model selection; validation is for
  predeclared model/config selection; test is a final untouched chronological
  holdout used once for reporting.
- The validator checks disjointness and ordering. The research runner must
  additionally freeze the selected configuration before test evaluation and
  record the manifest hash. Any test-informed change invalidates that test
  cohort for confirmatory reporting.
- Use an expanding-window or rolling-origin simulation for genuine historical
  forecasts: at each forecast as-of, refit/refresh only from data whose
  availability timestamp is at or before the recorded training cutoff. Do
  not train on later Gameweeks, later corrections, final prices, or final
  injury/news information.
- If validation observations become available before a later test forecast,
  they may enter that later forecast's training history only under a declared
  walk-forward policy and only after their actual availability time. They may
  not be used to tune a model after viewing the test outcomes.
- Report both forecast-row and distinct-Gameweek counts. Repeated snapshots
  within a Gameweek are clustered and are not independent observations.

### Reference benchmark

The reference must be declared before the holdout is opened. A defensible
initial reference is a simple historical joint-state frequency distribution
estimated only from the training history available at each forecast as-of,
with a documented smoothing rule fixed on validation. It must use the same
joint-state catalogue as the evaluated model. A reference generated from
held-out outcomes, retrospectively tuned probabilities, or marginal fixture
frequencies multiplied under an independence assumption is invalid. If the
catalogue changes, define an explicit versioned mapping; do not silently
relabel historical states.

The existing official `ep_next` baseline is a player expected-points
benchmark, not a joint Gameweek-state probability reference. It must not be
misrepresented as one.

### Sample size and uncertainty

No arbitrary minimum Gameweek count is set by this specification. Before
confirmatory evaluation, define the minimum number of distinct held-out
Gameweeks and seasons from the available historical coverage, expected effect
size, desired precision/power and dependence structure. Player rows, state
rows, and repeated forecasts do not increase the independent Gameweek count.
Confidence intervals must resample at the Gameweek (or larger season/block)
cluster level, preserving all forecasts and joint states within each sampled
cluster. Report the number of independent clusters, interval method, random
seed, interval coverage and any small-sample limitations. If there are too few
independent Gameweeks/seasons for a stable interval, label the result
exploratory rather than relaxing the independence assumption.

The current validator is a structural/time-order guard only. It does not prove
source-vintage availability, benchmark provenance, a frozen test protocol,
statistical power, confidence-interval validity, or predictive skill. No real
historical point-in-time dataset has yet been certified. CoVar therefore
remains research-only with `decision_weight=0` and
`production_eligible=false`.


## Gameweek-clustered calibration uncertainty

A separate paired percentile cluster-bootstrap evaluator is implemented in
`scripts/m4_covar_gameweek_cluster_bootstrap.py`, with tests in
`tests/test_m4_covar_gameweek_cluster_bootstrap.py`. It consumes the
`per_forecast` score rows produced by the joint-probability calibration
evaluator. It first averages repeated forecast snapshots within each
Gameweek, then resamples whole Gameweek clusters with replacement. The same
sampled clusters are used for model and reference scores, preserving their
paired comparison. It reports 95% percentile intervals for model Brier,
reference Brier, their paired difference, and Brier skill, alongside the
number of independent Gameweeks, resample count and deterministic seed.

The estimand is explicitly Gameweek-equal-weighted, so a Gameweek with more
forecast snapshots does not dominate the interval. This differs from the
existing forecast-row-weighted point summaries in the calibration evaluator;
compare like with like by using the bootstrap's own `point_estimate` when
interpreting its intervals. Fewer than 20 Gameweeks triggers an exploratory
small-sample warning; this is a caution label, not a claim that 20 is a
sufficient sample size. Percentile cluster-bootstrap intervals can remain
unstable with few independent Gameweeks or seasons and do not establish
predictive validity. The function is standalone and must be applied to the
calibration evaluator's `per_forecast` output; no real historical result has
been evaluated. CoVar remains research-only with `decision_weight=0` and
`production_eligible=false`.


### Integrated calibration report

The joint-probability calibration evaluator now invokes the Gameweek cluster
bootstrap directly and includes the resulting intervals in its report. The
report schema is `1.1.0`; callers may set `bootstrap_resamples` and
`bootstrap_seed` (defaults: 2,000 and 42). The top-level Brier and log-loss
summaries remain forecast-row-weighted for backward interpretability, while
the bootstrap interval point estimates are Gameweek-equal-weighted after
averaging repeated forecasts within each Gameweek. These are distinct
estimands and are labeled explicitly in `aggregation_estimands`; users must
not compare one point estimate to the other's interval as if they were the
same statistic. The bootstrap intervals are included under
`gameweek_cluster_confidence_intervals`. Integration tests verify the
complete report shape, deterministic seed propagation and distinct
aggregation labels. This remains synthetic-only validation; no historical
forecast archive has been evaluated and CoVar remains research-only.

## Historical forecast provenance validator

A fail-closed structural provenance validator is implemented in
`scripts/m4_covar_joint_forecast_provenance.py`, with tests in
`tests/test_m4_covar_joint_forecast_provenance.py`. Each forecast must carry
model-artifact, configuration and forecast-payload SHA-256 declarations;
model/config/state-catalogue versions; generation time; model training cutoff;
and one or more versioned source snapshots with content hashes, availability
times and retrieval times.

The validator requires model training cutoff no later than the declared
training-data cutoff, generation no later than forecast as-of, and every
source's availability and retrieval timestamps no later than forecast as-of.
It rejects missing provenance, malformed hashes, duplicate source IDs within a
forecast, naive timestamps and point-in-time violations. The report explicitly
states that hashes are declarations only: this validator does not retrieve or
rehash source bytes, authenticate model artifacts, prove that the declared
versions generated the forecast, or establish that a provider's historical
availability timestamp is truthful. Those claims require archived immutable
source bytes, independent digest verification and auditable acquisition
records. A structurally valid report is not a certified historical dataset;
outputs remain `decision_weight=0` and `production_eligible=false`.
