# Wyscout–FPL historical source audit — 2026-11-17

## Decision

**Promising historical event source with a published CC BY 4.0 grant; not ready for FPL integration until historical FPL target-data rights and point-in-time provenance are resolved.**

The Pappalardo–Massucco Wyscout collection provides an English Premier League 2017/18 event season that overlaps the 2017/18 FPL archive season. This is a concrete alternative to the non-overlapping StatsBomb Open Data seasons. It is a separate provider and must remain a separate adapter/ID namespace; do not relabel Wyscout IDs as StatsBomb IDs.

## Event-data provenance and license

Official Figshare collection:
- https://figshare.com/collections/Soccer_match_event_dataset/4415000
- DOI: https://doi.org/10.6084/m9.figshare.c.4415000.v5
- Collection description states that the event data was collected by Wyscout and contains spatio-temporal match events.

Official data items and their displayed license:
- Events: https://figshare.com/articles/dataset/Events/7770599 — CC BY 4.0.
- Matches: https://figshare.com/articles/dataset/Matches/7770422 — CC BY 4.0.
- Players: https://figshare.com/articles/dataset/Players/7765196 — CC BY 4.0.
- Teams: https://figshare.com/articles/dataset/Teams/7765310 — CC BY 4.0.
- Competitions: https://figshare.com/articles/dataset/Competitions/7765316 — CC BY 4.0.
- Data paper: Pappalardo et al. (2019), https://doi.org/10.1038/s41597-019-0247-7.

The published data description reports the 2017/18 English first division as 380 matches, 643,150 events, and 603 players. The collection contains match, event, player, team, and competition records. The event schema includes Wyscout `playerId`, `teamId`, `matchId`, event type/subtype, tags, match period, event time, and start/end coordinates. The match schema includes UTC date, competition, gameweek/round, teams, lineups, benches, and substitutions. The player schema includes Wyscout `wyId`, first/middle/last names, and `currentTeamId`.

The CC BY 4.0 grant is visible on the official Figshare item pages. Preserve attribution and the paper citations in any derived dataset or documentation.

## Structural inspection performed

A public processed mirror was inspected:
- https://github.com/koenvo/wyscout-soccer-match-event-dataset
- README identifies 380 English Premier League matches from 2017/18 and says the data is released under CC BY 4.0.
- Its match index includes Premier League fixtures beginning with match ID 2499719 (Arsenal vs Leicester City, 11 August 2017).
- One processed match file (2499719) was inspected. It contains event-level Wyscout IDs, team IDs, event types, tags, periods, times, and positions.

Important reconciliation caveat:
- The paper reports 4,299 players across all competitions.
- The inspected mirror's `raw_data/players.json` contains 3,603 player records; 442 of those records have a `currentTeamId` that maps to one of the 20 Premier League clubs.
- The 442 count is **not** the published 603-player season participation count: `currentTeamId` is a current-team field, not a match-level appearance history, and can omit players who moved during/after the season. The mirror's player-count difference must be reconciled against the official Figshare release before full ingestion.
- The full 73.74 MB Events archive was not materialized in this run. No full-season Wyscout ingestion or feature parity test has been claimed.

## Preliminary identity screening (candidate-only)

The 2017/18 FPL historical archive in https://github.com/vaastav/Fantasy-Premier-League contains:
- `data/2017-18/players_raw.csv`: 647 player rows.
- `data/2017-18/cleaned_players.csv`: 647 player rows.
- `data/2017-18/gws/gw1.csv` through `gw38.csv`: all 38 gameweeks.

A preliminary normalized full-name screen found:
- 442 Wyscout player records currently associated with the 20 Premier League clubs.
- 303 exact normalized full-name candidates against the 2017/18 FPL player list.
- 139 without an exact full-name match.
- No duplicate exact-name hits in this limited screen.

These are **candidate counts only**, not verified identity joins. No rows were added to the project's verified crosswalk. The screen did not establish match-level team membership for every player, did not resolve all name variants/transliterations, and did not prove that one provider ID maps to one FPL element for the relevant season. Continue to require provider ID, season, competition, team, and source evidence before a row can be marked verified.

## FPL historical data-rights blocker

The Vaastav repository's LICENSE grants MIT rights to the repository software but explicitly states that the data is property of Fantasy Premier League and Understat and that the repository author does not own it:
- https://github.com/vaastav/Fantasy-Premier-League/blob/master/LICENSE

Therefore the repository's MIT software license is **not** a data-use grant. The 2017/18 FPL files are publicly retrievable, but their reuse/redistribution rights are not cleared by that repository license. Do not copy them into the production project, redistribute them, or make them a production dependency without authorization or a separate permitted source.

The historical archive also appears to be a retrospective data snapshot. Even if use is authorized, a strict backtest still needs archived pre-deadline FPL vintages or another way to prove that historical predictors were available at each deadline. The current official 2026/27 API snapshot cannot supply those historical vintages.

## Engineering path if FPL target rights are cleared

1. Obtain an authorized 2017/18 FPL player-gameweek target dataset or written permission for the historical archive.
2. Download and pin the official Figshare Wyscout Events, Matches, Players, Teams, and Competitions items; record source URLs, versions, SHA-256 hashes, and attribution.
3. Reconcile the official player file count and the published 603 EPL-player coverage before building the season roster.
4. Build a separate `wyscout` provider adapter. Keep `wyId`, team IDs, match IDs, and event IDs distinct from StatsBomb identifiers.
5. Validate all 380 EPL matches, event counts, match dates, team assignments, lineups, and player appearances.
6. Create a season/competition/team-scoped Wyscout-to-FPL candidate crosswalk; promote only evidence-backed rows to verified.
7. Align Wyscout match dates and FPL gameweek fixtures, then build deadline-safe player-gameweek features and targets.
8. Run leakage checks and time-ordered backtests. Do not claim predictive validity from name overlap, structural joins, or Python–JavaScript parity alone.

## Current conclusion

Wyscout 2017/18 is the strongest historical event-side candidate found in this run: it has a published CC BY 4.0 grant and a season overlapping the FPL archive. It does **not** by itself clear the FPL target-data rights or point-in-time snapshot problem. The next external requirement is an authorized historical FPL target source (or user-provided permission/source); until then, keep the StatsBomb core and 2026/27 FPL-only pipeline separate and exploratory.
