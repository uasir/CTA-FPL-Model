# Opta/PulseLive–FPL source audit — 2026-11-17

## Decision

**Promising technical source; not approved for production ingestion yet.** The repository below appears to provide a same-season link between current FPL player records and Premier League/PulseLive player and team statistics. It is a separate provider from StatsBomb and must not be treated as StatsBomb event data.

Source repository: https://github.com/imadeddine-belkat/Premier-League-Stats
Pinned source commit: `f0f3d40f803c69bc7fac48d0748b49175e2d08ce` (2026-11-09)
Source README: https://github.com/imadeddine-belkat/Premier-League-Stats/blob/main/README.md

## Reproducible 2026/27 snapshot inspection

Files inspected at the pinned repository state:

- `fpl_scraper/fpl_stats/_merged/players/2026-27_all_players_gw.csv`
- `pl_stats/_merged/players/2026-27_players_stats.csv`
- `pl_stats/_merged/events/2026-27_events_stats.csv`
- `pl_stats/_index/2026-27_players.json`

Observed counts:

| Check | Result |
|---|---:|
| FPL player-gameweek rows | 6,562 |
| Unique FPL player codes | 672 |
| PL/PulseLive player-season rows | 511 |
| Shared unique player IDs | 511/511 |
| Shared IDs with matching team IDs | 511/511 |
| Full-name matches after diacritic/punctuation normalization | 444/511 |
| PL/PulseLive team-match event rows | 200 |
| Unique event match IDs | 100 |
| Event match IDs present in FPL fixture codes | 100/100 |
| Event matches with exactly two team rows | 100/100 |
| FPL fixtures in season file | 380 |

The 67 non-exact name comparisons are consistent with different display-name conventions (for example, full legal names versus short names). The numeric ID and team-ID checks are stronger than name equality for this sample. The numeric provider IDs remain a distinct identifier namespace and must be labelled `Opta/PulseLive playerId`, not StatsBomb ID.

The 161 FPL player codes without a PL player-season row are not automatically errors; they may not yet have a PL appearance or may be outside the provider's current player-stat coverage.

## Important repository discrepancy

The README describes per-player, per-match files under `players_match_stats`. The inspected repository tree at the pinned commit contains no such CSV outputs or directory; it contains player-season aggregates under `players_stats` and team-match event aggregates under `events_stats`. The only tree path matching `players_match_stats` is a merge script. Therefore this audit does **not** establish availability of player-level match event metrics.

Available in the inspected snapshot:
- FPL player-by-fixture outcomes and underlying FPL statistics.
- Opta/PulseLive player-season aggregate metrics.
- Opta/PulseLive team-match event aggregates.

Not established:
- Player-level Opta/PulseLive per-match event metrics.
- StatsBomb event JSON or StatsBomb player IDs.
- Point-in-time historical snapshots of the cumulative player-season aggregate files.

## Leakage-safe use if rights are cleared

Potential separate Opta/PulseLive adapter:
1. Join `player_code` to `playerId` only after rechecking the exact season's ID and team-ID coverage.
2. Resolve the season's FPL element ID from the official FPL bootstrap; do not confuse `element`, `player_code`, and `playerId`.
3. Join FPL player-fixture outcomes to team-match event data through the fixture ID, and infer the player's match team from the fixture's home/away team IDs plus `was_home`.
4. Use only prior-match team event metrics (rolling or expanding windows) for prediction. The current fixture's event metrics are post-match and would leak the target.
5. Use prior-season player aggregates as preseason priors. Do not use final/current-season aggregates to backtest earlier gameweeks.
6. Keep this feature family labelled Opta/PulseLive. It does not replace or validate the recovered StatsBomb Python/JavaScript core.

## Rights and provenance blocker

The README displays an MIT license badge, but the repository root listing has no visible LICENSE file and GitHub's repository metadata reports `license: null`. The README also states that the underlying historical PL archive comes from Premier League/PulseLive feeds and that the dataset is unofficial. The underlying data-use and redistribution rights are therefore **unverified**.

Do not copy these datasets into CTA-FPL-Model, redistribute them, or make them a production dependency until the source owner and applicable data terms are confirmed. The inspection above is a structural research audit, not a legal clearance or a claim that the data is independently verified.

## Engineering next step

Resolve data-use permission. If permission is confirmed, build an isolated Opta/PulseLive adapter with pinned source commits, row/hash manifests, ID/fixture reconciliation, lagged team features, and time-ordered backtests. Keep StatsBomb parity and the Opta/PulseLive adapter as separate providers.

## Live 2026/27 integration update — 2026-11-18

The technical identity and team-fixture adapter has now been run against the pinned source commit and a live official FPL bootstrap/fixture snapshot.

- Actions run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44352173248
- Aggregate artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44352173248/artifacts/14448343224
- Pinned provider commit: `f0f3d40f803c69bc7fac48d0748b49175e2d08ce`.

**Identity mapping is now verified for this snapshot:**
- 511/511 provider `playerId` values exactly equal an official FPL `code`.
- 511/511 also have matching team IDs when comparing provider `team_id` to FPL team `code`.
- This is not a comparison to FPL's internal team `id`. The adapter preserves both the internal FPL team ID and the FPL team code as separate fields.
- The verified runtime crosswalk maps 511 provider players to FPL element IDs. 161 of 672 FPL players have no provider player-season row; no fuzzy-name fill is attempted.
- Strict validator accepted 511/511 rows, with no duplicate or team-code errors.

**Team-match feature adapter:**
- Provider `matchId` matches FPL fixture `code`, not FPL fixture `id`; 100/100 provider match IDs reconcile.
- 200 team-match rows form 100 matches with exactly two team rows each; no unknown provider team codes.
- 760 fixture-team rows and 18,816 prospective player-fixture rows were generated.
- Ten team-level metrics are lagged over the previous maximum three matches, with provider kickoff values interpreted as Europe/London when timezone-naive and converted to UTC. The target fixture's own provider match ID is excluded.
- Current FPL roster assignments are emitted only for unfinished fixtures strictly after the run's as-of time; they are not back-projected onto completed fixtures.

**Interpretation remains limited:** the provider file is a current cumulative snapshot, not an archived series of deadline vintages. Team features are `PASS_STRUCTURAL_ONLY` and point-in-time status remains `NOT_VERIFIED`; do not use them for strict historical backtests or predictive recommendation scoring yet. The pinned repository snapshot does not contain player-level per-match event metrics. Underlying Premier League/PulseLive data rights remain unverified. The workflow uploads only aggregate counts and source hashes, not raw data, crosswalk rows or player-fixture outputs.
