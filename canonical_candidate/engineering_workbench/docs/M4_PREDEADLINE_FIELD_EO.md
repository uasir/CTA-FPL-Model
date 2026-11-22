# M4-T5 — Pre-deadline field EO acquisition

## Purpose
Capture a time-stamped, rank-stratified sample of managers' current picks before
the target Gameweek deadline. This is a decision-time field estimate, distinct
from the existing post-lock capture of final picks.

## Method
- Freeze the top-10,000 rank cohort from the official FPL classic league standings.
- Sample 400 managers equally across 200 rank pages (two managers per 50-rank page).
- Fetch each sampled manager's current target-Gameweek picks before the deadline.
- Estimate standard EO using the existing estimator; retain ownership, starting,
  captain, Triple Captain and scoring-exposure measures separately.
- Record cohort and picks capture timestamps, sample/effective sample sizes,
  weighting, rank bounds and manager-sample hash.
- Write CSV and JSON report; hash the CSV bytes.

## Temporal and statistical boundaries
The entire capture is discarded if the cohort or sampled picks finish at or
after deadline. The report sets `picks_lock_verified=false` and labels evidence
`PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE`. Picks may still change before lock.
It is a stratified sample, not global census or final locked EO. It must never be
relabelled as post-lock evidence. The pre-deadline contract can admit it only
when its capture timestamp precedes the same target deadline and candidate
decision timestamp is also before deadline.

The workflow is scheduled and manually dispatchable. A missed window, partial
sample, API failure, or deadline crossing yields no admitted snapshot.
