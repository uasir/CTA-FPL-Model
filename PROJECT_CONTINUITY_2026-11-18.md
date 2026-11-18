# CTA-FPL-Model — single-chat continuity brief and master operating prompt

Date: 2026-11-18  
Repository: https://github.com/uasir/CTA-FPL-Model  
Default branch: `main`  
Current verified main commit: `264f2792514d5927cc051d9fad36a6f03a2d3a24`

This document is the durable project handoff for continuing work in one primary ChatGPT conversation. It supersedes earlier status notes where newer evidence below conflicts with them. It is a continuity aid, not a claim that all integration gates have passed.

---

## 1. Master operating prompt

Continue engineering the user's existing CTA-FPL-Model project from its recovered original source lineage. Treat the GitHub repository and its CI artifacts as the current shared execution record; reconcile against Replit before claiming that Replit is synchronized.

Follow these non-negotiable instructions:

1. **Preserve original project files.** The five original archives are the historical source baseline. Do not overwrite, replace, or discard them. Work from the recovered v1.0.2 core plus the separate Engineering Workbench, and reconcile later fixes non-destructively.
2. **No substitute data.** Synthetic fixtures may be used only for unit tests and code-path checks. Never present synthetic data as real pilot, real multi-match, real FPL, or production evidence. If real inputs are unavailable, stop that specific validation gate and report the blocker.
3. **Keep the two recommendation systems independent.**
   - `general_market`: squad-independent market rankings. It must reject personal squad, budget, transfer, chip, formation, rank, and manager context.
   - `personal_squad`: manager-specific squad optimisation using that manager's squad, bank, transfers, constraints and preferences.
   Do not merge their inputs, outputs, state or responsibilities.
4. **Keep provider identity namespaces separate.** StatsBomb IDs, Wyscout `wyId`, Opta/PulseLive `playerId`, and FPL `element`/`player_code` are different identifiers. Join only through an evidence-backed, season-scoped crosswalk. Never fuzzy-match or infer identity from names.
5. **Do not overclaim.** Python–JavaScript parity proves implementation consistency only for the tested contract and inputs; it does not prove predictive accuracy, calibration, causal validity, or FPL usefulness. Label exploratory work accurately.
6. **Preserve provenance.** Pin source commits, hashes, retrieval times, season/competition, schemas, and workflow artifacts. Do not commit private manager picks or raw FPL snapshots to this public repository.
7. **Continue without unnecessary pauses.** The user asked for ordinary roadmap work to continue without stopping for routine briefings or approvals. Make safe, reversible engineering changes, run tests and inspect results. Pause only when an external permission, user-owned secret, irreversible action, or genuinely missing input requires the user.
8. **Use this conversation as the primary chat.** Do not ask the user to repeat known project context. If another chat contains an untransferred attachment or decision, identify that exact missing item rather than inventing it.

## 2. Source recovery and lineage

The original five archives were recovered, SHA-256 checked, extracted non-destructively and passed ZIP integrity checks in the 15–17 November recovery runs. Their recorded hashes are:

| Original archive | SHA-256 |
|---|---|
| `CTA_FPL_reconstruction_scaffold_v0_1.zip` | `b96b6e3c3ef04b4e12d5d153f4f381843f4ecc2e48f0ae54d41d4ec14c1d6dc1` |
| `CTA-FPL-Engineering-Workbench.zip` | `b7e62bec4299a63fb06d72e7bc38f54f2726ea68f366a29b4e3f64607f6e4630` |
| `CTA_FPL_Model_v1_0_2_Engineering_Build.zip` | `7c8960ef250472eb2bb57b3d82f4ebec8dec00096482307470aedecb40cf5a73` |
| `CTA_FPL_Model_v1_0_1_Engineering_Fix.zip` | `2c000b3c3f84bf1197303013d0d21e402b01d8ebfbddef3aa6558cfc50ab7553` |
| `CTA_FPL_Model_v1_0_Experimental.zip` | `2d8278b593165b2bad7d55ee50969d166070e8872288a7fc59d07976ae17d749` |

Lineage: v1.0 Experimental → v1.0.1 sparse-row CSV writer fix → v1.0.2 StatsBomb possession-direction correction. The Engineering Workbench is a separate parity/contracts/xT support package. The reconstruction scaffold is an earlier minimal baseline.

Current-turn materialization and checks:
- `CTA_FPL_Candidate_v1_0_2_plus_Workbench_2026-11-15.zip`: SHA-256 `ad4334228574ccfcc4bdfb6d3d4f7160a680837d58b92147d63b88ecda8b6305`, 70 ZIP entries, integrity passed; original core tests 7 passed and Workbench tests 17 passed.
- `CTA_FPL_INDEPENDENT_WORKSPACE_2026-11-17.zip`: SHA-256 `c482a282466e36d6eaa8f42f724e0103a29390954b2342d64a855714b6abb7c4`, 118 ZIP entries, integrity passed; provisional patched copy tests 11 core passed and 23 Workbench passed plus 3 subtests.
- The 17 November independent workspace is explicitly **provisional and not a Replit export**. It contains a synthetic smoke input (match ID 999999); do not treat that as real multi-match evidence or overwrite Replit with it.
- Earlier recovery logs state that all five original ZIPs were re-materialized and verified on 17 November. The original five ZIPs themselves were not found in the current `/mnt/data/files` directory during the 18 November turn; the materialized candidate archives above were available and verified.

## 3. Repository, Replit and execution record

- GitHub repository: https://github.com/uasir/CTA-FPL-Model
- PR #3, provider-specific identity crosswalks, was merged on 2026-11-18. Merge commit: `4183f389f23c2da88e8067928428f84900d7960f`.
- PR #4, Onside FPL benchmark source audit and this continuity brief, was merged on 2026-11-18. Merge commit/current main: `264f2792514d5927cc051d9fad36a6f03a2d3a24`.
- Latest main CI after both merges: run [44257955121](https://github.com/uasir/CTA-FPL-Model/actions/runs/44257955121), conclusion success; 37 JavaScript tests, 164 Python tests and 3 subtests passed. All three provider crosswalk validators correctly report `EMPTY_NOT_READY`.
- The earlier PR branch CI [44256906777](https://github.com/uasir/CTA-FPL-Model/actions/runs/44256906777) passed with 37 JavaScript tests, 164 Python tests and 3 subtests. The new crosswalk validators ran; both new provider templates correctly remained empty/not ready.
- Replit app: [CTA-FPL-Model](https://replit.com/@uasieg1/CTA-FPL-Model), replId `bb60190a-50a0-46bf-9253-a4c3e09302d9`.
- Replit Agent inspection requests on 18 November returned `phase=paused` with empty responses. The latest Replit source and whether its earlier multi-match update completed are therefore unverified. Do not claim the Replit workspace is synchronized with GitHub main.
- GitHub Actions is the currently verified cloud execution route. It can download pinned public source files and run Python/Node jobs even when the local container cannot reach the network.

## 4. Verified engineering milestones

### Python–JavaScript core parity

The 34-match multi-match Actions run [44091783751](https://github.com/uasir/CTA-FPL-Model/actions/runs/44091783751) completed successfully:
- 34/34 matches passed.
- 141,468/141,468 registered feature comparisons were within tolerance:
  - 113,373 sequence comparisons.
  - 21,567 player comparisons.
  - 6,528 xT-grid comparisons.
- The current core is the ID-based 1.0.3-experimental implementation with parity contract 1.1.0.
- Player rows are keyed by StatsBomb numeric player ID, with display names retained as metadata.
- This is real multi-match implementation parity, not predictive validation and not FPL integration.

### 360 data anomaly

The same run found match `3837706` has a 360 file with 3,548 unique frame UUIDs, zero overlap with 4,026 target-match event UUIDs, and zero overlap with the other matches in the 34-match sample. Its 360 file remains quarantined. Do not normalize UUIDs, relabel the match, or count those frames as valid coverage. The 34-match engineering parity result remains distinct from the 360 data-quality exception.

### Official FPL ingestion

The official FPL workflow has fetched the 2026/27 roster and fixtures:
- 672 players and 380 fixtures.
- Latest full snapshot recorded 6,562 player-fixture rows.
- All 672 player summaries succeeded in the latest reported full run.
- No orphan fixture/player references or minute/points reconciliation mismatches were reported.
- Official `ep_next` and `ep_this` are preserved as the official FPL baseline, not relabelled as CTA forecasts.

### Point-in-time features and baselines

- Lagged FPL feature and player-gameweek builders exist and have run.
- They are structurally lagged, but the historical source-vintage status remains `NOT_VERIFIED`; current API snapshots may include retrospective revisions.
- Rolling-history baselines and an exploratory ridge baseline have been evaluated. Results are not a validated production model.
- A private durable archive of deadline-time snapshots is still required; 90-day Actions artifacts are not a full-season archive.

### Recommendation systems

- Python and JavaScript implementations exist for both `general_market` and `personal_squad`.
- `general_market` has been run against the full 672-player official FPL pool. Its Python and JavaScript outputs were exactly numerically equal across the player pool and output categories. The latest forecast snapshot was stale relative to the target deadline and correctly labelled exploratory.
- `personal_squad` passed a 672-player scale smoke test using a **synthetic** legal 15-player squad; it evaluated 2,914 legal one-transfer candidates and built a legal 4-3-3. This was not the user's actual squad or a real manager recommendation.
- CoVar and player-variance risk application remain disabled in `personal_squad` pending validation. Do not claim CoVar optimisation is complete.
- The user's manager-specific squad has not been supplied to this engineering run.

### Effective ownership

- A lock-safe top-10k weighted manager-pick EO collector is implemented and its mocked timing/API tests pass.
- It samples ranks before the deadline and only fetches picks after official deadline lock verification.
- No live near-deadline capture has yet been verified. Global ownership from FPL history is not EO. Do not use `selected_by_percent` as EO.

## 5. Player identity and provider policy

PR #3 added:
- `wyscout_fpl_identity_crosswalk.csv` for Wyscout 2017/18 → FPL 2017/18.
- `opta_pulselive_fpl_identity_crosswalk.csv` for Opta/PulseLive 2026/27 → FPL 2026/27.
- A strict provider-specific validator, tests and CI integration.
- Existing StatsBomb identity crosswalk remains a separate namespace and is not repurposed.

A row can be promoted only with provider numeric ID, FPL element ID, same-season competition/team evidence, retrievable evidence URL, reviewer/date, approved verification method, and one-to-one mapping. Name matching can generate candidates only.

**Current state:** all three provider crosswalks remain empty/not ready. No StatsBomb-to-FPL, Wyscout-to-FPL, or Opta/PulseLive-to-FPL verified identity joins have been established.

Provider source assessment:
- **StatsBomb Open Data:** current EPL seasons do not overlap the usual FPL historical archive. The 34-match StatsBomb set is an engineering benchmark only.
- **Wyscout 2017/18:** official event collection is published under CC BY 4.0 and overlaps the 2017/18 FPL season. However, historical FPL target-data reuse rights and point-in-time vintages remain unresolved; official player/appearance reconciliation is incomplete. Candidate only.
- **Opta/PulseLive 2026/27:** preliminary structural audit found 511 shared player IDs and matching team IDs, but the third-party repository has no recognized licence and no player-match output files in the inspected tree. Do not ingest or redistribute without rights clearance.
- Keep each provider's feature family and ID namespace separate.

## 6. New Onside FPL benchmark audit

A separate source-audit workflow and script have been added on PR #4:
- PR #4: https://github.com/uasir/CTA-FPL-Model/pull/4 (merged; main commit `264f2792514d5927cc051d9fad36a6f03a2d3a24`)
- Workflow: `.github/workflows/cta-onside-benchmark.yml`
- Script: `canonical_candidate/engineering_workbench/scripts/inspect_onside_fpl_benchmark.py`
- Source: https://onsidearena.com/data/graded-predictions.csv
- Provider-stated licence: CC BY 4.0, attribution to Onside Arena.
- DOI: https://doi.org/10.5281/zenodo.22746985

Latest real-source audit: [GitHub Actions run 44257909685](https://github.com/uasir/CTA-FPL-Model/actions/runs/44257909685), conclusion success. Artifact: [cta-onside-benchmark-44257909685](https://github.com/uasir/CTA-FPL-Model/actions/runs/44257909685/artifacts/14407050697), ID `14407050697`, retained until 2027-02-16. Earlier successful audit: [run 44257817207](https://github.com/uasir/CTA-FPL-Model/actions/runs/44257817207). Source snapshot SHA-256:
`dd51366a5f71d5f0bf26b4265b17188f04774d584c4444172be3f307aaf02a81`

Verified:
- 5,450 player-gameweek rows and 14 columns.
- Every row's `captured_at` precedes `deadline_utc` (5,450/5,450).
- Every row's deadline exactly matches the official FPL event deadline (5,450/5,450).
- 608 unique `player_id` values all match official FPL `element` IDs (608/608); none match `player_code`.
- Zero duplicate player-gameweek keys.
- 4,954 populated actual-points rows reconcile exactly to official FPL event-live totals; zero mismatches.
- The remaining 496 rows have blank actual points and belong to gameweeks the official FPL API still marks unfinished; no finished gameweek has an ungraded row.
- Raw CSV and JSON audit are stored in the Actions artifact, not committed to the public Git history.

Exploratory comparison on the same 4,954 scored rows:
- All scored rows: Onside MAE 1.681 / RMSE 2.577; FPL `ep_next` MAE 1.600 / RMSE 2.651.
- Provider `minutes_qualified` subset (2,045 rows): Onside MAE 2.515 / RMSE 3.530; FPL `ep_next` MAE 2.685 / RMSE 3.765.
- These are our independent calculations from the current ledger, not the provider's four-season claim. The all-row and minutes-qualified cohorts answer different questions. The `minutes_qualified` cohort is the like-for-like played-minutes cohort described by the provider.
- This is an external FPL forecast benchmark only. It does not contain CTA event-derived features and is not CTA predictive validation. Keep Onside forecasts separate; do not train on them or blend them into CTA predictions.

## 7. Current blockers

1. **CTA event features aligned to FPL outcomes:** no cleared event-and-target source pair with documented overlapping season, rights, and point-in-time provenance. Wyscout 2017/18 is promising but target-data rights/vintage remain unresolved. Opta/PulseLive rights are unresolved.
2. **Historical FPL point-in-time snapshots:** the current lagged dataset is structurally safe but not vintage-verified. A private durable archive is required; do not place manager-specific data or private snapshots in the public repo.
3. **Verified player crosswalks:** StatsBomb, Wyscout and Opta/PulseLive crosswalks remain empty. No name-only or fuzzy joins.
4. **EO live validation:** collector logic is tested, but no live post-deadline capture has been accepted.
5. **360 anomaly:** match `3837706` remains quarantined pending source provenance.
6. **Personal-squad risk/CoVar:** CoVar estimation and risk application are not validated; keep disabled in the personal-squad engine.
7. **Replit reconciliation:** Agent returned empty responses; latest Replit workspace and whether it contains the GitHub changes are unknown.

## 8. Immediate next actions

1. Complete PR #4 review/CI and merge the Onside source-audit workflow if checks remain green.
2. Add a durable benchmark report and reproducible comparator from the audited artifact. Recompute MAE/RMSE and rank metrics on identical cohorts; keep all-player and minutes-qualified results separate.
3. Reconcile the official FPL deadline-time snapshot with Onside's frozen `fpl_ep_next` values where independent source vintages are available. Do not assume a current bootstrap can reproduce past forecasts.
4. Pursue an authorized FPL historical target source or written permission for the 2017/18 archive. Keep Wyscout event data as a separate provider until the target rights and point-in-time gates clear.
5. Preserve the 34-match StatsBomb engineering benchmark and investigate the quarantined 360 source anomaly without modifying the source records.
6. Validate live EO capture after an actual deadline; archive aggregated outputs and provenance privately.
7. Only after data rights, identity, point-in-time, and predictive validation gates pass, add CTA-derived player-gameweek features and integrate them into the FPL forecast layer.
8. Validate covariance/CoVar on time-safe player-gameweek data before enabling risk-aware personal-squad optimisation.

## 9. Durable evidence links

- 34-match parity: https://github.com/uasir/CTA-FPL-Model/actions/runs/44091783751
- FPL official ingestion + general-market integration history: https://github.com/uasir/CTA-FPL-Model/actions/runs/44255361502
- Provider-specific identity crosswalk PR (merged): https://github.com/uasir/CTA-FPL-Model/pull/3
- Onside benchmark audit PR #4 (merged): https://github.com/uasir/CTA-FPL-Model/pull/4
- Main CI after merges: https://github.com/uasir/CTA-FPL-Model/actions/runs/44257955121
- Onside benchmark source audit run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44257817207
- Onside dataset and CC BY 4.0 terms: https://onsidearena.com/data
- Onside public accuracy ledger: https://onsidearena.com/accuracy
