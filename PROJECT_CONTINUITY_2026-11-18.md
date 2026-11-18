# CTA-FPL-Model — single-chat continuity brief and master operating prompt

Date: 2026-11-18  
Repository: https://github.com/uasir/CTA-FPL-Model  
Default branch: `main`  
PRs #3–#7 and the 18 November documentation updates are merged to `main`. This brief records the current verified state as of 2026-11-18.

This document is the durable project handoff for continuing work in one primary ChatGPT conversation. It supersedes earlier status notes where newer evidence below conflicts with them. It is a continuity aid, not a claim that all integration gates have passed.

---

## 1. Master operating prompt

Continue engineering the user's existing CTA-FPL-Model project from its recovered original source lineage. Treat the GitHub repository and its CI artifacts as the current shared execution record.

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
- **All five original ZIPs were re-materialized into `/mnt/data/cta_fpl_original_archives/` and extracted non-destructively into `/mnt/data/cta_fpl_original_archives/extracted/`.** Every SHA-256 matched the recorded value above and all five ZIP integrity checks passed.
- Original source tests rerun in this Python session: scaffold 3 passed; Engineering Workbench 17 passed (with `PYTHONPATH=src`); v1.0.2 Engineering Build 7 passed; v1.0.1 Engineering Fix 5 passed; v1.0 Experimental 4 passed. **36 original tests passed.** No original archive was modified.
- `CTA_FPL_Candidate_v1_0_2_plus_Workbench_2026-11-15.zip`: SHA-256 `ad4334228574ccfcc4bdfb6d3d4f7160a680837d58b92147d63b88ecda8b6305`, 70 ZIP entries, integrity passed; original core tests 7 passed and Workbench tests 17 passed.
- `CTA_FPL_INDEPENDENT_WORKSPACE_2026-11-17.zip`: SHA-256 `c482a282466e36d6eaa8f42f724e0103a29390954b2342d64a855714b6abb7c4`, 118 ZIP entries, integrity passed; provisional patched copy tests 11 core passed and 23 Workbench passed plus 3 subtests.
- The 17 November independent workspace is explicitly **provisional**. It contains a synthetic smoke input (match ID 999999); do not treat that as real multi-match evidence.
- The original archives are now available to Python in the current runtime at the paths above.

## 3. Repository and execution record

- GitHub repository: https://github.com/uasir/CTA-FPL-Model
- PR #3, provider-specific identity crosswalks, merged 2026-11-18: `4183f389f23c2da88e8067928428f84900d7960f`.
- PR #4, Onside source audit and continuity brief, merged 2026-11-18: `264f2792514d5927cc051d9fad36a6f03a2d3a24`.
- PR #5, standard EO definition correction, merged: `090cb01f5a3bf6668612e589ebad3f28ae5da4cd`.
- PR #6, written-permission gate for automated FPL API access, merged: `327c7ac717d0fae389fc866c078629c186176d89`.
- PR #7, exploratory CoVar workflow from Onside actual points, merged: `0299f37139d2ef39c1da63de2470e1f2e92e1075`.
- PR #8, rolling-window CoVar stability diagnostic, merged: `db7eed7241ef91319630e705edbff64e8dc5e3e6`.
- EO correction CI: [44259359716](https://github.com/uasir/CTA-FPL-Model/actions/runs/44259359716), success; 165 Python tests and 3 subtests passed.
- Permission-gate CI: [44259464265](https://github.com/uasir/CTA-FPL-Model/actions/runs/44259464265), success.
- CoVar workflow: [44259763220](https://github.com/uasir/CTA-FPL-Model/actions/runs/44259763220), success; artifact [14407138593](https://github.com/uasir/CTA-FPL-Model/actions/runs/44259763220/artifacts/14407138593).
- CoVar branch CI: [44259735610](https://github.com/uasir/CTA-FPL-Model/actions/runs/44259735610), success.
- CoVar stability CI: [44260208715](https://github.com/uasir/CTA-FPL-Model/actions/runs/44260208715), success; 172 Python tests and 3 subtests passed.
- CoVar split-window audit: [44260264105](https://github.com/uasir/CTA-FPL-Model/actions/runs/44260264105), success; artifact [14407094178](https://github.com/uasir/CTA-FPL-Model/actions/runs/44260264105/artifacts/14407094178).
- Latest main CI after PR #7: [44259849870](https://github.com/uasir/CTA-FPL-Model/actions/runs/44259849870), success; 37 JavaScript tests, 170 Python tests and 3 subtests passed. All three provider crosswalk validators still correctly report `EMPTY_NOT_READY`.
- GitHub Actions is the verified cloud execution route for Python/Node tests and licensed-source research jobs.

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
- These are historical verified ingestion results. Automated API ingestion, EO capture and Onside's official-API reconciliation are now gated until written data permission is obtained.

### Point-in-time features and baselines

- Lagged FPL feature and player-gameweek builders exist and have run.
- They are structurally lagged, but the historical source-vintage status remains `NOT_VERIFIED`; current API snapshots may include retrospective revisions.
- Rolling-history baselines and an exploratory ridge baseline have been evaluated. Results are not a validated production model.
- A private durable archive of deadline-time snapshots is still required; 90-day Actions artifacts are not a full-season archive.

### Recommendation systems

- Python and JavaScript implementations exist for both `general_market` and `personal_squad`.
- `general_market` has been run against the full 672-player official FPL pool. Its Python and JavaScript outputs were exactly numerically equal across the player pool and output categories. The latest forecast snapshot was stale relative to the target deadline and correctly labelled exploratory.
- `personal_squad` passed a 672-player scale smoke test using a **synthetic** legal 15-player squad; it evaluated 2,914 legal one-transfer candidates and built a legal 4-3-3. This was not the user's actual squad or a real manager recommendation.
- A real exploratory CoVar matrix has been generated from 10 completed 2026/27 gameweeks (Onside actuals only): 350 complete-panel players, 296 non-zero-variance players, 43,956 pair estimates. Run [44259763220](https://github.com/uasir/CTA-FPL-Model/actions/runs/44259763220); artifact [14407138593](https://github.com/uasir/CTA-FPL-Model/actions/runs/44259763220/artifacts/14407138593).
- The split-window stability diagnostic across GW1–GW5 vs GW6–GW10 found correlation-of-correlations **0.0078**, median absolute pairwise correlation change **0.5004**, mean change **0.5780** across 260 players and 33,670 pairs. This is not a formal stationarity test, but it is a strong warning that the covariance estimates are unstable. CoVar remains disabled in `personal_squad`.
- The user's manager-specific squad has not been supplied to this engineering run.

### Effective ownership

- A lock-safe top-10k weighted manager-pick EO collector is implemented and its mocked timing tests pass.
- Standard EO now counts all 15 squad picks plus captain and Triple Captain extras. Starting percentage and scoring exposure are separate outputs.
- No live near-deadline capture has been verified. Automated FPL collection is gated pending written permission. Global ownership from FPL history is not rank-tier EO. Do not use `selected_by_percent` as EO.

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
- PR #4: https://github.com/uasir/CTA-FPL-Model/pull/4 (merged)
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

1. **CTA event features aligned to FPL outcomes:** Wyscout 2017/18 event data is provider-published CC BY 4.0, but FPL target-data rights and point-in-time vintages remain unresolved. Opta/PulseLive rights are unresolved.
2. **Historical FPL point-in-time snapshots:** the current lagged dataset is structurally safe but not vintage-verified. Automated FPL API jobs are gated until written permission is obtained. A private durable archive is still required; do not place manager-specific data or private snapshots in the public repo.
3. **Verified player crosswalks:** StatsBomb, Wyscout and Opta/PulseLive crosswalks remain empty. No name-only or fuzzy joins.
4. **EO live validation:** corrected standard EO logic and lock-safe collector are tested, but no live post-deadline capture has been accepted; automated capture awaits written permission.
5. **360 anomaly:** match `3837706` remains quarantined pending source provenance.
6. **Personal-squad risk/CoVar:** a 10-GW exploratory covariance panel exists, but it is too short and selection-biased for production risk use; keep disabled in the personal-squad engine.
7. **Data rights:** written permission for automated FPL API collection, private archival and research/model use is not yet obtained. Do not enable the gated workflows.

## 8. Immediate next actions

1. Obtain written permission from the FPL/Premier League rights holder for automated API access, private deadline snapshots, research/model development and intended publication. Ask Football DataCo about Opta/PulseLive match data.
2. After permission, create a private durable archive destination (private GitHub repository or private cloud folder) and enable the workflow gate only for the approved scope.
3. Continue Wyscout 2017/18 event-side parsing and numeric identity/fixture reconciliation under CC BY 4.0, but keep FPL target joins blocked until target rights are cleared.
4. Extend CoVar history beyond 10 gameweeks, test rolling-window stability and run time-ordered out-of-sample validation; keep it disabled in `personal_squad` meanwhile.
5. Preserve the 34-match StatsBomb engineering benchmark and investigate the quarantined 360 source anomaly without modifying source records.
6. After permission, validate live EO capture and archive only the approved outputs and provenance.
7. Only after rights, identity, point-in-time and predictive-validation gates pass, add CTA-derived player-gameweek features to the FPL forecast layer.

## 9. Durable evidence links

- 34-match parity: https://github.com/uasir/CTA-FPL-Model/actions/runs/44091783751
- FPL official ingestion + general-market integration history: https://github.com/uasir/CTA-FPL-Model/actions/runs/44255361502
- Provider-specific identity crosswalk PR (merged): https://github.com/uasir/CTA-FPL-Model/pull/3
- Onside benchmark audit PR #4 (merged): https://github.com/uasir/CTA-FPL-Model/pull/4
- Main CI after merges: https://github.com/uasir/CTA-FPL-Model/actions/runs/44257955121
- Onside benchmark source audit run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44257817207
- Onside dataset and CC BY 4.0 terms: https://onsidearena.com/data
- Onside public accuracy ledger: https://onsidearena.com/accuracy
