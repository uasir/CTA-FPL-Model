# M4 explicit joint-forecast intake contract

## Purpose

This source-independent contract defines what a genuine prospective joint FPL
forecast must provide before it can enter CoVar's existing scenario, realized
state, and historical evaluation pipeline. It is an intake boundary, not a
forecast model and not a probability estimator.

## Required source payload

The JSON document must declare:

- schema version `1.0.0` and forecast kind
  `EXPLICIT_JOINT_GAMEWEEK_DISTRIBUTION`;
- unique forecast ID, season, target Gameweek, deadline and pre-deadline as-of;
- the complete player universe and every fixture in the Gameweek;
- multiple complete joint scenarios, each with a unique ID, explicit
  source-supplied probability, every fixture state, and one aggregate
  Gameweek outcome for every declared player;
- model, config, state-catalogue and forecast-payload versions/hashes, model
  training cutoff, generation timestamp, and versioned source snapshots with
  availability/retrieval timestamps and content hashes.

Probabilities must be strictly positive and sum to 1.0. Every scenario must
cover the same player and fixture universes. The intake does not derive player
points from marginal xP, EO, fixture marginals or independent fixture models.
FPL points are supplied by the forecast source and may be negative.

## Temporal and provenance rules

The forecast as-of and source retrieval timestamps must precede the Gameweek
deadline. Every source must have been available and retrieved no later than the
forecast as-of. The existing provenance validator checks declared hashes and
timestamp metadata; the archive verifier must separately rehash actual source,
model, config and forecast payload bytes. Neither check authenticates the
provider's historical availability claim or proves model execution.

## Explicit non-goals

- No source/provider or probability model is selected by this contract.
- No scenario probabilities are generated or repaired.
- No Cartesian product or fixture-independence assumption is permitted.
- No inferred manager portfolios from marginal EO.
- No recommendation, transfer, XI or captaincy influence.
- `decision_weight=0`; `production_eligible=false`.

A successful structural intake is not calibration, historical validation,
forecast skill, or production approval. The first genuine source must be
identified and its pre-deadline forecasts archived before any prospective
validation can begin.
