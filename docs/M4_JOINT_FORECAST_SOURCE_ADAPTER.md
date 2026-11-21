# M4 joint forecast source adapter and private archive

This source-neutral adapter accepts a complete explicit joint Gameweek forecast
document and the exact raw source, model, configuration and forecast-payload
bytes referenced by its provenance. It validates the intake contract, checks
the hashes before writing, writes a private local archive, then independently
rehashes the written archive using the existing archive verifier.

## Inputs

The caller supplies a document conforming to the explicit joint forecast
intake contract, a byte mapping keyed by source:<source_id>, model_artifact,
config and forecast_payload, and a new archive destination outside the Git
checkout. Missing or additional byte artifacts are rejected.

## Security

The adapter refuses overwrite, unsafe forecast/source path identifiers and
destinations inside a Git repository, including paths reached through symlinks. It writes a staging directory with
0700 directory and 0600 file permissions, verifies the complete byte chain,
then atomically renames the staging directory. Failure removes staging files.

## Limitations

No provider is selected or called. No probabilities or scenarios are generated.
The adapter cannot authenticate provider claims or historical availability.
It is an offline intake/archival component pending a provider-specific source
connector and a separately approved private Actions handoff. Research-only
flags remain enforced.
