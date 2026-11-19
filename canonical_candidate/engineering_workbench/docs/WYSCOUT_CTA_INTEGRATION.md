# Wyscout EPL 2017/18 CTA player-match feature layer

Status: **STRUCTURAL RESEARCH LAYER / FPL IDENTITY NOT MAPPED / PREDICTION NOT EVALUATED**

## Purpose

The Wyscout 2017/18 English Premier League release is an independent event-level source that complements the current-season 11footy player-match statistics and sampled StatsBomb 360 spatial context. This adapter converts its event stream into season-scoped provider-native player-match features. It does not replace either source.

The public Pappalardo–Massucco dataset contains 643,150 EPL events across 380 matches. The data paper describes event types, player/team IDs, timestamps, tags and start/end coordinates, and releases the data under CC BY 4.0:
- Paper: https://doi.org/10.1038/s41597-019-0247-7
- Events: Figshare file 14464685
- Matches: Figshare file 14464622
- Players: Figshare file 15073721
- Teams: Figshare file 15073697

## Feature dimensions

The player-match layer separates:

- **Threat creation:** pass attempts and completions; progressive passes; final-third entries; provisional danger-zone entries; key, smart, through and opportunity passes.
- **Threat involvement/reception:** not attributed in this source because the public event schema does not provide a pass-recipient identity. The event actor is not assumed to be the receiver.
- **Threat realisation:** shot attempts, accurate shot attempts, goals, own goals and shot-opportunity tags. Goal and own-goal event tags are reconciled against the sum of both teams' match metadata scores. No xG is supplied by this release.
- **Supporting context:** progressive acceleration/carry events, dangerous-ball-loss tags, offsides and duel outcomes.

Threat-creation pass attempts use the union of the relevant indicators and are counted once per pass event, even when several indicators apply. Attempted and completed actions remain separate.

## Coordinate and tag conventions

The paper defines Wyscout event coordinates as percentages of the pitch from the attacking team's perspective: x increases toward the opponent goal. The adapter therefore does not infer a global home/away direction.

The implementation uses the documented event tags:
- 1801 accurate
- 1802 not accurate
- 101 goal
- 301 assist
- 302 key pass
- 201 opportunity
- 901 through
- 2001 dangerous ball lost
- 701 lost duel
- 703 won duel

See the Wyscout event/tag reference: https://support.wyscout.com/matches-wyid-events

## Provisional geometric features

- Progressive pass: end x minus start x is at least 10 percentage points.
- Final-third entry: pass starts below x=66.67 and ends at or above x=66.67.
- Danger-zone entry: pass endpoint x is at least 80 and y is between 20 and 80. This is an explicitly provisional geometric proxy, not a calibrated penalty-area definition, xG or proof of a genuine scoring opportunity.
- Progressive carry: an Others on the ball / Acceleration event advances at least 10 x-percentage points.

These thresholds must be sensitivity-tested and are not promoted to validated CTA weights.

## Identity and publication safeguards

- Provider player IDs remain Wyscout IDs. No FPL identity is inferred.
- The player-match CSV is generated only inside the Actions runner and is not uploaded.
- The uploaded artifact contains aggregate counts, feature definitions and source hashes only.
- Receiver identity and xG remain explicitly unavailable.
- The output is marked structural research only; predictive validation is NOT_EVALUATED.
- Attribution: Pappalardo and Massucco (2019), Wyscout event collection, CC BY 4.0.

## Next integration steps

1. Establish a season-scoped Wyscout-to-FPL identity crosswalk with independent source evidence.
2. Join only verified identities to historical FPL points; keep unmatched and ambiguous IDs isolated.
3. Validate fixture/player coverage and compare the provider features against actual FPL returns.
4. Evaluate whether these features add chronological out-of-sample value beyond minutes, xG/xA and prior points baselines.
