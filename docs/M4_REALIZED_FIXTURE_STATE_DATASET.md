# Official FPL realized fixture-state dataset

## Purpose

Build the match-level realized scoreline panel required by the M3-anchored
CoVar scenario model. This uses the existing official FPL ingestion source;
it does not introduce another forecast provider and does not predict scores.

## Outputs

- Player-independent fixture rows: fixture ID, Gameweek, kickoff, home/away
  team IDs, home/away goals, total goals, goal difference, result and the
  official finished_provisional flag.
- Gameweek summaries: fixture count, home/away/total goals, home wins, draws
  and away wins.
- A report with input/output hashes, Gameweek coverage and finality limitations.

## Integrity and privacy

The builder requires a passing official ingestion report, matching season
metadata and a fixture-object hash matching source_metadata.json. It preserves
finished_provisional rather than silently treating provisional scores as final.
Output is created only in a new directory outside a Git checkout, with 0700
directory and 0600 file permissions.

## Statistical boundary

This is realized historical data, not a forecast. It does not estimate scoreline
probabilities, player outcomes, or cross-fixture dependence. Provisional fixture
scores still require official event-live finality reconciliation. Retrospective
source capture does not authenticate historical point-in-time availability.
Decision weight remains zero and production eligibility false.
