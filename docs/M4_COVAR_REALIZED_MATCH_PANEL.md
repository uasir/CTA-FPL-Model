# CoVar realized player-fixture match panel

This component joins the existing official FPL player-fixture outcome panel to
the newly added official fixture scoreline panel. It joins on season and exact
fixture ID, then checks Gameweek, home/away team orientation and the
finished_provisional flag before attaching home/away goals and match result to
each player-fixture observation.

The output is a private research dataset. It preserves the upstream provisional
finality marker and explicitly states that finality is inherited from the
separate official event-live audit; this join does not re-run or authenticate
that audit. The current panel remains retrospective, not a point-in-time
forecast archive.

No scoreline probabilities, player probabilities, or fixture-independence
assumptions are introduced. Decision weight remains zero and production
eligibility false.
