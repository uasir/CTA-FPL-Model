# CTA–FPL decision integration status

**Status date:** 2026-11-19  
**Workstream:** `feat/verified-11footy-fpl-identity-bridge`  
**Purpose:** Integrate contextual-threat evidence into FPL decisions without replacing the existing FPL baseline or creating another effective-ownership system.

## Current architecture

- Official FPL `ep_next` remains the frozen expected-points baseline.
- The existing 11footy-derived CTA feature sidecar is joined to the official FPL forecast by verified FPL element IDs and fixture IDs.
- CTA context is passed through the Python and JavaScript personal-squad engines to the owned squad, starting XI, bench and transfer alternatives.
- The existing LiveFPL effective-ownership view remains the external field reference. This project does not create a second EO system.
- CTA features do not currently alter `ep_next`, expected-points rankings, transfer ordering or CoVar. No CTA composite has been promoted.

## Verified current-season identity and coverage

Latest completed 2026/27 11footy integration report:

- 340 exact normalized name/team/date-of-birth identities verified against official FPL.
- 2,526 player-match rows joined to verified FPL identities and fixtures.
- 100/100 provider matches mapped to FPL fixtures.
- 316 players have prior-match history available for the GW11 feature snapshot.
- All 672 official FPL players have a target fixture row for GW11.
- Source snapshot: 2026-11-10 12:21:18 UTC; GW11 deadline: 2026-11-21 11:00 UTC.
- The feature snapshot is deadline-safe, but remains research-only. Identity verification is not prediction validation.

## Historical Wyscout identity bridge

The 2017/18 cross-provider resolver requires exact normalized full name and date of birth agreement between Wyscout and 11footy, agreement on the same historical FPL element, P1 evidence from both providers, team corroboration, positive FPL minutes, fixture-history overlap and one-to-one IDs.

Latest verified report:

- 515 Wyscout identity candidates and 602 11footy candidates.
- 312 exact name/date-of-birth key matches.
- 91 strict cross-provider identities verified.
- Zero one-to-one ID collisions.
- 380/380 Wyscout matches mapped to historical FPL fixtures.
- 2,693 verified Wyscout player-fixture rows joined for 91 FPL players.
- 2,602 rows have strictly earlier player history available.

The historical FPL archive has no DOB. DOB agreement is between the two independent event providers; their independently corroborated FPL element mapping supplies the historical FPL link.

## First chronological incremental-value test

A single chronological 2017/18 holdout compared:

- Baseline: prior 3/5-match FPL points and minutes.
- Augmented: the same baseline plus 42 prior 3/5-match Wyscout event-threat features.
- Train: 1,802 player-fixture rows; test: 800 rows; 91 train and 89 test players.

| Metric | FPL-history baseline | Baseline + Wyscout features |
|---|---:|---:|
| Test MAE | 2.4269 | 2.4154 |
| Test RMSE | 3.1323 | 3.1694 |

MAE improved by 0.47%, while RMSE worsened. This is a weak and mixed exploratory result. It does not justify CTA weighting or a production decision adjustment.

A follow-up refinement adds per-90 normalisation using prior FPL minutes and reruns the chronological comparison. It must not use the target match's minutes or event data.

## Explicit limitations

- The 2017/18 historical FPL archive may contain retrospective corrections; it is not a point-in-time snapshot archive.
- Wyscout's public event schema has no pass-recipient IDs or xG and does not provide continuous player tracking.
- The 11footy dataset is CC BY-NC 4.0 and is restricted to non-commercial use.
- The Wyscout event metrics are event-count/geometric proxies, not calibrated xT or a validated CTA composite.
- The personal-squad scale smoke test uses a synthetic squad. It is not an analysis of manager entry 421025.
- CoVar remains unused in the personal-squad engine pending validated player-level covariance.

## Promotion gates

1. Finish per-90 and robustness tests on the historical Wyscout panel.
2. Extend identity-verified CTA/player-match coverage across more seasons and providers.
3. Obtain independent human review and inter-rater reliability for CTA event labels and sequence boundaries.
4. Build point-in-time FPL outcome snapshots and run rolling-origin, multi-season backtests.
5. Demonstrate incremental decision value against the frozen FPL baseline and the existing LiveFPL field reference.
6. Only then calibrate and enable a CTA decision adjustment; retain an auditable baseline-only fallback.
7. Apply the validated output to the real manager squad using entry 421025. Do not treat synthetic parity tests as personal-team results.

**Current decision-use status:** `RESEARCH_ONLY_NOT_IN_BASELINE`.
