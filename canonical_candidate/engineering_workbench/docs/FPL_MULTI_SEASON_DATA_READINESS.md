# FPL Multi-Season Data Readiness

## Purpose

Prepare the FPL-points predictor for multi-season chronological evaluation. This is a data-eligibility gate, not a model promotion decision. The four-layer CTA architecture remains unchanged, and CTA-derived features retain zero recommendation weight until incremental out-of-sample value is demonstrated.

## Source audit

### Official FPL public API

- The ingestion pipeline captures the current bootstrap, fixtures, and each player's element-summary history.
- Source and normalized-output hashes are recorded in `source_metadata.json`, together with capture time and a deterministic source snapshot ID.
- A current capture can support a genuinely upcoming deadline when fetched before that deadline.
- The ingestion workflow currently retains its uploaded FPL snapshot artifact for 90 days. Hashes prove the identity of captured files but do not make the raw snapshots a durable multi-season archive; a long-term archive/manifest retention path is still required.
- It cannot recreate historical pre-deadline vintages. Earlier player history may have been retrospectively revised, so historical training rows remain `NOT_VERIFIED` for strict point-in-time backtesting.
- The official API feed is therefore suitable for current-season forward snapshots and as a source of final historical targets, but not as proof that a feature value was available at an old deadline.

### vaastav/Fantasy-Premier-League

- Public repository inspected: https://github.com/vaastav/Fantasy-Premier-League
- It contains season folders and gameweek-level CSV files, including 2017/18 through 2024/25.
- Its README states that weekly updates stopped after 2024/25 and describes only three subsequent major updates per season.
- The README explicitly warns that the `xP` field may contain post-match information and should be shifted or excluded.
- GitHub reports the repository licence as `Other` / SPDX `NOASSERTION`; no clear reuse licence was identified.
- **Decision: use it for user-directed, research-only multi-season FPL prediction experiments despite unresolved rights metadata.** This is not a claim that the repository grants a permissive licence. Keep raw files and player-level outputs runner-local; do not redistribute the source dataset or derived player-level extracts. Preserve attribution, the pinned source commit, per-file hashes, and the `NOASSERTION` status in every report. Its historical gameweek files are not independently proven to be exact deadline-time snapshots.

### Multi-season research implementation

- Pinned source revision: `d7b05b51d137bfefef4b692386d18c610975b9b9`.
- Research seasons: 2016/17 through 2025/26; the incomplete 2026/27 season is excluded from the initial multi-season holdout.
- Builder: `scripts/build_vaastav_fpl_multiseason_panel.py`.
- Manual workflow: `.github/workflows/cta-fpl-multiseason-research.yml`.
- The builder downloads each season's `gws/merged_gw.csv` into runner-local storage, hashes each source file, builds player-season-GW lagged features, and runs a chronological 80/20 gameweek holdout.
- FPL element IDs are treated as season-scoped. The FPL-only experiment does not pretend they are persistent cross-season identities.
- `xP`, ownership/selected counts, transfers, and post-match `modified` values are explicitly excluded from model features.
- No raw source files or player-level panel artifacts are uploaded by the research workflow.
- The resulting scores remain exploratory: source vintages are retrospective, not verified deadline-time snapshots.

### Existing CTA-linked historical panel

- The existing Wyscout/11footy/FPL research panel covers 2017/18 only.
- It contains 91 verified cross-provider player identities and 2,693 verified player-fixture rows across 380 mapped EPL fixtures.
- This is useful for a single-season paired CTA experiment, but not enough for a multi-season CTA claim.
- 11footy source data is CC BY-NC 4.0 and remains subject to the existing non-commercial and runner-local handling restrictions.

## Feature-integrity decisions

- Missing provider metrics remain missing. Training uses training-window medians plus explicit missingness indicators; observed zero is not conflated with missing.
- Missing/non-finite targets fail closed rather than becoming zero.
- Imputation values and scaling statistics are fitted on training rows only.
- Target-gameweek fixture count is not used as a predictor or to scale historical features.
- Fixture difficulty is excluded from the exploratory FPL model because no archived pre-deadline fixture snapshot proves its historical value.
- Historical ownership percentages based on current bootstrap denominators are not used as model features.
- FPL `xP` is excluded from historical features because the inspected dataset warns of possible post-match leakage.
- Historical FPL player statistics are structurally lagged by kickoff/deadline, but source-vintage revisions remain an explicit limitation.

## Eligibility gate

Multi-season model evaluation remains blocked until a source is identified with:
1. clear reuse rights compatible with the intended project;
2. stable season, player, fixture, and gameweek identifiers;
3. complete gameweek-level FPL targets and usable prior-gameweek features;
4. capture timestamps or archived snapshots sufficient to establish deadline-time availability;
5. durable source commit/version and file hashes; and
6. a reproducible cross-season player identity mapping.

Until then, keep the current 2017/18 and current-season experiments research-only. Do not promote the ridge baseline, the 2PM-Transformer candidate, or CTA features into recommendation decisions on the basis of these limited experiments.
