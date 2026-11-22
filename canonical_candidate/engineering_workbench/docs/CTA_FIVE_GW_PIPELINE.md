# CTA-owned five-Gameweek forecast pipeline

## Scope and production boundary

This pipeline builds a fixture-grain forecast for the next five consecutive FPL
Gameweeks. It has three distinct responsibilities:

1. Reconstruct deadline-safe player/team history and the exact 286-feature input
   contract.
2. Import Dastan's released minutes component only: four position-specific p60
   heads and their packaged minutes calibration.
3. Train and score CTA-owned expected-points models, then aggregate fixture
   forecasts into player-GW and five-GW totals.

Dastan's expected-points, bucket, non60, direct and bucket-regression heads are
never loaded or called. CTA's points model is a separate position-specific
XGBoost candidate.

**The pipeline is not production-enabled.** The points and minutes outputs carry
`decision_weight=0` and `production_eligible=false` until the agreed M2
validation and subsequent M4 integration gates are cleared. The pipeline does
not use CoVar, does not publish player variance, and does not alter either
recommendation engine.

## Reproducible sources

The manual GitHub Actions workflow pins:

- Dastan reconstruction code and minutes artifacts: repository commit
  `758db9247e8b3a9a870c991064f74d8339d61cd0`.
- Vaastav FPL archive: commit
  `d7b05b51d137bfefef4b692386d18c610975b9b9`.
- fplcache snapshots: the commit recorded in the pinned Dastan source manifest.

The source-preparation script:

- Acquires the historical FPL, Understat player and Understat team inputs.
- Refreshes the active season from official FPL bootstrap, fixtures and
  element-summary endpoints, rather than relying on a stale early-season
  archive.
- Records which active-season files are hybrid/overridden by official API
  snapshots in `downloads.json`.
- Uses corrected historical FPL-to-Understat identities while preserving the
  release's season/gameweek assignment intervals.
- Excludes shared Understat IDs from identity joins. Unmapped players remain
  present; no display-name or fuzzy identity matching is used.
- Uses Understat fallback acquisition when pinned player/team history is
  incomplete.
- Runs the fixture-level archive completeness audit and strict stable-code
  normalizer for every season before canonical feature construction.
- Builds canonical player-match and team-match Parquet tables.
- Rebuilds historical pre-deadline artifacts from the pinned fplcache snapshots
  for CTA points-model training.

The fixture audit proves finished-fixture coverage and internal fixture
metadata consistency. It deliberately does not claim that every registered
player must have a row for every fixture; no absent player rows are synthesized.

## Feature construction

The feature builder executes the pinned MIT Dastan/OpenFPL rolling definitions
on CTA's canonical match tables, while CTA owns target-fixture assembly and the
final feature contract.

For each target Gameweek independently, it appends only that Gameweek's
unplayed fixtures to completed history. It does not append GW+1 target dummies
when building GW+2. This prevents future fixtures from becoming false history.

The feature matrix has one row per `(season, gameweek, fixture_id, fpl_code)`
and exactly the pinned 286 ordered features. Double-gameweek fixtures remain
separate fixture rows. Player, own-team and opponent-team rolling histories are
anchored to the common FPL deadline; opponent features are separately
re-anchored so an earlier target fixture cannot contaminate a later DGW fixture.

The live official bootstrap contributes `ep_next`, status, chance-of-playing
and news only to the immediate next Gameweek. For later target Gameweeks those
snapshot fields use the explicit `-1.0` absence sentinel. The two-stage
missing-value contract is preserved:

1. Absent pre-deadline snapshot fields: `-1.0`.
2. Residual feature NaNs at the inference boundary: `0.0`.

## Minutes component

The p60 inference runner hash-verifies the four Dastan p60 model files, the
ordered feature list and minutes calibration against Dastan's artifact
manifest. It loads only those four p60 heads and applies the packaged
calibration to produce:

- `p60`
- `p_any`
- `expected_minutes`

It does not instantiate Dastan's full points predictor or load any Dastan
points head.

## CTA-owned points component

The CTA points trainer fits one XGBoost regression model per position on the
six-season historical feature frame with pre-deadline snapshot joins. It saves
model hashes and training coverage. It does not use Dastan points heads.

M2 validation is deliberately not run by this workflow. The model manifest
states `NOT_RUN_M2_DEFERRED`; candidate predictions cannot enter conventional
or CTA-informed recommendations until the deferred evaluation is completed
and approved.

## Forecast products

The scorer emits three files:

- `fixture_forecasts.csv`: fixture-level CTA expected points, p60, p_any and
  expected minutes.
- `player_gameweek_forecasts.csv`: sums of fixture-level expected points and
  minutes for each player-GW.
- `player_five_gw_forecasts.csv`: sums of player-GW values across the five-GW
  horizon.

Aggregate values are calculated from fixture-level rows; aggregate forecasts
are never split or artificially allocated across fixtures. Appearance
probabilities are retained at fixture level and are not naively summed across
fixtures. No covariance or joint player-point scenarios are inferred.

## Execution

The PR workflow runs Python compilation, the engineering-workbench Python
tests and JavaScript tests. The full data/model run is manual:

1. Open GitHub Actions in the CTA-FPL-Model repository.
2. Select **CTA five-Gameweek forecast pipeline**.
3. Select **Run workflow** on the branch containing the pipeline.
4. Download the `cta-five-gw-candidate-forecast` artifact.

The artifact contains raw-source manifests, active-season API snapshots,
fixture-audit and normalization reports, canonical tables, the historical
training frame, the 286-feature forecast matrix, minutes predictions, CTA
points model hashes and all three forecast products.

The first complete run remains the operational evidence gate. A successful
compile/test workflow alone does not prove that live source acquisition,
Understat coverage, fixture auditing or the five-GW feature build succeeds.
