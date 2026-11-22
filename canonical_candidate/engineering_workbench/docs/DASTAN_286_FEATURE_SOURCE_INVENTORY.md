# Dastan 286-Feature Source Inventory

**Purpose:** Reproduce the exact Dastan minutes-model input frame for CTA. This is an engineering inventory, not a claim that the CTA feature builder is complete.

**Pinned contract:** `config/dastan_minutes_feature_schema.json` (286 ordered columns).

## 1. Exact schema composition

Counts below are computed from the pinned `feature_order` in CTA's schema artifact, not copied from the upstream prose summary.

| Feature group | Columns | Count | Primary source / construction |
|---|---|---:|---|
| Player rolling | `player_*` | 115 | FPL player-match statistics plus Understat player attacking metrics; 23 source metrics × 5 windows |
| Own-team rolling | `team_*` | 60 | Understat team-match metrics and pre-match league ranks; 12 metrics × 5 windows |
| Opponent rolling/context | `opp_*` | 61 | 60 rolling opponent metrics (12 × 5 windows) plus `opp_status_league_rank` |
| Availability history | `p_any_*`, `p60_*`, `e_minutes_*` | 9 | Lagged FPL appearances, 60+ minute appearances, and minutes; windows 3, 5, 10 |
| Dastan engineered/context | `ar_*` | 32 | Defensive workload rolling stats, threshold rates, starts, rest/congestion and opponent defensive allowance |
| Pre-deadline FPL projection | `ar_ep_next` | 1 | Provenance-checked pre-deadline FPL `ep_next` snapshot |
| Flat context | `is_home_num`, `status_league_rank`, `value`, `selected`, `transfers_balance` | 5 | Venue, own-team rank, price, ownership, transfer balance |
| Pre-deadline availability | `sig_*` | 3 | FPL bootstrap status risk, chance of playing, news presence |
| **Total** | | **286** | |

The upstream `docs/FEATURES.md` family table does not reconcile arithmetically to 286 as currently written (its published family counts sum to 274). CTA's pinned feature list is the executable schema authority. The reconciled count above separates `ar_ep_next` from the 32 `ar_*` engineered features.

## 2. Source and transformation inventory

### A. FPL player-match history

Used by player rolling features and availability history:

- FPL points, minutes, influence, creativity, threat, goals, assists, cards, own goals, saves, penalty events, BPS and bonus.
- FPL defensive contribution, CBIT, recoveries and tackles where available (introduced in 2025-26).
- Start indicators derived from minutes / source match records.
- Lagged rolling means use windows 1, 3, 5, 10 and 38 for player metrics; availability uses 3, 5 and 10.
- Player identity across seasons must use stable `fpl_code`; season-specific `element` IDs are not cross-season identities.

### B. Understat player-match history

Used for player rolling attacking metrics:

- Shots, xG, xA, xGChain, xGBuildup and key passes.
- Join requires audited FPL-to-Understat player identity plus match/date alignment.
- Missing or ambiguous mappings must be surfaced; do not guess by display name alone.

### C. Understat team-match history

Used for own-team and opponent rolling blocks:

- Goals scored/conceded, xG/xGA, deep/deep allowed, PPDA attack/defence and allowed variants.
- Opponent pairing is reconstructed from same-slot home/away team rows using score and xG consistency.
- League rank is calculated from standings accumulated before each match.
- Rolling means use windows 1, 3, 5, 10 and 38.
- Team names require a controlled FPL-to-Understat normalization map.

### D. Dastan engineered features

- Availability history: prior match played, prior match 60+, and prior minutes, grouped by player and season. Position-specific base rates fill the cold-start rows.
- Defensive contribution family: prior rolling averages for defensive contribution, CBIT, recoveries and tackles; defensive-contribution hit/near rates use position-specific thresholds; prior starts rates; defensive contribution points proxy.
- Rest/congestion: days since prior Premier League fixture and team matches in the preceding 14 days.
- Opponent defensive allowance: prior opponent defensive-contribution and tackle totals allowed.
- `ar_ep_next`: provenance-checked FPL `ep_next` captured before the target deadline. It is named with the `ar_` prefix but is a separate source snapshot feature, not calculated by `add_dastan_features()`.

### E. Pre-deadline FPL bootstrap signals

- `sig_status_risk`, `sig_chance_playing`, `sig_has_news`.
- A snapshot is eligible only when it identifies the target GW as next, its deadline matches the official deadline, and capture time is strictly before that deadline.
- These values are snapshot fields, not retrospective current-bootstrap values.

## 3. Temporal and missing-value rules

- Every rolling feature is shifted so the target fixture's result cannot enter its own input.
- All fixtures for the same player in one Gameweek share the same deadline-anchored historical player/team state. Opponent/venue context may differ by fixture.
- Do not let an earlier fixture in a double Gameweek update the features for a later fixture from the same deadline.
- Dastan's loader fills absent pre-deadline snapshot artifact values with `-1.0`.
- Dastan's training matrix fills remaining NaNs with `0.0`; the released inference path applies the same residual NaN-to-zero fill.
- CTA must reproduce the source-specific `-1.0` sentinel stage and then the residual NaN `0.0` fill. Never globally replace all missing values with one constant.
- A genuine zero must remain distinguishable from an unavailable snapshot sentinel.

## 4. Deadline-safety classification for CTA

| Source family | Deadline-safe construction | Main failure mode to guard against |
|---|---|---|
| FPL historical match stats | Use only matches completed before target deadline | Same-GW/double-GW leakage; revised or incomplete history |
| Understat player/team stats | Use only matches completed before deadline; pin/retrieve historical snapshots where possible | Mutable historical corrections; wrong identity or match join |
| Availability history | Derive only from prior completed FPL matches | Same-GW fixture ordering leakage |
| Price / ownership / transfer balance | Use an archived pre-deadline FPL bootstrap vintage | Current values substituted for historical values |
| `ep_next` and `sig_*` | Require target-GW marker, matching deadline, pre-deadline capture timestamp | Post-deadline snapshot or wrong GW association |
| Rest/congestion | Calculate from prior PL fixture schedule only, matching upstream semantics | Omitting cup/European fixtures; do not silently change definition |

## 5. Implementation sequence

1. Reproduce the canonical raw player-match and team-match tables with stable identities and explicit source timestamps.
2. Implement player rolling and availability features.
3. Implement team/opponent rolling features and rank calculations.
4. Implement Dastan engineered defensive/context features.
5. Add pre-deadline snapshot features with strict provenance checks.
6. Apply deadline anchoring across all same-GW fixtures.
7. Apply source-specific missing-value rules, exact 286-column ordering, and row-level coverage diagnostics.
8. Compare reconstructed rows and values against the released feature frame where available; document expected drift from mutable source histories.

**Current status:** Source families and major transformations are identified. Full source-table reconstruction, current-season mapping coverage, and row-level parity are not yet implemented or verified.


## 6. Identity coverage: do not mix mapping populations

The upstream repository exposes three different mapping populations, and their coverage figures must not be combined:

- **Frozen training mapping:** the historical identities used to reproduce the released model frame.
- **Corrected historical mapping:** an audited correction of that model-era population.
- **Operational registry/current-roster projection:** a newer mapping release used for new-season ingestion.

The pinned operational manifest dated 2026-09-07 reports 1,738 registry players, 1,686 mapped, 52 unmapped, and one shared Understat ID. That is the global operational registry, not the 2026-27 roster coverage. The current-roster CSV is a separate season-scoped projection. The upstream mapping README and DATA documentation report different current-roster coverage snapshots (518/577 versus 627/654), so CTA must calculate coverage directly from the exact pinned `fpl_understat_current.csv` artifact and its matching roster, not copy either prose figure.

For CTA's active-season build, retain one row per `(season, fpl_code)`, nullable Understat ID, mapping status, confidence, source manifest ID and source hash. Reject duplicate FPL codes; explicitly flag shared Understat IDs; never fill an unmapped ID with a name-based or fuzzy match. Unmapped players may still receive FPL-only features, but Understat-dependent features must retain their missingness state and be handled through Dastan's exact input policy.


## 7. Canonical raw-table reconstruction contract

The upstream source builder establishes the following raw-table contract. CTA should implement or wrap this sequence without changing the model-facing feature definitions:

| Canonical input | Upstream raw inputs | Join / key | Required fields and checks |
|---|---|---|---|
| FPL player-match table | Vaastav `merged_gw.csv`, `players_raw.csv`, `teams.csv` for each season | Season + element to season roster; stable `fpl_code` thereafter | Filter valid positions; normalize GK to GKP; retain fixture, GW, kickoff, player/team/opponent, minutes and FPL match statistics; reject missing stable codes and duplicate fixture keys |
| Understat player-match table | Pinned Vaastav Understat player CSVs; live Understat player-history fallback where pinned match-date coverage is incomplete | Understat player ID + match date | Validate expected played FPL dates against Understat history; a complete live fallback supersedes an incomplete pinned file; reject duplicate player/date keys |
| Understat team-match table | Pinned Vaastav team CSVs; live Understat EPL team-history fallback for incomplete seasons | Understat team + match date | Normalize team names; parse PPDA into attack/defence and allowed attack/defence components; retain goals, xG/xGA, deep/deep allowed, points and home/away |
| FPL-to-Understat assignment table | Frozen historical assignment intervals plus versioned operational mapping for the active season | `(season, fpl_code)` with first/last GW interval | Frozen training assignments are immutable; active-season mapping must be versioned and coverage-audited; no fuzzy fallback |
| Pre-deadline projection/signal tables | Pinned fplcache snapshots | `(season, gameweek, fpl_code)` | Target GW must be `is_next`, deadline must match, capture must precede deadline with five-minute safety buffer; stale/missing snapshots are refused |

### Source acquisition and reproducibility

The upstream data rebuild pins:
- Vaastav `Fantasy-Premier-League` commit from `data/source_pins.json` for FPL match/roster/team archives and cached Understat histories.
- `Randdalf/fplcache` commit from the same source-pins file for historical pre-deadline bootstrap snapshots.
- `understatapi==0.7.1` as a live fallback when pinned Understat player/team histories are incomplete.

Each download run writes a manifest containing source commits, file sizes and SHA-256 hashes. The rebuild writes a second manifest binding output artifacts to the source-manifest hash. CTA should retain both manifests alongside every generated feature snapshot.

### Frame grain and model-facing projection

The upstream canonical builder returns:
1. player-match rows at `(season, fixture, fpl_code)`;
2. team-match rows at `(season, understat_team, date)`;
3. a season-scoped player lookup.

Its feature builder creates a 304-column frame. The minutes classifier consumes only the exact ordered 286 columns in `models/feature_cols.json`; the remaining columns are identity, targets, or intermediate raw/engineered fields. CTA must retain the richer canonical frame for audit and evaluation, then project the 286 model columns in pinned order only at the inference boundary.

### CTA implementation rule

The current CTA official API ingestion already produces current-season FPL player, fixture and player-fixture CSVs, but it is not a substitute for the historical FPL archive or Understat match tables. Reuse it for live-season operations; build the historical source adapter separately. Never mix current-snapshot API values into a historical pre-deadline training row unless an archived vintage proves availability at that deadline.


## 8. CTA source-pin verification utility

CTA now has a fail-closed verifier at
`scripts/verify_source_pins.py`. Its version-1 pin document records, per
source, a stable source ID, repository, full 40-character commit SHA, and
each acquired file's relative path, expected SHA-256 and required/optional
flag. The verifier:

- resolves every path beneath the declared source root and rejects traversal;
- checks required-file presence and every supplied digest;
- reports optional missing files distinctly from required missing files;
- emits a machine-readable verification manifest with actual hashes and
  explicit PASS/FAIL status; and
- returns a non-zero exit code for missing required files or digest mismatch.

This utility verifies already-acquired files; it does not download archives,
infer upstream paths, or claim that the Vaastav/fplcache inputs have been
acquired. The next ingestion step is to pin the exact upstream commits and
file inventory, then add schema-aware normalizers for each source family.
The verifier's unit tests have been added but have not yet been executed in a
verified CI run.


## 9. First canonical FPL archive normalizer

CTA now has `scripts/normalize_vaastav_fpl_archive.py`, which accepts one
season's `merged_gw.csv`, `players_raw.csv` and `teams.csv` and emits
canonical player-match rows plus a JSON audit report.

The identity chain is exact and season-scoped:
`merged_gw.element -> players_raw.id -> players_raw.code`. The final
`fpl_code` is the stable cross-season identity; the season-specific element
ID is retained separately. The output grain is
`(season, fixture_id, fpl_code)`. It validates duplicate player-fixture keys,
duplicate roster IDs/codes, position against `element_type`, fixture and
kickoff presence, kickoff parsing, and team/opponent references. GK is
normalized to GKP. Display names are never used for identity matching.

Only `minutes` and `total_points` are mandatory match-stat columns in this
first adapter. Other known match-stat columns are preserved when present;
historically unavailable columns remain blank and are listed in the report.
This is intentional schema-variation handling, not imputation. The report
does not claim complete player/fixture coverage: archive completeness and
missing player-fixture combinations must be audited separately before feature
construction.

Unit tests cover stable-code identity, canonical grain, duplicate keys,
unknown player elements, position conflicts, historical optional-column
absence, invalid kickoff timestamps and duplicate stable codes. Tests are
committed but have not yet been run in a verified CI environment. The
normalizer has not yet been executed against the full upstream archive.


## 10. Fixture-level FPL archive completeness audit

CTA now has `scripts/audit_vaastav_fixture_archive.py`, which compares
`merged_gw.csv` against the season's `fixtures.csv` and `teams.csv`.
It checks unique fixture IDs and fixture/player keys, finished fixtures with
no player-match rows, both home/away sides represented, event and kickoff
agreement, and team/opponent/home-away consistency. It emits per-fixture row
counts and zero-minute row counts.

The audit deliberately does **not** assume that every registered player must
appear in every fixture. It does not synthesize missing player rows or
reinterpret absent rows as zero-minute appearances. Row-count distributions
are diagnostic; the strict completeness claim is limited to fixture-level
coverage and internal fixture metadata. Player-population completeness needs
an independently established upstream row-generation contract before it can
be asserted.

The upstream season fixture schedule is `data/2026-27/fixtures.csv`, with
numeric team IDs and fixture IDs; the player archive's `team` field is a
team name, `opponent_team` is the numeric opponent ID, and `was_home`
identifies the player's side. The normalizer's team-name/ID cross-check is
therefore consistent with the inspected source schema.

Inspection of the pinned upstream `collector.py` further establishes that
`collect_gw` walks the per-player `gw.csv` files, selects rows whose
`round` matches the requested gameweek, assigns the team name from the
fixture/home-away lookup, and writes those rows into each `gwN.csv`; the
merge routine concatenates the per-GW rows while filling absent historical
columns with blanks. This explains the archive's row provenance and confirms
that a missing row must not be silently manufactured by CTA. It does not, by
itself, prove that every registered player is guaranteed a row for every
fixture, so the audit keeps player-population completeness separate from
fixture-level completeness.

Unit tests cover a valid two-sided fixture, a finished fixture missing player
rows, duplicate player-fixture keys and inconsistent opponent metadata. These
tests are committed but remain unexecuted in a verified CI run. The audit has
not yet been run against a fully acquired local copy of the entire season
archive.

## API.SH Understat import contract

- API.SH provides JSON player-season/match histories and team-season match histories.
- Player imports use include_shots=false and raw=true; team imports use raw=true.
- Current FPL roster only is required for target forecasts; Dastan's published all-player feature frame supplies historical model training.
- The raw source cache stores player histories by Understat player ID and team histories by season.
- GitHub Actions reads APISH_KEY from a repository secret; the key is never written to source manifests or artifacts.
- The local monthly credit guard defaults to 900 calls, below the provider's documented 1,000 recurring monthly free credits. Paid use is not enabled automatically; increase the guard only after reviewing billing.
- Each acquisition report records provider, player/team request counts, reserved credits, cache status and failures.

