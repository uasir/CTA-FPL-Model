# 11footy provisional CTA research panel

## Purpose

The current-season 11footy/FPL integration now produces two deliberately separate outputs:

1. `verified_player_match_panel.csv` remains the only identity-verified common player-match panel.
2. `provisional_research_only_player_match_panel.csv` is a runner-local exploratory panel for candidates with exact normalized full name, team and matching birth date, plus an exact official FPL player-code check and fixture-team corroboration.

The second file does **not** promote identities, populate the verified crosswalk, or make any row production eligible. Its report explicitly sets both `production_eligible` and `prediction_training_eligible` to false.

## Inclusion rules

A row is included only when all of the following hold:

- Exactly one season/competition-scoped provider-to-FPL candidate exists for the canonical 11footy player ID.
- Candidate confidence is high and the candidate match method is exact name/team/birth date.
- Candidate status is still pending; a verified mapping belongs in the verified panel instead.
- Provider match resolves to exactly one official FPL fixture by date, home team and away team.
- Official FPL player-fixture history exists for the candidate FPL element and fixture.
- Provider player team agrees with the player's actual home/away team for that fixture.
- Candidate FPL player code equals the official FPL player code.

Ambiguous candidates, missing history, team conflicts, and code conflicts are excluded and counted by reason.

## Features and target

The local panel includes 11footy player-match minutes, goals, assists, shots, shots on target, key passes, event-count attempts, big chances, offsides, fouls and tracked-shot xG where available. It also carries the same-fixture official FPL minutes, points, goals and assists as descriptive targets.

The same-match provider features must **not** be used to predict that same match's FPL points. Any future predictive experiment must shift player features to prior matches only, join them to a later fixture, use chronological/rolling-origin validation, and compare against the existing FPL-only lagged baseline. It must report coverage and sensitivity to identity confidence. No promotion to production is allowed without demonstrated incremental predictive value and independent identity verification.

## Privacy and licensing

Player-level provisional rows and source data remain inside the GitHub Actions runner and are not uploaded. The published integration artifact contains aggregate counts and source hashes only. 11footy is CC BY-NC 4.0 and may be used only for non-commercial purposes under that licence. The FPL underlying data remains owned by Fantasy Premier League; no commercial rights are claimed.

## Current status

The current pipeline writes the isolated panel and publishes only its aggregate row/player/fixture counts. Prediction validation remains not evaluated. The next engineering step is a separate lagged research builder and walk-forward evaluation, not feeding this file into the verified panel or live recommendation engines.
