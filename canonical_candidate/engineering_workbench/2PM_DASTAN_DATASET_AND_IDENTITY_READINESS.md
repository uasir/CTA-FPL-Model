# 2PM — Dastan Dataset Coverage and Player-Identity Readiness

**Date:** 2026-11-23  
**Status:** Evidence review; no data rows promoted  
**Pinned upstream:** `qazybekb/smartplayfpl-dastan@758db9247e8b3a9a870c991064f74d8339d61cd0`

## 1. Published feature-frame coverage

The pinned Dastan release manifest records:

- `features.parquet`: 163,072 rows, 304 total columns, 38,697,486 bytes.
- SHA-256: `dcf8411d458e7b99b15472975280cf855e15de22070022fad6fce0f76f3f299c`.
- Release seasons: 2020/21 through 2025/26 (six completed EPL seasons).
- The 286 model input columns are separate from target/identity/metadata columns.
- Pre-deadline `ep_next` artifact: 142,173 rows.
- Pre-deadline signals artifact: 137,982 rows.

The immutable release registry ends at 2025/26. It does **not** contain 2026/27 feature rows. The pinned mapping repository does contain a 2026/27 roster projection, but that is not a current-season player-fixture feature frame and is not evidence that 2026/27 inputs have been built.

**2PM implication:** the six-season frame may support historical training research after its feature and identity corrections. It cannot by itself provide current 2026/27 inference rows. A separate current-season data build, pinned to current FPL/Understat source revisions and a current player/team mapping release, is required before live 2PM forecasts can be prepared.

## 2. Current-roster mapping is a separate population

The pinned upstream mapping documents disagree: `docs/DATA.md` reports 627/654, while `data/mappings/README.md` still says 518/577. Direct counting of the pinned `data/mappings/fpl_understat_current.csv` (SHA-256/blob evidence recorded in `2PM_DASTAN_FEATURE_POINT_IN_TIME_AUDIT.md`) gives 654 rows: 626 `mapped`, 1 `shared_understat_id`, and 27 `unmapped`. Effective mapped coverage is therefore 627/654 when the documented shared-ID case is counted as mapped. The README's 518/577 statement is stale for this exact pinned roster snapshot.

This is a captured 2026/27 roster mapping, not a live count on 2026-11-23 and not a 2026/27 player-fixture feature frame. Always recalculate and hash the exact roster/mapping files for a new build. Also calculate:
- total active roster players;
- mapped players;
- unmapped players;
- shared Understat IDs;
- missing Understat player histories;
- mapped player-fixture rows;
- missing player/team feature coverage.

Unmapped players must not be assigned by fuzzy name matching. FPL-only feature rows may remain usable if the relevant 286-column semantics support the missingness; Understat-dependent fields must preserve explicit missingness.

## 3. Historical identity correction is mandatory for 2PM

The pinned upstream mapping documentation separates:
1. immutable training assignments used to reproduce the released Dastan frame;
2. corrected historical identities;
3. current operational mappings for new data.

The released training map deliberately retains two incorrect historical identities so the published Dastan model remains reproducible:

| FPL code | Release identity | Corrected identity | Release Understat ID | Corrected Understat ID |
|---:|---|---|---:|---:|
| 437688 | Lewis Richardson (Burnley) | Lewis Richards | 9082 | 9216 |
| 515501 | Álvaro Fernández (goalkeeper) | Álvaro Fernández Carreras (defender) | 5191 | 10576 |

The source code's `assignments_for_seasons()` uses the immutable frozen training-assignment table for released seasons. Therefore, calling the upstream canonical rebuild without modification reproduces those two identity errors. It is suitable for reproducing Dastan, not automatically suitable for a new independent 2PM training set.

The corrected mapping reports 1,563 unique Understat IDs across the 1,564 FPL-code population; the remaining shared ID is documented as two FPL spellings of Kaine Kesler-Hayden. Shared IDs must be handled explicitly rather than rejected or merged blindly.

### Required 2PM mapping policy

- Use stable `fpl_code` as the FPL-side player key.
- Build a new versioned historical assignment table by applying the evidence-backed corrected Understat IDs to the relevant historical FPL-code/season intervals.
- Preserve first/last Gameweek assignment intervals and mapping provenance.
- Retain the identity audit and evidence URLs in the data manifest.
- Record the exact source snapshot and mapping hashes.
- Explicitly handle legitimate shared IDs and alias transitions.
- Never use the immutable release's incorrect identities merely to reproduce its feature values.
- Do not apply current operational IDs retrospectively without evidence that the mapping was valid for the historical period.

The corrected historical map changes the player histories used to construct Understat rolling features. Consequently, 2PM should rebuild its candidate player/team feature frame from canonical source data under the corrected mapping, not merely patch two rows in the already-computed 286-feature frame. A corrected identity can change the rolling history of every later row for that player.

## 4. Defensive feature chronology

The upstream feature documentation says defensive contribution, CBIT, recoveries and tackles are available from 2025/26 onward. The six-season historical frame therefore has a major structural season boundary for these features.

Before admission, calculate feature-level coverage by season and distinguish:
- source statistic genuinely observed as zero;
- statistic unavailable/not collected in that season;
- row missing due to player/provider mapping;
- residual NaN;
- imputed value.

Do not let pre-2025/26 absence become a synthetic zero history without explicit missingness indicators and a points-model-specific rationale. The rolling windows that include these features must also be rebuilt under the correct season-aware missingness policy.

## 5. Source freshness and current-season build

The pinned source-pins file records Vaastav and fplcache commits reviewed on 2026-08-08. The release registry ends at 2025/26. For a 2026/27 current-season feature build:

1. Obtain current FPL historical match/fixture/event-calendar source revisions through the target GW.
2. Obtain current Understat player/team match revisions and versioned player/team mappings.
3. Pin every source commit and retain raw download hashes.
4. Rebuild player-fixture rows and all 286 candidate features in an isolated candidate directory.
5. Capture archived pre-deadline `ep_next` and availability snapshots with the existing strict `is_next`, matching-deadline and pre-deadline timestamp requirements.
6. Do not treat a current bootstrap roster snapshot as a historical deadline snapshot.
7. Run the independent official-deadline reconstruction required by `2PM_DASTAN_SOURCE_SEMANTICS_AUDIT.md`.
8. Publish season/GW coverage and mapping completeness before any 2PM inference use.

No source update, external acquisition or production data promotion is performed by this record.

## 6. Readiness status

| Requirement | Status |
|---|---|
| Six-season 2020/21–2025/26 Dastan release manifest | Verified from pinned source manifest |
| Exact 286 ordered columns | Verified separately against pinned schema |
| 2026/27 rows in pinned feature release | Not present |
| 2026/27 current roster mapping | Snapshot exists but is stale for current date; refresh and hash required |
| Corrected historical identity map | Exists upstream; not yet applied to a 2PM rebuild |
| Corrected feature-history rebuild | Not performed |
| Defensive-stat season coverage table | Not produced |
| Full official-deadline feature reconstruction | Not performed |
| Historical market-field timestamp validation | Not performed |
| Current-season 2PM feature rows | Not available/verified |
| Training schema freeze | Not approved |

**Gate:** `DASTAN_286_ADAPTATION_AUDIT_IN_PROGRESS`.

The next data task is not model training. It is a clean, corrected-identity rebuild of the historical feature candidate plus a separately pinned 2026/27 feature build, followed by the full official-deadline reconstruction and feature admission tests.
