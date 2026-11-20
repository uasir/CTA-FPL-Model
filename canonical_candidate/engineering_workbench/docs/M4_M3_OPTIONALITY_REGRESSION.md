# M4-T7 — M3 optionality and regression boundary

`scripts/m4_m3_optionality_adapter.py` verifies the frozen M3 decision hash and
the duplicate decision embedded in the M3 `evaluation_candidate`. It attaches
M4 only as a separate descriptive context after checking exact manager, season,
Gameweek, deadline, decision hash, original squad and hold-lineup identity.

A field snapshot must predate the M3 decision timestamp, not merely the
Gameweek deadline. M4 is withheld when absent, stale, incomplete, mismatched,
or ineligible. The wrapper returns the M3 output unchanged in all these modes.
It does not alter provider xP, legality, recommendation status or transfer.

M4 context must remain non-release-eligible, keep EV and EO separate, and keep
CoVar disabled. This wrapper is an audit/integration boundary, not a new M3
recommendation engine or production release path.
