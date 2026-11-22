# M3 CoVar: real archive integration and evidence gate

## Integration

The residual-block bootstrap producer is now ported onto the current M3 branch. The integration consumes the existing private, manager-free M3 forecast archive and the official realized-outcome evidence artifact. It does not reconstruct forecasts, use synthetic residuals, or substitute CTA/CDF/CTS forecasts.

The preflight verifies:
- exact M3 archive bundle SHA-256 and byte count against `archive_manifest.json`;
- exact snapshot, season, target Gameweek, model version and timing identity;
- raw FPL Cat provider and official bootstrap payload hashes;
- manager-free privacy declarations;
- official event-live capture manifests and their observed availability timestamps;
- the presence and temporal eligibility of a real multi-Gameweek forecast/outcome panel before invoking the producer.

If a real panel is supplied and passes the producer's strict checks, the scenario payload is stored only in the private `uasir/cta-fpl-covar-archive` repository. Public Actions artifacts contain only an aggregate preflight report.

## First real archive inspected

Private M3 archive:
- Path: `2026-27/gw11/source-run-44809552413/`
- M3 source workflow run: `44809552413`
- Snapshot: `fplcat-gw11-20261120T201442368955Z`
- Target: 2026/27 GW11
- Forecast as-of: `2026-11-20T20:14:42.975478Z`
- Deadline: `2026-11-21T11:00:00Z`
- Model version: `external:FPL Cat:published xP:public next-gameweek JSON API:api/v1`
- Bundle SHA-256: `411ce54287339f11b692cbb51611334074e390d1cf8ef86f39bf8f825862fe8a`

The bundle is explicitly manager-free, its provider and metadata raw payloads are hash-bound, and it remains research-only.

## Realized-outcome evidence and current blocker

The official GW1-GW10 finality artifact is:
- Workflow run: `44882707622`
- Artifact: `cta-covar-realized-evidence-44882707622-1`
- Finality result: `PASS_ALL_EVENTS` for GW1-GW10.

That finality pass is not proof that the historical outcomes were observed by the GW11 forecast cutoff. The archived event-live capture manifests show the first observed event-live retrieval at approximately `2026-11-21T08:00:15Z`, whereas the GW11 M3 forecast as-of was `2026-11-20T20:14:42.975478Z`. The observed retrieval is later than the forecast's training cutoff. The preflight therefore blocks those outcomes from GW11 residual training.

There is also no verified accumulated prospective conventional forecast/outcome matched panel for GW1-GW10. A finality-only realized-points panel cannot substitute for forecast residuals. Retrospective FPL points without matching same-version pre-deadline M3 forecasts are not residual observations.

## Prospective match-archive intake

A separate manual workflow, `.github/workflows/cta-fpl-m3-covar-match-prospective-evidence.yml`, now connects a specific manager-free M3 forecast archive to a later official finality artifact. It:
- re-verifies the exact M3 bundle SHA-256, byte count, model version, raw FPL Cat provider bytes and official bootstrap metadata bytes against the private archive manifest;
- requires the official realized player-Gameweek and fixture CSVs plus the exact event-level finality report;
- matches only the intersection of observed FPL element IDs, with no zero-fill;
- records the conservative observed outcome availability timestamp from `reports[].source_provenance.captured_at_utc` when the finality report does not carry a dedicated `outcome_available_at_utc` field;
- writes the matched player-level archive only to the private CoVar archive repository, with immutable hashes and research-only flags.

This workflow is manual because the forecast can only be matched after the corresponding Gameweek's final official scoring reconciliation is complete. The current GW1-GW10 finality artifact cannot match GW11 because it does not contain an event-11 finality pass. When GW11 finality is available, the exact GW11 M3 forecast archive can be matched and preserved as the first prospective residual block. It becomes eligible only for a later target forecast whose training cutoff is strictly after the recorded outcome-availability time and whose model version is identical.

## What is required before scenarios can be emitted

1. Accumulate genuine prospective conventional M3 forecast snapshots and their later official outcomes, matched by exact season, Gameweek and player ID.
2. Preserve the same exact conventional model version as the target M3 archive.
3. Preserve the observed event-live availability timestamp for every matched Gameweek and require it to precede the target training cutoff.
4. Require at least five complete Gameweek residual blocks for the prototype; incomplete player coverage remains missing and is never zero-filled.
5. Keep the full player-level scenario payload private. Keep `probability_calibrated=false`, `decision_weight=0`, `production_eligible=false`, and `covar_used=false`.

The current preflight should therefore pass archive verification but report a blocked CoVar producer state. That is the correct result for the available evidence, not an engineering failure to work around.
