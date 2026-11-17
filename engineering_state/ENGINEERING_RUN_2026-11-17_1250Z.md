# CTA-FPL-Model engineering state — 2026-11-17 evening

## Recovery and provenance

- All five required original archives were recovered from the Library and extracted into separate directories:
  - `CTA_FPL_reconstruction_scaffold_v0_1.zip`
  - `CTA-FPL-Engineering-Workbench.zip`
  - `CTA_FPL_Model_v1_0_2_Engineering_Build.zip`
  - `CTA_FPL_Model_v1_0_1_Engineering_Fix.zip`
  - `CTA_FPL_Model_v1_0_Experimental.zip`
- All five ZIP integrity checks passed; SHA-256 hashes are recorded in the recovery manifest.
- The GitHub repository's current `canonical_candidate/src/cta_engine.py` was byte-for-byte identical to the recovered v1.0.2 source (Git blob SHA `e00f0fe3a1a66c003609599e3417b81ba107c918`). The independent workspace candidate is a separate Python-only derivative with a zero-filled player schema and match-scoped 360 audit; it did not contain the JavaScript port. The GitHub repository contains the JavaScript port and pilot parity fixtures. These sources must be reconciled, not treated as interchangeable.

## Verified baseline results

- Recovered archive test suites: scaffold 3/3; experimental 4/4; v1.0.1 5/5; v1.0.2 7/7; original Workbench 17/17.
- Independent workspace derivative: core 11/11; Workbench 23 passed with 3 subtests; Python compileall passed.
- GitHub Actions run `44085658038` on commit `d02c64cc0d22014c4ccbcf290cc16ed78843e43d` completed successfully:
  - Python core tests: 7 passed.
  - Workbench Python tests: 20 passed, 3 subtests passed.
  - 34/34 match-level Python–JavaScript parity comparisons passed.
  - 1,027 player rows, 5,967 sequence rows, and 6,528 xT cells were compared.
  - Feature comparisons: 20,540 player; 137,241 sequence; 6,528 xT; all within the declared tolerance.
- This is implementation parity only. It is not evidence of calibrated CTA scores, FPL points prediction, or improved transfer/captain decisions.

## Data-quality finding

- The 34-match run staged 23 StatsBomb 360 files and 11 matches without 360.
- Match `3837706` is a real source-quality anomaly: at the pinned StatsBomb commit, its 360 file contains 3,548 unique frame UUIDs, but none matches the 4,026 event IDs in the same match's event file. The other 22 staged 360 files have complete frame-to-event UUID joins.
- The original parity auditor called this linkage `PASS` because it only checked that Python and JavaScript reported the same values; it did not check whether the values were valid.
- The new quality policy keeps the source SHA/size in the manifest but excludes this invalid 360 file from model inputs. The sample therefore has 34 verified event sources, 22 usable 360 sources, 1 explicitly excluded invalid 360 source, and 11 matches with no 360 source.

## Current branch work

Branch: `engineering/reconcile-34match-quality-20261117`

Changes prepared on this branch:
- Match-scoped 360 linkage in Python and JavaScript.
- Zero-filled counter-backed player counts in both implementations; mean action xT and per-90 remain blank/null when denominators are unavailable.
- Updated parity contract to version 1.1.0 and added the new 360 match key to parity comparison.
- SHA-pinned StatsBomb downloader and sample manifest with the invalid 3837706 360 source explicitly excluded.
- Separate source/data-quality audit and tests.
- Workflow updated to run Python, JavaScript, parity, and data-quality checks, then upload complete reports.

Local tests for the downloader and quality-audit work passed: 28 Workbench tests plus 3 subtests; the new quality audit correctly fails the old artifact and passes the simulated corrected staging policy (22 valid, 1 excluded, 11 unavailable). Remote branch CI/PR validation remains pending.

## Replit / execution access

- Replit project is connected and searchable, but the agent inspection call returned a paused phase with an empty response; no further Replit-side edits or export were available.
- Python/container execution is available. GitHub repository read/write access is available. Main has not been modified; all reconciliation work is on the branch above.

## Remaining roadmap / next action

1. Finish remote CI validation of the reconciliation branch and inspect the resulting 34-match artifact.
2. Confirm source SHA/size verification passes for all 34 event files and 22 usable 360 files.
3. Reconcile the Python and JavaScript player schemas and match-scoped 360 audits with the recovered code, then freeze a versioned feature contract.
4. Add stable StatsBomb player IDs, trusted minutes, and verified FPL player-ID aliases; current mappings are empty/unsupported.
5. Harmonise shot-linked and non-shot sequence definitions, add human review and inter-rater reliability, and quantify uncertainty.
6. Obtain a permitted current-season Premier League event source; the selected StatsBomb Open Data sample is historical and incomplete for current FPL.
7. Only then run time-ordered FPL backtests against the frozen baseline, report MAE/RMSE, rank correlation, calibration and decision utility, and test whether CTA adds value. EV/EO/CoVar integration remains downstream; CoVar is the priority but is not yet computed by this feature prototype.
