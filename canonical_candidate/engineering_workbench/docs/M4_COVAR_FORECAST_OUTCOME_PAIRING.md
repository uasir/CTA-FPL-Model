# M4 CoVar forecast-to-outcome pairing

## Purpose

`m4_covar_joint_forecast_outcome_pairing.py` builds calibration-ready rows only
after historical joint forecasts pass the existing chronological, provenance,
and archived-byte acceptance gates, and a separately versioned resolver supplies
an explicit observed joint state for each realized Gameweek.

This is a pairing contract. It is not a joint-state resolver, forecast generator,
probability estimator, or source-authentication service.

## Required inputs

### Forecast archive

Each forecast row must satisfy the existing joint-forecast dataset and provenance
contracts, and its source, model, configuration, and forecast payload bytes must
be present in the archive manifest and pass SHA-256 verification.

In addition to the existing forecast fields, each row supplies:

- `season`, `gameweek_id`
- `state_catalogue_sha256`: hash of the complete, versioned joint state catalogue
- `player_universe_sha256`: hash of the exact player universe represented
- `player_count`
- model and reference probability maps with identical state IDs

The state catalogue must include the observed state even when the forecast assigns
it zero probability. The calibration evaluator then records a zero-probability
actual outcome as infinite/unavailable log loss rather than silently clipping it.

### Realized state mapping

Exactly one mapping per season/Gameweek is required. It must provide:

- `mapping_status=PASS_EXACT_OBSERVED_STATE_RESOLUTION`
- `mapping_inferred_from_marginals=false`
- `finality_audit_status=PASS_EXACT_MATCH`
- retrospective final-scoring temporal status
- matching state-catalogue and player-universe SHA-256 values
- a SHA-256 identifying the resolver's mapping evidence bytes
- resolver name and version
- observed state ID
- exact mapped player count, with zero missing and unexpected players

The mapping source hash is a declaration checked for shape and consistency. The
pairing module does not fetch or authenticate those bytes, nor inspect the resolver
implementation. The caller must retain and independently review those artifacts.

## Pairing rules

- Every forecast must have one realized mapping for its season/Gameweek.
- Multiple forecast snapshots for one Gameweek share the same observed state,
  state catalogue, player universe, and resolver evidence.
- The observed state ID must exist in the forecast's complete state catalogue.
- Model and reference probability maps must use the same catalogue.
- Forecast acceptance includes chronological split validation and complete
  archive-byte verification.
- Extra realized mappings without forecasts are rejected.
- No state is inferred from player xP, ownership, EO, or marginal probabilities.

## Output

The output contains calibration-ready rows in the exact shape accepted by
`evaluate_joint_probability_calibration`, plus per-Gameweek pairing evidence.
It remains research-only:

- `decision_weight=0`
- `production_eligible=false`
- retrospective outcomes are not represented as point-in-time features
- historical forecast availability is not authenticated by this pairing step

## Current readiness

No real pre-deadline joint forecast archive and no independently reviewed
realized-state resolver outputs have yet been supplied. Synthetic unit tests
validate the contract only; they do not constitute historical calibration
evidence. The module must not be described as having produced a real paired
historical dataset until those inputs exist and pass acceptance.
