# M3-anchored CoVar scenario-model input contract

## Purpose

This contract is the first modelling layer after the existing M3 integration.
It binds the conventional FPL Cat player-level xP/minutes snapshot to
chronologically eligible, officially reconciled historical FPL player-fixture
outcomes. It does not introduce another forecast provider and does not use CTA
as the CoVar forecast source.

## Intended model boundary

- M3 FPL Cat xP and expected minutes remain the player-level expectation anchor.
- Official FPL realized player-fixture outcomes supply historical outcome
  distributions and dependence evidence.
- The eventual CoVar model must generate explicit joint Gameweek scenarios and
  model-generated probabilities, with its own versioned model/config artifacts.
- The scenario model must preserve within-fixture and cross-player dependence;
  it must not multiply independent player or fixture marginals.
- Model-generated probabilities are not calibrated simply because they are
  normalized. They must be evaluated chronologically against reconciled
  outcomes and leakage-safe reference forecasts.

## Input gates

1. M3 anchor must be the conventional M3 CoVar bundle, regular Gameweek mode,
   with decision weight zero and production eligibility false.
2. Anchor player IDs must be unique, with finite expected points and expected
   minutes. The M3 as-of must precede deadline and first kickoff.
3. Training cutoff must not follow the M3 as-of.
4. Every training Gameweek must precede the target Gameweek and its first
   kickoff must precede target kickoff.
5. Every historical Gameweek must carry PASS_EXACT_MATCH official FPL
   finality reconciliation, a dataset SHA-256, an explicit outcome-availability
   timestamp, and complete non-empty player-fixture rows.
6. Outcome availability must be strictly before the model training cutoff.
7. Duplicate player-fixture keys, invalid IDs, missing timestamps, non-finite
   minutes/points and unsupported availability evidence types are rejected.

## Evidence limitations

The validator checks the declared chronology and finality status. It does not
authenticate the historical availability timestamp or verify the supplied
dataset bytes itself. Those require a separately verified source manifest and
archive. Retrospective finality reconciliation establishes agreement with the
captured official event-live response; it does not prove when that response
became available historically.

The current GW1-10 realized dataset is retrospective. It can be used for
exploratory development, but cannot be labelled fully point-in-time authenticated
without defensible historical outcome-availability evidence. Prospective
archives must be captured before deadline and retained for later validation.

## Research-only boundary

This is an input contract, not a probability model. It does not create scenarios,
estimate probabilities, infer dependence, or claim predictive validity.
Decision weight remains zero and production eligibility remains false; no
recommendation, transfer, starting XI or captaincy changes are permitted.
