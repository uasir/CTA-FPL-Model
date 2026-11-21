# Private CoVar forecast archive setup

The M3-to-CoVar handoff writes only a sanitized conventional M3 forecast bundle to a separate private GitHub repository. It does not copy the raw M3 evidence bundle, manager identity, squad, bank/transfers, frozen recommendation, or manager-specific decision state into the archive.

## One-time GitHub setup

1. Create a new repository named `cta-fpl-covar-archive` under the `uasir` account.
2. Set **Visibility** to **Private**. Initialize it with a README so it has a default branch.
3. Create a fine-grained personal access token restricted to this one repository:
   - Repository access: **Only select repositories** → `cta-fpl-covar-archive`
   - Repository permissions: **Contents: Read and write**
   - Metadata: read-only (GitHub's required repository metadata permission)
   - Use an expiration and rotate the token before it expires.
4. In the public source repository `uasir/CTA-FPL-Model`, open **Settings → Secrets and variables → Actions → New repository secret**.
5. Name the secret exactly `COVAR_ARCHIVE_TOKEN` and paste the fine-grained token value.

Do not put the token in source code, workflow inputs, a commit, or an artifact. Do not grant the token access to the public source repository or unrelated repositories.

## Handoff behavior

The workflow `.github/workflows/cta-fpl-m3-covar-private-archive.yml` is designed to:

- Trigger after a successful `Capture pre-deadline FPL decision evidence` run on `feat/m3-unified-evaluation-report`, or be dispatched manually with a source run ID.
- Download the source run's existing artifact into the ephemeral GitHub runner.
- Run the M4 manager-free extraction adapter and archive packager.
- Validate that the destination repository is private.
- Commit only the sanitized forecast bundle and hash/provenance manifests to the private repository.
- Refuse to overwrite an existing source-run archive.
- Never upload a new public artifact or commit source manager-specific evidence.

Archive layout: `<season>/gw<NN>/source-run-<M3-run-id>/`.

The bundle contains the conventional M3 forecast snapshot and FPL player metadata, including the provider and metadata raw source payloads needed for later hash verification. It excludes manager identity, squad, bank/transfers, frozen decision and recommendation result.

## Activation and limitations

The workflow must be merged into the source repository's default branch before GitHub will activate its `workflow_run` trigger. Its code checks out the sanitization adapter from `feat/m4-field-portfolio-intelligence`; after the M4 code is merged or moved, update that pinned ref deliberately.

The existing M3 evidence workflow currently uploads its input artifact publicly. This handoff does not re-upload that artifact; it downloads it transiently and stores only the sanitized CoVar forecast privately. The existing artifact's current visibility/retention is unchanged. A separate change is required if the project decides to stop public publication of the full M3 evidence bundle, because that may affect independent M3 replay/validation.

A successful handoff proves that the adapter accepted the M3 evidence and that the sanitized bytes were committed to the private destination. It does not authenticate the provider's publication timestamp, establish forecast calibration, or make CoVar production-eligible. CoVar remains research-only with `decision_weight=0` and `production_eligible=false`.
