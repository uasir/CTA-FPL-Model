# Provider-specific player identity crosswalks

Date: 2026-11-18

## Decision

Keep provider identifiers in separate namespaces. Do not merge Wyscout `wyId`, Opta/PulseLive `playerId`, and StatsBomb player IDs. The FPL-side anchor is the season-specific official FPL `element` ID; retain `player_code` as an additional source identifier.

Two independent crosswalk templates are provided:

- `data/wyscout_fpl_identity_crosswalk.csv` — Wyscout 2017/18 Premier League to FPL 2017/18.
- `data/opta_pulselive_fpl_identity_crosswalk.csv` — Opta/PulseLive 2026/27 Premier League to FPL 2026/27.

The existing `data/player_identity_crosswalk.csv` remains the StatsBomb-specific crosswalk and is not repurposed.

## Verification policy

A row may be marked `verified` only when all of the following are evidenced for the same season and competition:

1. Provider numeric player ID and FPL `element`/`player_code` are present.
2. Provider and FPL team IDs/names reconcile for the relevant season or match appearance; current-team fields alone are insufficient for historical seasons.
3. Evidence source and a retrievable HTTP(S) evidence URL are recorded.
4. Reviewer and verification date are recorded.
5. The mapping is one-to-one within `(season, provider_player_id)` and `(season, fpl_element_id)`.

Permitted verification methods: `provider_id_crosswalk`, `official_alias`, `club_roster_crosscheck`, `manual_source_verified`. Name normalization can generate candidates only; it cannot verify a mapping. No fuzzy-name matching is permitted.

Use `pending`, `ambiguous`, or `rejected` for non-verified rows. Never insert fabricated or example player records into production crosswalks.

## Current evidence and blockers

### Wyscout 2017/18

The preliminary source audit identified 303 exact normalized full-name candidates among 442 Wyscout records currently associated with Premier League clubs. These are not verified joins. The official Wyscout player/match files still need full reconciliation, and FPL historical target-data reuse rights remain unresolved. Therefore the Wyscout crosswalk is intentionally header-only.

### Opta/PulseLive 2026/27

The preliminary source audit found 511 shared player IDs between the inspected FPL and provider season files, with matching team IDs for all 511. These are strong technical candidates, but the provider's numeric ID namespace must remain explicitly labelled Opta/PulseLive. Underlying data-use and redistribution rights are not cleared. Therefore this crosswalk is also intentionally header-only pending permission and reproducible source ingestion.

## Integration rule

Provider adapters must emit canonical player records with `provider`, `provider_player_id`, `season`, and `fpl_element_id` as explicit fields. Join downstream only on a verified season-scoped mapping. Keep provider feature families and provenance separate; an Opta/PulseLive ID is never a StatsBomb ID.

## Validation

Run:

```bash
python canonical_candidate/engineering_workbench/scripts/validate_provider_identity_crosswalk.py --provider wyscout --input canonical_candidate/data/wyscout_fpl_identity_crosswalk.csv --out-dir run_artifacts/wyscout_identity
python canonical_candidate/engineering_workbench/scripts/validate_provider_identity_crosswalk.py --provider opta_pulselive --input canonical_candidate/data/opta_pulselive_fpl_identity_crosswalk.csv --out-dir run_artifacts/opta_identity
```

An empty template returns `EMPTY_NOT_READY`; it is not a successful join. Invalid or conflicting verified rows return `BLOCKED`.
