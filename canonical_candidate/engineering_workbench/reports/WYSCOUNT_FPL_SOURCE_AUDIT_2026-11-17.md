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

## Match-level identity reconciliation — 2026-11-18

A strict match-roster reconciliation has now produced a **verified partial identity crosswalk**. It supersedes the earlier `currentTeamId`-only name screen for join decisions. The global player metadata `currentTeamId` is not used as season-team evidence because it can reflect transfers after the target season.

### Pinned inputs

- Wyscout processed mirror: `koenvo/wyscout-soccer-match-event-dataset`, commit `ebc4c54c1093c420a81ce442c69e4186fab33bb4`.
- FPL historical player archive: `vaastav/Fantasy-Premier-League`, commit `d7b05b51d137bfefef4b692386d18c610975b9b9`.
- FPL input: `data/2017-18/players_raw.csv`, Git blob `117a93b6bb6a093d790381c9347662a7d1e6defa`, 647 rows.
- Wyscout input: 10 final-gameweek match roster files, all from 13 May 2018:
  `2500089` through `2500098` (Burnley–Bournemouth, Crystal Palace–West Brom, Huddersfield–Arsenal, Liverpool–Brighton, Manchester United–Watford, Newcastle–Chelsea, Southampton–Manchester City, Swansea–Stoke, Tottenham–Leicester, West Ham–Everton).
- Each processed match file exposes the two club IDs and the matchday roster with numeric Wyscout `playerId`, first/last name and team context. The Wyscout EPL competition ID is `364`.

### Reconciliation method

1. Parse the FPL 2017/18 player list (FPL element ID, player code, first name, second name, web name and FPL team ID).
2. Parse the 10 Wyscout final-round match rosters (Wyscout player ID, first/last name, short name, match ID, team ID and team name).
3. Generate exact normalized full-name matches only; normalization removes diacritics and punctuation but does not reorder or approximate names.
4. Infer the 20-club FPL-team-ID → Wyscout-team-ID map from exact full-name matches only. Each FPL team has 9–16 independent full-name votes, every vote agrees on one provider team, and the 20 provider team IDs are one-to-one.
5. Accept the 251 exact full-name matches only when their match-roster team agrees with that unanimous club mapping.
6. Add five further exact official-alias matches only where FPL `web_name` exactly equals Wyscout `shortName` and the provider player is unique within the mapped club. These use `official_alias`, not fuzzy matching.
7. Reject all remaining players from the verified crosswalk. No fuzzy, phonetic, or manual spelling guesses are used.

### Result

- **256 verified player identity rows** in `canonical_candidate/data/wyscout_fpl_identity_crosswalk.csv`.
- 251 rows use `club_roster_crosscheck`; 5 use exact `official_alias`.
- 245/256 mapped players have positive FPL season minutes.
- 256/647 (39.6%) of all FPL player rows are mapped; 245/515 (47.6%) of players with positive minutes are mapped.
- 20/20 FPL team IDs map to unique Wyscout team IDs, with 100% agreement among 9–16 full-name votes per club.
- Zero duplicate FPL element IDs and zero duplicate Wyscout player IDs.
- Evidence URLs are pinned to the exact Wyscout match roster file for each player; evidence-source fields also record the FPL archive commit and source CSV blob.

This is a **verified partial identity crosswalk**, not a full-season player coverage claim. The 10 matchday rosters contain 360 distinct Wyscout player records; the remaining FPL players require additional match rosters or other season-specific evidence. The `verified` status means the player identity/team join is evidenced; it does not grant rights to the FPL target data or establish point-in-time provenance.

### 20-club team mapping

| FPL team ID | Wyscout team ID | Club | Exact full-name votes |
|---:|---:|---|---:|
| 1 | 1609 | Arsenal | 11 |
| 2 | 1659 | AFC Bournemouth | 15 |
| 3 | 1651 | Brighton & Hove Albion | 11 |
| 4 | 1646 | Burnley | 16 |
| 5 | 1610 | Chelsea | 9 |
| 6 | 1628 | Crystal Palace | 13 |
| 7 | 1623 | Everton | 11 |
| 8 | 1673 | Huddersfield Town | 12 |
| 9 | 1631 | Leicester City | 15 |
| 10 | 1612 | Liverpool | 13 |
| 11 | 1625 | Manchester City | 13 |
| 12 | 1611 | Manchester United | 10 |
| 13 | 1613 | Newcastle United | 9 |
| 14 | 1619 | Southampton | 14 |
| 15 | 1639 | Stoke City | 15 |
| 16 | 10531 | Swansea City | 14 |
| 17 | 1624 | Tottenham Hotspur | 14 |
| 18 | 1644 | Watford | 12 |
| 19 | 1627 | West Bromwich Albion | 15 |
| 20 | 1633 | West Ham United | 9 |

The FPL historical archive rights and point-in-time vintage issues below remain separate blockers. The identity crosswalk can be structurally validated without promoting the historical points data to a production target.

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
