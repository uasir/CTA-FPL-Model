# CTA–FPL Model v1.0 — experimental integration build

## What is delivered
A runnable Python feature pipeline that transforms StatsBomb event JSON into:
- possession-level sequence features (`sequences.csv`)
- player-level, action-attributed features (`player_features.csv`)
- an optional action-based xT grid (`xt_grid.csv`)
- a data and limitation audit (`audit.json`)
- optional StatsBomb 360 event-UUID join audit

This is the **final implementation prototype for the current evidence base**, not a statistically validated FPL points predictor. It deliberately does not output a weighted CTA composite score.

## Project status carried forward from CTA pilot v0.2
The authoritative pilot is Bayer Leverkusen 2–2 VfB Stuttgart, 27 April 2024, StatsBomb match ID `3895320`.
- 3,771 event records parsed.
- 3,185 StatsBomb 360 frames parsed.
- 3,185/3,185 frame UUIDs matched uniquely to event IDs (100% frame-to-event join).
- 3,185/3,771 event records have a 360 frame (84.46% event coverage).
- 15-sequence register: 10 shot-linked legacy sequences and 5 added non-shot sequences.
- The 10 legacy shot-linked sequence boundaries were not reconstructed in v0.2.
- Provisional scores for three evidence-supported dimensions were assigned to S11–S15 only.
- Space creation/manipulation and defensive destabilisation remain N/A without video/tracking evidence.
- The pilot xT grid is a single-match exploratory fit, not a production reference.
- StatsBomb event coordinates are already oriented so the team in possession attacks toward x=120; do not apply a physical home/away half-direction flip.

The pipeline is designed to make the next data-processing stage repeatable. It does not claim that the 15 manually curated pilot sequences are already a complete or balanced training set.

## CTA feature philosophy
CTA is represented as a **vector of distinct, interpretable features**, not one opaque score:
- threat access / box entry
- final-third access
- progressive actions (direction-normalised forward progression proxy, not proof of line-breaking)
- pressured receipts and pressured actions
- shot-linked sequence involvement
- rule-based non-shot candidate sequence involvement
- action xT gain (separate conventional spatial baseline)

Off-ball space creation and defensive destabilisation require trajectory/video evidence and are not guessed from event data. Shot xG is output as reference-only and must not be used as a pre-shot process feature.

## Install and run
Python 3.10+; standard library only.

1. Put one StatsBomb event JSON file per match in `data/events/`, named `{match_id}.json`.
2. Spatial metrics and xT use StatsBomb's possession-oriented coordinate convention: the team in possession attacks toward x=120. The pipeline now fills the direction map automatically with `true` for each match-period-possession-team key. You do not need to provide a direction map for standard StatsBomb Open Data. If an override CSV is supplied, it must use `match_id,period,team,attacks_right` and every `attacks_right` value must be `true`; a `false` value would double-flip already-normalised coordinates and is rejected.
3. Optional player join: populate `data/player_id_map.csv`:
   `statsbomb_player_name,fpl_player_name`
   Only manually verified aliases.
4. Optional minutes: populate `data/player_minutes.csv`:
   `player_name,minutes`
   Use minutes from a trusted source.

Run:
```bash
python src/cta_engine.py --events-dir data/events --three-sixty-dir data/three-sixty --direction-map data/direction_map.csv --player-map data/player_id_map.csv --minutes data/player_minutes.csv --output-dir outputs
```

Run tests:
```bash
python -m unittest discover -s tests -v
```

## FPL integration contract
Join player features to FPL player IDs only through the verified alias table, then to FPL player IDs through a separately checked mapping. Preserve CTA features in a namespace:
- `cta_nonshot_candidate_sequences_per90`
- `cta_shot_linked_sequences_per90`
- `cta_box_entries_per90`
- `cta_final_third_entries_per90`
- `cta_progressive_actions_per90`
- `cta_pressured_receipts_per90`
- `cta_action_xt_gain_per90`

Do not assign the same sequence's total threat to every participant. The current pipeline attributes actions to the action actor and pass-reception counts to the named recipient. Sequence involvement is a context count, not a share of sequence threat.

## Validation gate before production
The CTA feature layer must remain outside the frozen FPL baseline until:
1. Sequence boundaries are harmonised across shot and non-shot samples.
2. Multiple teams and matches are included, with competition/season coverage documented.
3. Human review checks rule-based non-shot candidates; reviewer agreement and inter-rater reliability are measured.
4. Player identity and minutes are joined without leakage.
5. Time-ordered FPL backtests compare baseline vs baseline+CTA using held-out gameweeks.
6. Forward validation confirms any gain persists.

Report at least MAE/RMSE for points, rank correlation, calibration, and decision utility (e.g. transfer/captain choices) with uncertainty. Keep features only if they improve out-of-sample performance.

## Important data availability limit
StatsBomb Open Data is a selected-competition dataset, not a complete live feed for every current FPL season/team. The Leverkusen–Stuttgart pilot is useful for methodology development but cannot directly create a complete current Premier League player feature table. A current FPL deployment requires a licensed or otherwise permitted event/tracking source covering the target league and season, or an explicitly narrower historical evaluation.

## Provenance
StatsBomb Open Data repository:
https://github.com/hudl/open-data
Pilot event file:
https://github.com/hudl/open-data/blob/master/data/events/3895320.json
Pilot 360 file:
https://github.com/hudl/open-data/blob/master/data/three-sixty/3895320.json

Follow the repository attribution requirements and applicable data terms.
