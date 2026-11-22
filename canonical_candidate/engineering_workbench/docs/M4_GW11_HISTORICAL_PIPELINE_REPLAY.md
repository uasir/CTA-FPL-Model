# M4 — GW11 historical pipeline replay

Status: **REHEARSAL INPUT ONLY — NOT A GW12 RECOMMENDATION**

## Purpose

Use the published GW11 forecast snapshot solely to exercise the end-to-end M3-to-M4 data path while a GW12 forecast is unavailable. This is a historical pipeline rehearsal, not a transfer recommendation for GW11 or GW12.

## Required path

1. Retrieve and preserve the exact GW11 provider payload and its original publication/generated timestamp, capture timestamp, source URL and SHA-256.
2. Preserve the matching official FPL bootstrap/player metadata snapshot and its provenance.
3. Normalize the forecast into the canonical player-level expected-points contract. If the provider publishes fixture-grain rows, retain those rows and apply only the provider-documented aggregation to player-Gameweek grain.
4. Validate provider identity, product/variant registration, official FPL element IDs, target Gameweek, deadline, timestamps, coverage and raw hashes.
5. Assemble a manager-context fixture explicitly labelled as historical/rehearsal input. Do not substitute today's squad, bank or free-transfer state into a historical decision.
6. Run the existing personal-squad engine and M4 product adapter using the same source-independent contract intended for both conventional and future CTA-FPL forecasts.
7. Preserve the output as a non-release rehearsal artifact. It must not be presented as a live recommendation or used to make a GW12 transfer.

## Source and evidence rules

- Sideline Quant's published GW11 endpoint is a candidate historical forecast source. The published GW11 payload must be retrieved and archived before claiming a real-data replay; synthetic tests do not count as retrieval of that payload.
- GW12 availability must not be inferred from the GW11 endpoint. Do not retry the known-unpublished Sideline Quant GW12 endpoint.
- A missing generated timestamp, incomplete player coverage, failed identity gate or unverified manager context must remain an explicit limitation; never backdate or silently fill missing evidence.
- No cross-provider blending. One run uses one registered provider product/variant.
- CoVar remains research-only and excluded from conventional expected-points decisions. Field-relative EO/exposure is contextual only and cannot alter the conventional transfer/lineup score.

## Reuse when GW12 becomes available

Replace the historical GW11 forecast input with the eligible GW12 forecast snapshot and the user's then-current, deadline-valid manager state. Keep the same canonical forecast contract, M4 engine, squad constraints and product adapter. Retain the provider/model label so conventional and CTA-FPL runs remain separate and comparable.

## Acceptance criteria

- The run records target_gameweek 11 and a historical/rehearsal designation.
- Source payload, metadata payload, hashes, timestamps and provider identity are traceable.
- The manager state is explicitly historical or the run is limited to a pipeline-only synthetic fixture; no stale state is represented as current.
- M3 normalization, M4 recommendation contract and product adapter execute without provider blending.
- Output remains EXPLORATORY_PREVIEW and release_eligible false.
- A GW12 rerun requires a fresh GW12 forecast and current manager state; GW11 output is never relabelled as GW12.
