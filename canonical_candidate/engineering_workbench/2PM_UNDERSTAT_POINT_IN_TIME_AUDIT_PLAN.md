# 2PM Understat Point-in-Time Source-Vintage Audit

**Status:** HOLD — audit design and initial repository evidence recorded; no Understat feature is admitted.

## 1. Why this audit is required

The current 2PM source-observation sidecar records whether a value exists in the reconstructed source history. That is not sufficient for Understat. A value may be present in a pinned repository file today even though that file version was not published until after the historical target deadline.

The pinned Dastan source (qazybekb/smartplayfpl-dastan, commit 758db9247e8b3a9a870c991064f74d8339d61cd0) has three relevant behaviors in dastan/rebuild/sources.py:

- _latest_player_paths() selects the latest season-path for each Understat player ID from the pinned Vaastav tree.
- _incomplete_pinned_players() checks whether the selected file covers all expected played FPL match dates. It does not check when each row or file version was committed.
- _fetch_understat_fallbacks() obtains missing player histories and team seasons from the live Understat API. load_understat_player_matches() lets a live fallback JSON supersede the pinned CSV.

Consequently, a complete match history is not automatically a point-in-time-safe match history. A match_available_at = kickoff + 24 hours value is only a football-data availability convention; it does not prove that the particular Understat row existed in the pinned source by that time.

## 2. Verified repository evidence

Pinned Vaastav source: vaastav/Fantasy-Premier-League, commit 8c97b2adb123863c3dd581e730f1360e89815ac2.

### 2.1 2020/21 player and team files are different source types

The pinned data/2020-21/understat/ directory contains team match files such as understat_Arsenal.csv and an understat_player.csv aggregate. The aggregate header is:

id,player_name,games,time,goals,xG,assists,xA,shots,key_passes,yellow_cards,red_cards,position,team_title,npg,npxG,xGChain,xGBuildup

It has season totals and no match-date column. The pinned 2020/21 directory contains no individual player match-history CSVs of the later <player>_<understat_id>.csv form. Therefore, the aggregate player file cannot support player rolling features at historical match-token cutoffs.

The 2020/21 team files are match-level and have a date column. The Arsenal team file has 40 commits in its file history, from the initial scrape on 2020-08-21 through the GW38 update on 2021-05-24. This is evidence that team match rows were versioned during the season, but each row's exact first-available commit still needs reconstruction.

**Initial conclusion:** Understat player-history features should be structurally unavailable for 2020/21 under this pinned source. Do not scrap the whole 2020/21 season on this basis. Audit 2020/21 team-context features separately.

### 2.2 2021/22 player files contain retrospective seasons

The pinned tree has individual player match-history files from 2021/22 onward. For example, data/2021-22/understat/Bruno_Fernandes_1228.csv contains dated match rows with a season field. The pinned file includes rows for seasons 2021, 2020, 2019, 2016, 2015, and 2014.

Its file history begins on **2021-08-24 20:21:52 UTC** (Add understat weekly data for players) and continues with weekly updates through **2022-05-23 11:50:22 UTC** (Add GW38 data). Thus the presence of 2020/21 rows in this later file does not establish that they were available during 2020/21.

The 2021/22 Arsenal team file begins on 2021-07-21 and also has weekly updates. Player and team file histories must be evaluated separately.

### 2.3 Current latest-file selection creates vintage risk

Selecting a player's latest file from 2024/25 or another later season can import older match rows that were only added to the repository after their historical deadlines. The current row-date cutoff alone cannot distinguish those rows.

The live fallback is even less suitable for historical training: a JSON response fetched during a later rebuild is a current provider response, not a historical snapshot. Its hash proves the downloaded bytes, not historical availability.

## 3. Required row-level vintage reconstruction

For each pinned player and team source file:

1. Enumerate the file's Git history at the pinned Vaastav commit.
2. Identify the first commit in which each match row appears. Use the commit's committer timestamp as a conservative source-publication timestamp.
3. Record the repository, pinned commit, file path, row key, first-appearance commit SHA, and source-publication timestamp.
4. For each player/team history token, admit a row only when both the football match cutoff and the source-publication cutoff are strictly earlier than the token cutoff:

   effective_available_at = max(match_available_at, understat_source_available_at)

   A row is eligible only when effective_available_at < token_cutoff.
5. If a row cannot be assigned a reliable first-appearance timestamp, mark it unavailable. Do not infer publication time from its match date.
6. Treat a live-fallback row as unavailable for historical point-in-time training unless a separately archived response proves it was captured before the token cutoff.
7. Preserve the distinction between an observed zero, a missing row, a structurally unavailable season/source, and a row whose first source publication was after the token cutoff.

For large commits, GitHub's commit-details endpoint may cap the returned file list. The audit must detect incomplete commit file listings and use file-specific history or raw-file-at-commit checks rather than assuming an omitted file was unchanged.

## 4. Season-level policy pending the audit

| Season | Player Understat | Team Understat | Interim policy |
|---|---|---|---|
| 2020/21 | Only aggregate player totals in pinned season directory; no player match-history files | Match-level team files with weekly commit history | Player Understat structurally unavailable; audit team rows by commit vintage |
| 2021/22 | Individual player histories begin in August 2021 and are updated weekly | Match-level team files updated weekly | Reconstruct per-row first-commit timestamps; early deadlines may lack source coverage |
| 2022/23 | Individual player histories and season/team files | Match-level team files | Reconstruct per-row first-commit timestamps |
| 2023/24 | Individual player histories and season/team files | Match-level team files | Reconstruct per-row first-commit timestamps |
| 2024/25 | Individual player histories and season/team files | Match-level team files | Reconstruct per-row first-commit timestamps |
| 2025/26 | No pinned Vaastav Understat season directory; Dastan can use live fallback | No pinned Vaastav Understat season directory; Dastan can use live fallback | Unavailable for historical PIT use unless a pre-deadline archive is proven |
| 2026/27 | Live/current source only unless historical snapshots were captured | Live/current source only unless historical snapshots were captured | Sealed OOT labels; Understat inputs require a snapshot timestamp before each actual deadline |

This is a policy for Understat-derived features only. It does not automatically exclude FPL-native player history, market snapshots, fixture context, or other independently validated feature families from those seasons.

## 5. Implementation contract

The audit should produce a versioned understat_point_in_time_manifest keyed by (source_type, season, entity_id, match_date) with:

- source_kind: pinned CSV, live fallback JSON, or other explicitly named source;
- source_repository, source_commit, source_path;
- first_appearance_commit, first_appearance_committer_time;
- match_available_at, effective_available_at;
- row_present, vintage_verified, and a reason code;
- audit method/version and content hashes.

The player-history and team-context builders must consume this manifest before producing __observed__{feature} sidecars. Understat-derived observed-value masks must be zero when source vintage is unverified or after the token cutoff, even if the current CSV contains a finite value. The raw-source sidecar may record that a value exists in the current file; the source-vintage policy must still suppress it. The original feature value may remain in the diagnostic candidate, but it must not be presented to the model as observed.

Add regression tests for:
- a row committed before versus after the token cutoff;
- a later-season file containing earlier-season rows;
- 2020/21 aggregate player data with no match date;
- live fallback superseding a partial pinned CSV;
- a missing or incomplete commit patch/file listing;
- strict equality at the cutoff (not eligible);
- zero values that are genuinely present versus missing rows.

## 6. Admission gate

All Understat-derived features remain **HOLD** until one of these is completed:

- the row-level vintage manifest is generated and validated for every relevant season; or
- a reviewed exclusion policy explicitly masks unverified Understat source rows/seasons.

No training, validation-fold fitting, or OOT scoring may consume an Understat value solely because it is finite in the latest pinned file or a live fallback response.
