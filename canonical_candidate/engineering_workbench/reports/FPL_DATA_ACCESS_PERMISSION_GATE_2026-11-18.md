# FPL data access permission gate

Updated: 2026-11-18

The official Fantasy Premier League terms state that users must not use automated systems to access the Game and extract information, and reserve intellectual-property rights in Game data. A publicly reachable API endpoint is not, by itself, a data licence.

Before the project resumes automated FPL API extraction, obtain written permission from the Premier League/FPL rights holder that covers the intended research use, automated collection, private archival storage, historical snapshots, and any planned redistribution or publication.

The Premier League's published data-contact guidance directs match-data permissions to Football DataCo. Opta/PulseLive event data must not be ingested or redistributed until the appropriate provider/data rights are cleared.

## Technical enforcement

The following GitHub Actions jobs are gated:
- `.github/workflows/cta-fpl-ingestion.yml`
- `.github/workflows/cta-fpl-eo-capture.yml`
- `.github/workflows/cta-onside-benchmark.yml` (its independent reconciliation calls official FPL endpoints)

The jobs run only when the repository Actions variable `FPL_DATA_PERMISSION_CONFIRMED` is exactly `true`.

Do not set this variable based only on public API accessibility, personal use, or an assumption that non-commercial research is exempt. Set it only after written permission is received and reviewed for the intended scope.

Offline unit tests, source-code work, local processing of already-authorized datasets, and the separately licensed Wyscout CC BY 4.0 event dataset may continue subject to their own licence and attribution requirements.

This note is an engineering safeguard, not legal advice.
