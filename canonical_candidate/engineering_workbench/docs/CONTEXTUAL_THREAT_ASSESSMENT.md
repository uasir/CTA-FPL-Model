# Contextual threat assessment — StatsBomb 360 research sidecar

## Objective

Develop match-derived predictors of FPL points that add information beyond conventional
shot xG and xA. The initial research direction is to measure the context in which
players act: defensive pressure, available space, goal-side defensive coverage,
passing/carrying lanes, supporting teammates, and the danger created or removed by
actions.

This is a feature-research programme, not a validated points model. No contextual
feature in this document is connected to either recommendation engine.

## Data sources and realistic coverage

### StatsBomb Open Data

StatsBomb Open Data provides match metadata, lineups, event JSON and selected
StatsBomb 360 freeze frames. The 360 frames contain visible player locations,
teammate/opponent flags, actor flags and goalkeeper flags, joined to events by
event_uuid. It is a valuable source for developing spatial-context features, but
it is not continuous optical tracking.

The currently published competition index lists only the 2015/16 and 2003/04
men's Premier League seasons. 360 availability is narrower still and must be
checked match by match. Consequently, this source can support historical method
development and cross-competition experiments; it cannot alone supply a
current-season Premier League training panel.

Source: https://github.com/hudl/open-data
Attribution is required when publishing analysis based on StatsBomb Open Data.
The source terms and the exact permitted use must be retained with every dataset
manifest. CTA stores no new bulk StatsBomb source files in this feature PR.

### Openplay historical event dataset

Openplay is currently the strongest candidate for the historical Premier League
event panel: its published snapshot contains 41.6 million events across 26,536
matches, with Premier League coverage from 2014/15 through 2025/26 (4,556 of
4,560 matches have event data). It includes event-level passes, shots, tackles,
interceptions and more with pitch coordinates, xG on every shot, plus separate
player-match statistics, lineups and shot tables. Coordinates use a 0–100
attacking-direction convention. The dataset is CC BY 4.0 and requires credit to
"openplay (Noah Bair)".

Source: https://github.com/nlbair/openplay

This aligns well with the historical FPL outcome archive from 2016/17 onward.
Before use, ingest its coverage, known-gaps and data-issues tables; handle
repeated event IDs with the provider's event_id_sub field; and preserve the
expanded-minutes convention. The 2026/27 season is not included, so it cannot
replace a current-season feed.

Openplay access check (2026-11-18): the public Python reader installs, but
its first attempt to fetch the pinned data release's checksums.json from
nlbair/openplay returns HTTP 404 in GitHub Actions. The dataset is therefore
not integrated or used by CTA at this point. Treat it as a promising source
whose release access must be fixed or confirmed by its maintainer; do not build
the training pipeline on an unverified download path.

### 11footy current-season match dataset

11footy publishes a Premier League SQLite/CSV snapshot rebuilt after rounds.
The pinned 11footy-2026-11-10 Premier League release includes lineups,
player-match statistics, player-match event counts, tracked shots with xG and
match-level event layers. It is useful for current-season player-match and
shot-context monitoring, but its README describes summary/play-by-play event
layers rather than a full StatsBomb-style every-pass action stream. It has no
360 or continuous tracking data.

Source: https://github.com/fm-devlab/11footy-dataset
Release: https://github.com/fm-devlab/11footy-dataset/releases/tag/11footy-2026-11-10

The dataset is CC BY-NC 4.0: non-commercial use only, with credit to 11footy.
Its README does not identify every upstream source for the event/statistics
layers, so reconcile its outputs against official FPL actuals and other feeds.
The release is a snapshot, not a live API. A verified FPL-to-11footy player
crosswalk is still required.

### Wyscout public event dataset

The Pappalardo–Massucco Soccer Match Event Dataset contains event logs from
seven competitions, including the full 2017/18 Premier League season. Its event
records include event/subevent type, tags, event time, match ID, player ID,
team ID, and origin/destination positions on a 0–100 attacking-team-oriented
pitch. The Events file is 73.74 MB and is available under CC BY 4.0; cite the
dataset paper when using it.

Source: https://figshare.com/articles/dataset/Events/7770599
Collection: https://figshare.com/collections/Soccer_match_event_dataset/4415000

This is a stronger immediate bridge to FPL historical outcomes than the
StatsBomb EPL subset: 2017/18 is within the historical FPL archive's coverage.
It does not include StatsBomb-style 360 freeze frames or continuous player
tracking. CTA should use it for event-derived player-match features, then join
to FPL gameweek outcomes only through a verified season-specific player
crosswalk. The existing Wyscout-to-FPL crosswalk is currently header-only, so
identity reconciliation remains a required step, not an assumed join.

### Other sources

- Opta/PulseLive: current CTA integration currently has team-match aggregates and
  player-season aggregates, not verified player-level event rows. Keep this
  adapter separate; its data rights and point-in-time vintage remain unresolved.
- Wyscout: a separate event-data provider and identity namespace. Do not treat
  Wyscout player IDs as StatsBomb IDs or merge provider data without a verified
  crosswalk and source-specific terms.
- Paid StatsBomb, Opta or Wyscout feeds may be required for consistent current
  Premier League event coverage. Compare rights, historical depth, event schema,
  360/tracking availability, identity mapping and price before committing.

### Current-season 11footy/FPL player-match integration

The current-season integration adapter now reconciles 11footy Premier League
matches against official FPL fixtures using exact kickoff date and home/away
team names. It joins 11footy player-match statistics, event counts and tracked
shot-level xG to the common season/fixture/player-match structure.

Identity handling is deliberately two-tiered:

- Only validator-accepted, season- and competition-scoped verified crosswalk
  rows can enter the model-ready player-match panel.
- Pending 11footy/FPL candidates are checked against official FPL player-fixture
  history using team, minutes, goals and assists. This is independent
  corroboration for manual review, not automatic proof and never promotes a
  candidate to verified.
- Retired 11footy IDs are resolved through the provider's player-merges table
  before identity lookup.
- Fixture, player and source-snapshot provenance are retained. Match-level
  feature rows and candidate evidence remain inside the workflow runner;
  only aggregate integration status and source hashes are published.

The adapter preserves 11footy's CC BY-NC 4.0 non-commercial restriction and
does not treat its player-match summary layer as continuous tracking or a full
event stream. Its current output is not a validated CTA score and does not
enter points training until verified mappings and chronological holdout tests
are available.

### Wyscout 2017/18 EPL audit result (2026-11-18)

The pinned public Figshare download completed successfully in GitHub Actions.
The England event file contains 643,150 events across all 380 Premier League
matches, with 515 distinct players in event rows and 3,603 player metadata
records. All 380 match IDs reconcile between the event and match files; one
event player ID is absent from the player metadata catalogue.

- 328,657 passes, 176,688 duels, 51,085 other-on-ball events, 36,423 free
  kicks, 27,535 interruptions, 8,451 shots, 8,138 fouls, 3,349 save attempts,
  1,558 offsides and 1,266 goalkeeper-leaving-line events.
- 643,032 of 643,150 events (99.98%) have both start and end positions.
- Data license: CC BY 4.0. The Pappalardo–Massucco data paper must be cited.

The audit is structural only. It does not yet join the 2017/18 FPL points
history or calculate a validated threat feature. It is nevertheless a viable
first full-season event-level bridge for developing progressive-action and
expected-threat features against FPL outcomes.

## First feature family: 360 spatial context

The new script scripts/extract_statsbomb_contextual_threat.py emits two outputs:

1. contextual_threat_events.csv: one row per supported event with a usable
   linked 360 frame.
2. contextual_threat_player_match.csv: player-match aggregates over those
   sampled 360-linked events only.

Initial components include:

- Number of visible opponents and teammates.
- Opponents within 5 and 10 pitch units of the actor.
- Nearest opponent and goalkeeper distance.
- Explicitly direction-aware opponents in the goal corridor and goal-side band.
- Forward teammates and opponents in the actor's attacking lane.
- Visible forward receiving options, passing-lane obstruction and receiver pressure.
- Progressive pass attempts/completions and progressive carries.
- Dangerous ball receipts, separated from passes that create progression or enter the final 40 pitch units.
- Shot attempts, StatsBomb xG and goals, kept as separate realisation outcomes.
- Event-level under-pressure indicator, pass recipient, shot-assist and goal-assist flags.

Coordinates are retained in StatsBomb's 120 × 80 frame. Out-of-bounds visible
players are excluded from geometric calculations and counted in diagnostics.
Duplicate event-frame UUIDs are reported; only the first frame is used.

### Attack direction and receiving-option safeguards

The earlier extractor treated the right-hand goal as the attacking goal for
every team and period. That assumption is not valid for a shared match coordinate
frame and could invert goal-side, forward-player and passing-lane features.

The extractor now accepts an explicit direction_map.csv keyed by match,
period and team ID (or team name). It does not infer or default a direction.
When no verified direction row exists, it withholds goal-relative, forward-lane,
progression, dangerous-receipt and receiving-option features rather than
publishing a misleading zero or a directionally inverted value. The repository
direction map currently contains only its header, so the real-match pilot will
report these directional features as unavailable until verified directions are
added.

Receiving options are assessed only among visible teammates ahead of the actor
and within 35 pitch units. A lane is considered blocked when a visible defender
occupies the actor-to-receiver corridor; receiver pressure is estimated from
visible opponent distance to the receiver. These are observable-frame
opportunity indicators, not proof that the entire pitch is open or that a pass
was actually available to the player.

## Threat dimensions and non-shot opportunities

Keep three dimensions distinct:

1. **Threat creation:** progressive pass attempts/completions and passes directed
   into the dangerous area, plus progressive carries. The extractor also records
   visible open dangerous receiving options even when no pass or shot follows.
2. **Threat involvement/reception:** a player receiving the ball in a dangerous
   area, independently of whether the possession produces a shot.
3. **Threat realisation:** shots, xG and goals, with assists retained as separate
   contribution evidence.

Do not sum these into an opaque score or count every failed action as a chance.
Pass attempts and completions are separate; open receiving options are counted
only when a visible teammate, visible defenders and a usable direction support
the geometric assessment. Creation, reception and realisation can be studied
as separate predictors and their sequence overlap must be handled explicitly
in player-match modelling.

The StatsBomb 360 feature set remains a sampled research sidecar. It does not
measure off-ball runs continuously, and it must not claim to observe every
receiving option or every attacking sequence.

## Interpretation safeguards

- A missing 360 frame is missing information, never zero pressure or zero opponents.
- Player-match aggregates explicitly say 360_sampled_events_only_not_full_match_totals.
- Freeze frames are snapshots around selected events, not full-match tracking.
- These spatial features are not xG, xA, xT or a calibrated probability of scoring.
- A high number of nearby defenders can mean pressure, but can also mean a
  crowded attacking zone; interpretation depends on event type and location.
- A shot's freeze frame is post-action context only if the provider's event/frame
  timing confirms it. Do not use it as a pre-shot prediction feature without
  checking temporal semantics.
- This PR deliberately does not create a single opaque "threat score".
  Preserve interpretable components until they have been tested against
  independent labels and future FPL outcomes.
- StatsBomb player IDs are not FPL element IDs. Only a separately verified,
  season- and competition-scoped identity crosswalk may join them.
- A single match, one competition, or sampled 360 events cannot establish
  out-of-sample FPL predictive value.

## Validation roadmap

1. Validate event-frame joins and geometric calculations on real 360 fixtures.
2. Compare spatial features with event-level xT, shot xG, xA, progressive actions,
   box entries and FPL points, while keeping post-action values out of predictors.
3. Establish a multi-match player-match panel with trusted minutes and verified
   player identity mapping.
4. Build player-role and position-specific rolling features using only matches
   completed before each FPL deadline.
5. Evaluate rolling-origin temporal holdouts and compare:
   - minutes / start-probability baseline;
   - recent FPL points and role baseline;
   - xG/xA and conventional underlying-stat baseline;
   - xT / progressive threat baseline;
   - contextual 360 feature augmentation.
6. Report MAE, RMSE, calibration, minutes error, coverage and performance by
   position and player role. Promote only when gains are stable across multiple
   held-out periods and do not depend on a single competition or season.

## Current status

PASS_STRUCTURAL_ONLY means the extractor completed its data and geometry checks.
It does not mean the feature predicts points. The extractor's report therefore
sets prediction_validation to NOT_EVALUATED.
