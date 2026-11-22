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

## What is required before scenarios can be emitted

1. Accumulate genuine prospective conventional M3 forecast snapshots and their later official outcomes, matched by exact season, Gameweek and player ID.
2. Preserve the same exact conventional model version as the target M3 archive.
3. Preserve the observed event-live availability timestamp for every matched Gameweek and require it to precede the target training cutoff.
4. Require at least five complete Gameweek residual blocks for the prototype; incomplete player coverage remains missing and is never zero-filled.
5. Keep the full player-level scenario payload private. Keep `probability_calibrated=false`, `decision_weight=0`, `production_eligible=false`, and `covar_used=false`.

The current preflight should therefore pass archive verification but report a blocked CoVar producer state. That is the correct result for the available evidence, not an engineering failure to work around.
