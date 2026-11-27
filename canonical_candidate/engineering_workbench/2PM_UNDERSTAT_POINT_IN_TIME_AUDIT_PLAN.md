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
2. Identify the first commit in which each match row appears. Record the commit's author and committer timestamps as evidence, but do not treat either as a verified public-publication timestamp: a commit can be created locally and pushed later.
3. Record the repository, pinned commit, file path, row key, first-appearance commit SHA, commit author/committer timestamps, and independently evidenced public-publication timestamp (if available).
4. For each player/team history token, admit a row only when both the football match cutoff and a verified public-source-availability timestamp are strictly earlier than the token cutoff. The commit timestamp is only a lower bound: if it is after the token cutoff, the row is definitely unavailable; if it is before the cutoff, availability remains unresolved until push/publication timing is independently evidenced:

   effective_available_at = max(match_available_at, understat_source_available_at)

   A row is eligible only when effective_available_at < token_cutoff.
5. If a row cannot be assigned a verified public-availability timestamp, mark it unavailable/unverified. Do not infer publication time from its match date or assume the commit timestamp equals the push time.
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
- first_appearance_commit, first_appearance_author_time, first_appearance_committer_time, verified_publication_time;
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

As of 2026-11-27, manifest 1.7.0 applies this HOLD to **152 Understat-derived features**: 30 player-history features, 120 own/opponent team rolling features, and two direct deadline league-rank fields. This corrects the previous 100-feature mask, which omitted player xGChain/xGBuildup and team/opponent goals/rank context even though those values are reconstructed from Understat histories. The exact ordered inventory is generated from the pinned 286-feature schema and stored in the manifest. The training loader also reapplies this HOLD to older tensor artifacts at load time.

All Understat-derived features remain **HOLD** until one of these is completed:

- the row-level vintage manifest is generated and validated for every relevant season, including verified public-publication timestamps (not commit timestamps alone); or
- a reviewed exclusion policy explicitly masks unverified Understat source rows/seasons.

No training, validation-fold fitting, or OOT scoring may consume an Understat value solely because it is finite in the latest pinned file or a live fallback response.


## 7. Commit-time limitation

Git commit author/committer timestamps are not the same as the time a commit became publicly fetchable. A commit can be created locally and pushed later. Therefore:

- A first-appearance commit timestamp after a target cutoff is sufficient evidence that the row was not in that repository commit history by the cutoff.
- A first-appearance commit timestamp before a target cutoff is only necessary evidence, not sufficient proof that the row was publicly available by the cutoff.
- Do not turn a pre-deadline commit timestamp into a verified source-availability timestamp without push/publication evidence. A guessed fixed delay is not proof.
- If the public push time cannot be recovered from a contemporaneous archive or other reliable evidence, keep the row unverified and its Understat observed-value mask at zero.

This is deliberately conservative. The audit may prove some rows unavailable, but it must not claim historical availability from commit dates alone.


## 8. Evidence pointers

- Pinned Dastan acquisition logic: https://github.com/qazybekb/smartplayfpl-dastan/blob/758db9247e8b3a9a870c991064f74d8339d61cd0/dastan/rebuild/sources.py
- Pinned Vaastav 2020/21 Understat directory: https://github.com/vaastav/Fantasy-Premier-League/tree/8c97b2adb123863c3dd581e730f1360e89815ac2/data/2020-21/understat
- 2020/21 aggregate player table: https://github.com/vaastav/Fantasy-Premier-League/blob/8c97b2adb123863c3dd581e730f1360e89815ac2/data/2020-21/understat/understat_player.csv
- 2020/21 Arsenal match-level team file: https://github.com/vaastav/Fantasy-Premier-League/blob/8c97b2adb123863c3dd581e730f1360e89815ac2/data/2020-21/understat/understat_Arsenal.csv
- 2021/22 Bruno Fernandes multi-season player file: https://github.com/vaastav/Fantasy-Premier-League/blob/8c97b2adb123863c3dd581e730f1360e89815ac2/data/2021-22/understat/Bruno_Fernandes_1228.csv
- Bruno file history: https://api.github.com/repos/vaastav/Fantasy-Premier-League/commits?path=data%2F2021-22%2Funderstat%2FBruno_Fernandes_1228.csv&per_page=100

## 9. Pinned-tree inventory cross-check (2026-11-27)

The pinned Vaastav Git tree at `8c97b2adb123863c3dd581e730f1360e89815ac2` was independently enumerated (recursive tree returned 25,924 entries; not truncated). The six-season Understat CSV inventory is:

| Season | Individual player match-history CSVs | Team match CSVs | Aggregate player file |
|---|---:|---:|---|
| 2020/21 | 0 | 23 | Yes |
| 2021/22 | 712 | 23 | Yes |
| 2022/23 | 554 | 20 | Yes |
| 2023/24 | 774 | 23 | Yes |
| 2024/25 | 765 | 23 | Yes |
| 2025/26 | 0 | 0 | No |

This confirms the **season-directory** source structure, but it must not be mistaken for the final Dastan player-history input structure. At the pinned Dastan commit, `_latest_player_paths` scans the entire pinned Vaastav tree and selects the latest-season individual CSV for each mapped player ID, regardless of the target historical season. The selected CSV is downloaded once per player and checked against the expected played FPL dates across all six requested seasons. If dates are missing, the downloader requests a live Understat player-history JSON snapshot; when present, that JSON supersedes the pinned CSV for that player across every requested season.

Consequently, 2020/21 individual player histories are **not structurally absent from the reconstructed Dastan player dataset** merely because the 2020/21 directory has no per-player CSVs. They may be supplied by later-season multi-season player CSVs. For example, the pinned 2021/22 Bruno Fernandes file's first recorded repository commit (2021-08-24 20:21:52 UTC) contains 148 match rows spanning 2014-08-31 through 2021-08-22, including 37 rows in 2020/21 and two in 2021/22. The pinned 2024/25 Mohamed Salah file's initial commit (2024-08-15 17:16:49 UTC) already contains 334 rows spanning 2014-09-13 through 2024-05-19. This demonstrates multi-season history in later-season files; it does **not** prove those older rows were available at their original historical deadlines.

The team path is different: Dastan loads season-specific team CSVs and, when a season is incomplete, a live team fallback supersedes that season's pinned team files. The 2020/21 Arsenal team file's first commit is 2020-08-21 04:49:25 UTC; the 2021/22 Arsenal team file's first commit is 2021-07-21 20:57:13 UTC. These dates and the file histories make a separate season-specific team-row vintage audit feasible, but commit timestamps alone are not proof of public availability.

For 2025/26, the pinned Vaastav tree has no Understat CSVs; Dastan's completeness logic therefore relies on the live fallback path for player and team coverage. The fallback is a mutable provider snapshot, not a historical deadline archive. The downloader's `downloads.json` records one acquisition timestamp and per-file hashes, but does not record a verified first-publication timestamp or a historical provider version for each row.

The inventory is therefore source-structure evidence only. Player and team feature subfamilies must be audited separately. The next audit must reconstruct **first row appearance by source path and commit**, distinguish player CSVs from live fallback JSON, identify which rows existed before each target cutoff, and retain all rows with unverified public-availability time as HOLD. A player-history exclusion must not automatically remove team-context features for the same season.
