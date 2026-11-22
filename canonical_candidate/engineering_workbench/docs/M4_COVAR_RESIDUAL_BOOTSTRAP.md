# CoVar residual-block bootstrap — research baseline

## Purpose

This is the first empirical joint-outcome baseline on the conventional M3 forecast path. It uses the exact M3 player expected-points snapshot as the mean anchor and samples complete historical Gameweek vectors of forecast residuals:

`player residual = final FPL points - that Gameweek's pre-deadline M3 expected points`

For each historical Gameweek, the residual vector is kept intact across the target players. Each player's residuals are centered across the eligible historical blocks before being added to the target M3 expected-points value. This preserves the target forecast's marginal expected-points mean while retaining the observed cross-player residual co-movement in each sampled Gameweek. The producer can be restricted to the exact union of candidate and anonymized field portfolio player IDs, avoiding an unnecessarily large all-player universe. It also carries centered minutes residuals in the same sampled blocks, clips scenario minutes to the valid 0–90 Gameweek range, and derives explicit `played` flags for the existing lineup resolver. Points and minutes remain paired to the same source Gameweek.

## Why this is a baseline, not a calibrated producer

- It is a non-parametric block-resampling reference, not a learned fixture-event model.
- Equal scenario weights are empirical resampling weights, not calibrated predictive probabilities.
- It requires the exact same conventional model version for the target and historical residuals.
- It uses only historical Gameweeks for which every requested target player has an observed, finality-reconciled forecast/outcome match. Incomplete blocks are excluded as a whole; missing player rows are never zero-filled.
- A historical outcome is eligible only when its observed official event-live capture timestamp is strictly before the explicit training cutoff. A retrospective finality pass without an observed availability timestamp is insufficient.
- It does not model player transfers, role changes, injuries, fixture-level event allocation, or conditional regime changes. The existing lineup resolver can apply autosubs to the supplied minutes/played outcomes, but this does not make the residual probabilities calibrated.
- Five complete Gameweeks is only the testable prototype floor. It is not an adequacy threshold. Small-sample warnings and out-of-sample validation remain mandatory.

## Provenance change

The official event-live finality audit now preserves the exact event-live source retrieval timestamp as `outcome_available_at_utc`. The forecast/outcome matcher carries that value into each per-Gameweek match archive, and the multi-Gameweek panel carries it into its cluster manifest. This is a conservative observed-availability timestamp, not a claim about the first instant the public endpoint became available.

Older archives without this timestamp remain valid for descriptive matched-error analysis but cannot be admitted to this residual bootstrap.

## Output and safeguards

The producer emits a versioned player-Gameweek scenario set, source Gameweek IDs, complete/excluded cluster lists, a deterministic payload hash, and explicit limitations. It always sets:

- `probability_calibrated=false`
- `decision_weight=0`
- `production_eligible=false`
- `covar_used=false`

The artifact is not yet wired into recommendation decisions or treated as a replacement for the full joint fixture-state producer. It must first be evaluated against the expanding-window historical-frequency benchmark with Gameweek-clustered uncertainty intervals, then compared prospectively on held-out Gameweeks. The existing CoVar eligibility gate remains authoritative.
