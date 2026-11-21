# M4 CoVar exact realized joint-state resolver

## Purpose

`m4_covar_realized_joint_state_resolver.py` maps a reconciled official FPL
player-Gameweek outcome vector to a state in a forecast producer's declared
joint state catalogue. It uses exact equality over the full player universe:

- Gameweek minutes
- whether the player played in any fixture
- total FPL points

No nearest-neighbour matching, interpolation, missing-row zero-fill, or
marginal xP/EO inference is permitted.

## Inputs

- Realized player-Gameweek rows from the retrospective official FPL dataset.
- A complete, versioned joint state catalogue with unique scenario IDs and
  player outcomes for every player in the exact Gameweek universe.
- Exact bytes identifying the realized dataset source.
- A matching official event-live finality audit with `PASS_EXACT_MATCH`.

The resolver rejects duplicate player rows, wrong-season/Gameweek rows,
incomplete scenario player coverage, invalid numeric values, and failed
finality evidence.

## Hash contract

The resolver emits deterministic SHA-256 values:

- `player_universe_sha256`: canonical JSON of the sorted string player IDs.
- `state_catalogue_sha256`: canonical JSON of catalogue states sorted by
  player ID, with minutes and FPL points normalized as decimal strings.
- `realized_source_sha256`: exact supplied realized-source bytes.
- `mapping_source_sha256`: canonical JSON of the mapping evidence.

Forecast producers must use the same canonical catalogue and player-universe
hash contracts. The pairing builder rejects hash mismatches.

## Outcomes

Exactly one matching state yields
`PASS_EXACT_OBSERVED_STATE_RESOLUTION` and an observed state ID.

No matching state yields `FAIL_NO_EXACT_STATE_MATCH`. More than one matching
state yields `FAIL_AMBIGUOUS_STATE_MATCH`. Neither failure is repaired by
selecting a nearby state. A no-match is a direct indication that the supplied
catalogue did not contain the realized outcome vector.

The passing output is shaped for
`m4_covar_joint_forecast_outcome_pairing.py`, including the resolver identity,
hashes, exact player coverage and retrospective finality status.

## Limitations

- The resolver does not prove that the forecast state catalogue was exhaustive.
- It does not generate scenarios or assign probabilities.
- It cannot authenticate the supplied source bytes or resolver runtime.
- Retrospective official scoring reconciliation is not point-in-time forecast
  feature availability.
- A passing exact state match is not evidence of forecast calibration.

All outputs remain research-only with `decision_weight=0` and
`production_eligible=false`.
