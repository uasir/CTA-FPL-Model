# M4 joint forecast source adapter and private archive

This adapter is the private archive boundary for CoVar's own explicit joint
scenario model. The model is to be built around the already-integrated M3
conventional FPL Cat xP/minutes anchor and reconciled historical official FPL
outcomes. The adapter accepts the complete joint Gameweek forecast document
and exact historical-source, model, configuration and forecast-payload bytes
referenced by provenance. It validates the intake contract, checks hashes,
privately archives the complete document and independently rehashes the
provenance-linked artifacts.

## Inputs

The caller supplies a document conforming to the explicit joint forecast
intake contract, a byte mapping keyed by source:<source_id>, model_artifact,
config and forecast_payload, and a new archive destination outside the Git
checkout. Missing or additional byte artifacts are rejected.

The CLI accepts the same inputs as files:

```text
python m4_covar_joint_forecast_source_adapter.py \
  --document /path/to/forecast.json \
  --artifact-dir /path/to/covar-model-artifacts \
  --archive-root /private/archive/gwNN-forecast-id
```

The artifact directory layout is `sources/<source_id>.bin`,
`model/model.bin`, `model/config.bin` and `forecast/payload.bin`.
The CLI rejects symlinked artifact files and preserves the validated forecast
document in the archive as `forecast/validated_document.json`.

## Security

The adapter refuses overwrite, unsafe forecast/source path identifiers and
destinations inside a Git repository, including paths reached through symlinks. It writes a staging directory with
0700 directory and 0600 file permissions, verifies the complete byte chain,
then atomically renames the staging directory. Failure removes staging files.

## Limitations

No external joint-forecast provider is required or being sought. The adapter
does not itself generate probabilities or scenarios; that is the responsibility
of the M3-anchored CoVar model. Historical outcome availability and provider
publication claims are not authenticated by this adapter. A private Actions
handoff remains a separate task. Research-only flags remain enforced.
