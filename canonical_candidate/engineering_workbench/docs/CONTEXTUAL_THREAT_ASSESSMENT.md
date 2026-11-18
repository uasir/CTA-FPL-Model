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
- Opponents occupying a 5-unit corridor between actor and goal.
- Goal-side opponents within a 12-unit lateral band.
- Teammates ahead within 20 units.
- Nearest opponent ahead in an 8-unit lateral lane.
- Event-level under-pressure indicator and action type.

Coordinates are retained in StatsBomb's 120 × 80 frame. Out-of-bounds visible
players are excluded from geometric calculations and counted in diagnostics.
Duplicate event-frame UUIDs are reported; only the first frame is used.

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
