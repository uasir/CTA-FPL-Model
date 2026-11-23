# 2PM Transformer — Shared Data Foundation Audit

**Date:** 2026-11-23  
**Branch:** `feat/four-layer-2pm-transformer-evaluation`  
**Status:** Initial source/code audit; data gate not cleared  
**Governing implementation decision:** `2PM_PAPER_FIRST_CLEAN_IMPLEMENTATION_CHARTER.md`

## 1. Executive finding

The repository has reusable FPL identity, fixture, player-fixture history, source-provenance, and point-in-time feature-building infrastructure. It does **not** currently demonstrate a complete, authorized, point-in-time-safe player-match dataset that satisfies the paper's 116-feature input contract.

The most important blockers are:

1. The paper's complete 116-feature dictionary has not been located in the accessible paper or public supplementary material.
2. The official FPL API history contains useful player-fixture scoring and selected performance fields, but not all detailed match-action fields described in the paper.
3. The current Opta/PulseLive integration has player-season identity mapping and team-match context, but the inspected source does not contain player-level per-match event rows.
4. Wyscout 2017/18 offers a promising event-level source, but the corresponding historical FPL target-data rights and point-in-time provenance are unresolved.
5. The existing FPL lagged-history builder is structurally lagged but explicitly marks historical point-in-time status as `NOT_VERIFIED`, because current API snapshots may contain retrospective revisions.

**Decision:** do not begin 2PM model training or build the new sequence dataset from these sources yet. Continue with source/schema resolution and a formal feature-coverage audit. No legacy 2PM code or preprocessing is authorized for reuse.

## 2. Governing paper requirements

The governing publication is:

Wiechno, W., Duch, P. and Bartosik, B. (2026), *Modeling Fantasy Premier League Player Performance with a Two-Component Poisson Mixture Transformer*, ICAART 2026, pp. 3093–3100. DOI: 10.5220/0014358000004052.

Paper: https://www.scitepress.org/Papers/2026/143580/143580.pdf

The paper describes:

- Five consecutive previous matches actually played by a player, with no more than 21 days between selected matches.
- 116 features per match, representing player form and FPL-relevant match actions.
- An encoder-only Transformer with input embedding, positional encoding, self-attention and feed-forward processing.
- A two-component Poisson-mixture output with mixture probability (p) and positive rates λ1 and λ2.
- Mixture negative log-likelihood and training-only MLE initialization of Poisson rates.
- Chronological train, validation and test separation.
- A paper-specific transformation of negative FPL point totals to non-appearance/zero for the Poisson training target.

The paper describes feature categories such as minutes, position, goals, assists, penalties, cards, own goals, saves, tackles, blocks, clearances, interceptions, pass types, shot/goal-creating actions and save percentage. It does not provide a complete machine-readable list of all 116 fields in the accessible text.

The paper's data covers six leagues and seasons 2017/18–2024/25. Its EPL player points come from official FPL statistics; other leagues' points are reconstructed under FPL scoring rules. The paper reports 6,170 players, 9,057 matches and 305,616 samples.

The paper's notation for the five-match window is not perfectly consistent (`H=5` alongside an inclusive (t:t+H) expression). The prose and repeated description specify five previous matches; the implementation should follow five unless author clarification establishes otherwise.

## 3. Repository data assets audited

### 3.1 Official FPL ingestion

Inspected:
- `canonical_candidate/engineering_workbench/scripts/fetch_fpl_official_api.py`
- `canonical_candidate/engineering_workbench/reports/CTA_PROJECT_STATUS_2026-11-17.md`

The ingestion adapter fetches official bootstrap data, fixtures and each rostered player's `element-summary` history. It emits season-scoped player records, fixture records and player-fixture history rows, retaining source timestamps and hashes.

The player-fixture fields include, among others:

- Minutes and total FPL points.
- Goals, assists and clean sheets.
- Goals conceded, own goals, penalties saved/missed.
- Yellow/red cards, goalkeeper saves.
- Bonus and BPS.
- Influence, creativity, threat and ICT.
- Starts and expected-goals/assists/involvement/conceded fields.
- Selected count, transfers and player value.

This is useful for actual FPL scoring outcomes, target aggregation and some historical form features. It does not provide all detailed player actions required by the paper's described feature families (for example complete passing types, shot/goal-creating actions, tackles, blocks, clearances and interceptions as a full match-level feature set).

The latest documented current-season ingestion had 672 player records, 380 fixtures and 6,562 player-fixture rows. Those are current-season structural counts, not evidence of multi-season training coverage.

### 3.2 Existing lagged FPL feature builder

Inspected:
- `canonical_candidate/engineering_workbench/scripts/build_fpl_lagged_features.py`
- `canonical_candidate/engineering_workbench/scripts/aggregate_fpl_gameweek_rows.py`

The builder uses earlier Gameweeks, checks actual prior kickoffs against the target deadline, and gives all fixtures in the same target Gameweek a common pre-deadline feature snapshot. The aggregator produces one player-Gameweek target by summing points and minutes across fixtures.

Important limitations for 2PM:

- Its history features are Gameweek aggregates/rolling summaries, not a five-observation sequence of actual player matches.
- It does not implement the paper's five-played-match sequence and maximum 21-day inter-observation gap rule.
- Its report labels the result `PASS_STRUCTURAL_ONLY` and `point_in_time_status: NOT_VERIFIED`. Current API snapshots can contain retrospective revisions to earlier statistics.
- Its current feature schema is far smaller and semantically different from the paper's 116 per-match features.

This builder is evidence of reusable deadline/fixture and target-grain logic, not a sequence builder or a compliant 2PM dataset. It must not be reused as the new 2PM sequence builder.

### 3.3 Opta/PulseLive current-season integration

Inspected:
- `canonical_candidate/engineering_workbench/reports/OPTA_PULSELIVE_LIVE_INTEGRATION_2026-11-18.md`
- `canonical_candidate/engineering_workbench/reports/INTEGRATION_PROGRESS_2026-11-18.md`

Verified structural findings in the inspected integration report:

- 511 provider player IDs mapped exactly to FPL player codes, with team validation.
- 100/100 provider match IDs matched FPL fixture codes.
- The source contained player-season data and team-match rows.
- Ten team metrics were available, including expected goals/assists, accurate passes, possession, final-third entries, box attempts, recoveries, interceptions, duels won and touches.
- The report explicitly states that the inspected source did not contain player-level per-match event rows.
- The provider file was a current cumulative snapshot, so historical point-in-time status was `NOT_VERIFIED`.
- Underlying Premier League/PulseLive data rights were unresolved.

**2PM conclusion:** the existing Opta integration is not currently a source for the required 116 player-match vectors. Its team-context rows must not be relabelled as player-match observations or substituted for player event features.

### 3.4 Wyscout 2017/18

Inspected:
- `canonical_candidate/engineering_workbench/reports/WYSCOUNT_FPL_SOURCE_AUDIT_2026-11-17.md`
- `canonical_candidate/engineering_workbench/reports/CTA_PROJECT_STATUS_2026-11-17.md`

The official Pappalardo–Massucco collection describes a 2017/18 English Premier League season with 380 matches, 643,150 events and 603 players. Its event schema includes Wyscout player, team and match IDs, event types/subtypes, tags, match periods, times and coordinates. Match records include dates, teams, lineups, benches and substitutions. The official Figshare items display CC BY 4.0.

This is the strongest identified historical candidate for detailed player-match actions and overlaps the 2017/18 FPL archive season.

However:

- The full event archive was not materialized or ingested in the previous source audit.
- A candidate name screen is not a verified identity crosswalk; match-level appearances, team, season and numeric IDs must support every join.
- The historical FPL archive's underlying data rights are not granted by the repository's MIT software licence.
- The FPL archive is retrospective; archived pre-deadline vintages have not been established.
- No Wyscout data or candidate name match has been promoted into the verified project crosswalk.

**2PM conclusion:** Wyscout is a candidate, not an approved training source. It cannot be joined to historical FPL targets until the target source and identity/provenance gates are cleared.

### 3.5 StatsBomb Open Data

The repository audit found EPL seasons 2003/04 and 2015/16 in the currently inspected StatsBomb Open Data index. The commonly used Vaastav FPL archive begins in 2016/17, so the inspected EPL seasons do not overlap its FPL targets.

The existing 34-match StatsBomb benchmark is an engineering/parity benchmark, not an FPL training dataset. The StatsBomb/FPL player crosswalk remains empty.

**2PM conclusion:** do not use this benchmark to create FPL training labels or imply season-aligned coverage.

### 3.6 Dastan historical training frame

The shared CTA architecture documentation describes a published Dastan training frame of approximately 163,072 player-fixture rows and 286 ordered features, with associated historical snapshots and model artifacts.

The upstream Dastan release was inspected directly at pinned commit `758db9247e8b3a9a870c991064f74d8339d61cd0`, including `dastan/data.py`, `data/release_manifest.json`, `data/season_registry.json`, `docs/FEATURES.md` and `docs/DATA.md`.

The source documentation establishes:
- `features.parquet` contains 163,072 rows and 304 columns, with 286 ordered model feature columns.
- Each row is one player per fixture, across six EPL seasons: 2020/21 through 2025/26.
- The feature composition includes 115 player rolling features, 60 team rolling features, 60 opponent rolling features, and availability/snapshot-derived families.
- The rolling player/team/opponent features are engineered history windows (OpenFPL-derived), not 116 raw per-match feature vectors.
- The dataset's target columns include player-fixture points/minutes-related labels. Its history is deadline-anchored, with a specific safeguard that broadcasts the earliest fixture's pre-deadline history across all fixtures in the same Gameweek to prevent double-GW leakage.
- The release is EPL-only and does not reproduce the paper's 2017/18–2024/25 six-league source coverage.

This resolves the row-grain question: Dastan rows are player-fixture rows, but the 286 predictors are deadline-anchored engineered rolling features. They are **not** equivalent to the paper's five consecutive player-match observations, each represented by 116 per-match features. The Dastan frame therefore cannot be passed directly into 2PM or treated as its input sequence.

It may still be useful as an independently audited source of some historical player-fixture labels or derived feature provenance, subject to the exact data rights, field-level definitions, and transformation audit. The release documentation says its FPL/Understat source data remain subject to their respective terms; the upstream code licence does not grant rights to those source datasets.

No Dastan model code, weights, points heads, preprocessing or feature order is automatically part of the new 2PM implementation. The clean-slate charter permits only independently audited shared data assets and generic infrastructure.

## 4. Feature dictionary and supplementary-material search

The accessible paper specifies the total of 116 features and names broad feature categories, but does not enumerate a complete 116-column schema in a machine-readable form.

A search of the publication record, paper pages, conference listing and author/publication records did not locate an author-hosted 2PM source repository or supplementary feature dictionary. This is a search finding, not proof that no private or unindexed supplement exists.

Required next action:
1. Seek author clarification or a supplementary feature list/source, if obtainable.
2. If the exact list cannot be recovered, construct a source-backed 116-feature mapping only as an explicitly labelled reconstruction/adaptation—not an exact reproduction.
3. Do not invent feature names to reach 116, and do not silently substitute another provider's schema.

For each eventual feature, record canonical name, definition, source/provider, units, observation grain, timestamp availability, missingness semantics, transformation, and observed-versus-derived status.

## 5. Data grain and sequence requirements

The paper combines match-level historical observations with a next-Gameweek FPL points target. Our data model must preserve this distinction.

- **History input grain:** one actual player-match observation, not one calendar Gameweek and not an arbitrary rolling summary.
- **Input sequence:** exactly five eligible previous played matches, ordered by actual kickoff, with no more than 21 days between selected observations.
- **Target grain:** one player-Gameweek FPL points total. For a double Gameweek, aggregate the official points across all target fixtures.
- **Blank Gameweek:** not a played historical match; do not fabricate a match observation.
- **No appearance:** a target outcome, not a historical match row.
- **Long gap:** do not bridge it silently; the sequence eligibility policy must require five newly qualifying observations after the gap.
- **Point-in-time:** every feature must have been available before the target Gameweek deadline. A retrospective current API response is not proof of historical availability.

The five-match sequence builder must be newly implemented for 2PM after the source and feature gates are satisfied. It must not import or wrap the frozen legacy sequence builder.

## 6. Target transformation and evaluation record

The paper maps negative FPL point totals to non-appearance/zero for Poisson training because the Poisson distribution has non-negative integer support.

For our reproduction:
- Preserve original actual points and a transformation flag.
- Build the paper-faithful transformed training target separately.
- Report the number and rate of transformed negative outcomes.
- Preserve original actual points for sensitivity evaluation and clearly state that the Poisson mixture cannot assign probability to negative totals.
- Do not silently drop negative outcomes or describe the model as predicting negative points.

## 7. Rights and provenance status

- The paper publication page identifies CC BY-NC-ND 4.0. Preserve attribution and do not redistribute/adapt the paper itself as if it were project-owned source material.
- The official Wyscout Figshare items display CC BY 4.0, subject to their attribution conditions.
- The Vaastav historical repository's MIT notice applies to repository code, not the underlying FPL/Understat data. Historical FPL target-data rights remain unresolved.
- Opta/PulseLive underlying data rights remain unresolved.
- Official FPL API availability does not by itself establish a historical archive licence or immutable historical vintages.

The source/rights register remains authoritative; this audit does not clear any data-use blocker.

## 8. Readiness decision

| Requirement | Current evidence | Status |
|---|---|---|
| Paper architecture understood | Full published paper inspected | Ready for implementation specification |
| Exact 116-feature dictionary | Categories described; complete list not found | **Blocked / unresolved** |
| Player-match event observations | Wyscout candidate; current Opta source lacks player-match rows | **Not ready** |
| Five-match / 21-day sequence data | Existing builder is GW-based, not paper sequence | **Not built** |
| FPL target labels | Official current-season history works; historical target rights/vintages unresolved | **Not ready for historical reproduction** |
| Point-in-time integrity | Existing lagged history explicitly `NOT_VERIFIED` | **Not cleared** |
| Cross-source player identity | Opta current IDs verified; Wyscout historical joins unverified; StatsBomb crosswalk empty | **Partial / source-specific** |
| Model implementation | Clean-slate code not started | **Not started** |
| Training and evaluation | Not run for clean implementation | **Not started** |

**Overall:** `DATA_GATE_NOT_CLEARED`. Do not implement training or claim paper reproduction yet.

## 9. Recommended next work

1. Resolve the exact 116-feature dictionary with the authors or document a properly sourced reconstruction.
2. Complete a dedicated audit of the Dastan shared training frame's row grain, feature definitions, timestamps and source lineage; do not reuse its model or preprocessing.
3. Determine whether a lawful, historically aligned FPL target source can be obtained for Wyscout 2017/18. If not, plan a prospective point-in-time dataset from the current season onward, without claiming the paper's historical multi-season reproduction.
4. Evaluate the Wyscout event archive only after target rights and identity strategy are addressed; reconcile its match and player appearances against official source files.
5. Only after these gates, define the versioned 116-feature mapping and build the independent five-match sequence dataset.

No model code, training code, sequence builder, tests, artifacts, production settings or M3/M4 interfaces were changed by this audit.
