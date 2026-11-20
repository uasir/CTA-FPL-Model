# FPL Sequential Manager-State Transition Contract

Status: **STATE-TRANSITION MODULE IMPLEMENTED; UNIT/CI VALIDATION PENDING; NOT YET INTEGRATED WITH MULTI-GAMEWEEK SCORING**

Implementation:
- scripts/transition_fpl_manager_state.py
- tests/test_transition_fpl_manager_state.py

## Purpose

This module advances one manager-policy trajectory from one FPL deadline to the next. It is deliberately separate from the one-Gameweek scoring engine. It does not generate recommendations, predict points, calculate rank gain or choose an optimal action.

The current paired one-step evaluator compares policies on the same manager state at each deadline. A sequential evaluation is different: all policies start from the same initial manager state, then each policy's own transfers, bank, squad, free transfers and chip inventory evolve independently. At later deadlines, each policy may therefore have a different starting state. Do not force the sequential trajectories back onto the same real-manager state after the initial deadline.

## Inputs

The transition function receives:

- Current state: season, Gameweek, timezone-aware deadline, bank in tenths of a million, free-transfer count, two-period chip inventory and the exact 15-player squad.
- Frozen action: outgoing player ID and incoming player record for each transfer, starting XI, ordered bench, captain, vice-captain and optional chip.
- Next-deadline market snapshot: current price and Premier League team ID for every player who will remain in the next squad.
- Immediately following Gameweek number and deadline timestamp.

Player records carry player ID, position, Premier League team ID, purchase price, current price and selling price, all prices represented in tenths of £m.

## Implemented transition rules

- Squad remains exactly 15 players with 2 GKP, 5 DEF, 5 MID and 3 FWD.
- Transfers are one-for-one and position-matched.
- Budget arithmetic uses the recorded selling price of outgoing players and the pre-deadline current price of incoming players.
- Selling price is independently checked against the official rule: if current price exceeds purchase price, the manager retains half the rise, rounded down to the nearest £0.1m; otherwise the selling price is the current price.
- The resulting Gameweek squad must remain within budget.
- Any transfer action must leave no more than three players from any Premier League club. An existing over-three exception can be carried forward without transfers, matching the official exception for real-world club transfers.
- Normal free-transfer rollover is min(5, max(1, free_transfers - transfers_made + 1)).
- Wildcard and Free Hit preserve the manager's previously banked free-transfer count; they do not add another free transfer for the chip Gameweek.
- Wildcard transfers are permanent and do not incur hits.
- Free Hit transfers are used for the current Gameweek only; the original squad and bank are restored for the next deadline. The chip is consumed.
- Bench Boost and Triple Captain consume their respective half-season chip but do not alter squad persistence.
- One chip can be used in a Gameweek; the inventory is tracked separately for GW1–19 and GW20 onward.
- Free Hit is rejected in GW1 and cannot be used in both GW19 and GW20 consecutively.

## Outputs

The result separates:
- gameweek_squad and gameweek_lineup: the squad and lineup that should be scored for the current Gameweek;
- next_state: the permanent squad, bank, free transfers, updated player prices/selling prices, chip inventory and transfer history for the next deadline;
- transfer-hit points and budget/free-transfer diagnostics.

For Free Hit, gameweek_squad is the temporary squad while next_state.squad is restored to the original squad. For other actions, the resulting squad persists.

## Deliberate boundaries

- This is a single state transition, not yet a complete season policy runner.
- The module does not score the Gameweek. Feed the returned Gameweek squad/lineup into the separately validated one-Gameweek scorer with official points, minutes, positions and played status.
- It assumes incoming transfer prices, current squad prices and next-deadline market prices are supplied from point-in-time snapshots. It does not query FPL or infer missing prices.
- It does not independently verify that a transfer action was frozen before the deadline; the archive validator must verify chronology and source hashes.
- It does not yet handle manager deletion, team merges, postponed/cancelled Gameweeks, mid-season rule changes or unmodeled special transfer adjustments.
- It does not yet construct policy trajectories from frozen forecasts. A separate policy runner must apply each policy to its own current state at each deadline.
- Sequential results must be compared from a shared initial state and identical official outcomes, with paired uncertainty clustered by manager trajectory.

## Official 2026/27 rule references

- [Fantasy Premier League Help and FAQs](https://fantasy.premierleague.com/help/faqs): free-transfer rollover and five-transfer cap; Wildcard/Free Hit preservation of saved transfers; selling-price calculation; temporary over-three club exceptions.
- [Premier League: What’s happening with FPL chips in 2026/27](https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627): two sets of chips, half-season reset, Free Hit restoration and the GW19/GW20 Free Hit restriction.

## Required validation before decision-value use

1. Unit tests for transfer budget, price changes, selling price, free-transfer rollover, chips, Free Hit restoration and team-limit exceptions.
2. CI pass on the public working branch.
3. Cross-check a sample of actual official manager histories across normal transfers, Wildcard and Free Hit, including bank and free-transfer balances at consecutive deadlines.
4. Validate each transition against a point-in-time manager-state archive.
5. Only then integrate the transition with scoring and policy execution for multi-Gameweek paired replay.
