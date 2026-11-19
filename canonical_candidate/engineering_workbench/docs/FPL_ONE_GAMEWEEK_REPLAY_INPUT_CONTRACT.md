# FPL One-Gameweek Decision Replay Input Contract

Status: **EXPLORATORY ENGINE IMPLEMENTED / HISTORICAL DATASET NOT YET ASSEMBLED / RULE PARITY VALIDATION REQUIRED**

Implementation:
- `scripts/replay_fpl_gameweek_decisions.py`
- `tests/test_replay_fpl_gameweek_decisions.py`

## Purpose and scope

The replay engine scores frozen manager decisions against official player outcomes and compares policies on matched starting states. It is a one-gameweek evaluator, not yet a sequential season simulator or an optimizer.

It intentionally requires an upstream `action_legality_verified=true` flag. It does not claim to validate transfer affordability, selling prices, team limits after real-world club transfers, chip availability, or the historical squad transition. A used chip additionally requires `chip_legality_verified=true`.

## Input JSON

Top-level object:

```json
{
  "baseline_policy": "hold",
  "rows": [
    {
      "deadline_id": "2026-27_GW01",
      "starting_state_id": "manager-state-hash-or-stable-id",
      "policy": "hold",
      "decision_frozen_at": "2026-08-14T16:00:00Z",
      "deadline_at": "2026-08-14T17:30:00Z",
      "decision": {
        "action_legality_verified": true,
        "starting_xi": ["FPL_ELEMENT_ID_1"],
        "bench_order": ["FPL_ELEMENT_ID_12", "FPL_ELEMENT_ID_13", "FPL_ELEMENT_ID_14", "FPL_ELEMENT_ID_15"],
        "captain": "FPL_ELEMENT_ID_1",
        "vice_captain": "FPL_ELEMENT_ID_2",
        "transfers_made": 0,
        "free_transfers": 1,
        "chip": null
      },
      "official_points": {"FPL_ELEMENT_ID_1": 8},
      "minutes": {"FPL_ELEMENT_ID_1": 90},
      "positions": {"FPL_ELEMENT_ID_1": "FWD"},
      "team_by_player": {"FPL_ELEMENT_ID_1": "TEAM_ID"},
      "played_by_player": {"FPL_ELEMENT_ID_1": true}
    }
  ]
}
```

The example is schematic: a real row must contain the complete 15-player roster and complete outcome, minutes and position maps for all 15 players. IDs in maps may be JSON strings.

Required row fields:
- `deadline_id`, `starting_state_id`, `policy`.
- `decision_frozen_at` and `deadline_at`, both timezone-aware ISO-8601 timestamps, with the frozen decision strictly earlier than the deadline.
- `decision`, `official_points`, `minutes`, `positions`.

Decision fields:
- Exactly 11 distinct starting players and four distinct bench players, forming a legal 15-player squad (2 GKP, 5 DEF, 5 MID, 3 FWD).
- One goalkeeper in the XI; legal outfield formation; three outfield bench players followed by the reserve goalkeeper.
- Distinct captain and vice-captain, both in the starting XI.
- Transfer count and free-transfer count; optional chip.
- Explicit upstream legality verification flags.

Optional outcome/context fields:
- `team_by_player`: if supplied, the engine checks the three-per-team limit.
- `played_by_player`: explicit FPL appearance status. If absent, the engine uses minutes > 0. Supply it when official event records show a card/appearance that means a player counts as having played despite zero recorded minutes.

## Implemented scoring

- Starting XI official player points.
- Goalkeeper replacement when the starting goalkeeper does not play and reserve goalkeeper does.
- Outfield autosubs in bench priority order, only when the resulting formation is legal.
- Vice-captain fallback when the selected captain has no Gameweek appearance.
- Triple Captain bonus, including its transfer to the vice-captain when the selected captain does not play.
- Bench Boost inclusion of all four substitutes.
- Four-point hits for transfers beyond the available free transfers; Wildcard and Free Hit waive transfer hits for that Gameweek.

The scorer uses official total points as supplied; it does not reconstruct goals, assists, clean sheets, bonus or defensive-contribution scoring from raw events.

Official rule references:
- [Fantasy Premier League Help and FAQs](https://fantasy.premierleague.com/help/faqs) — captain/vice, chips, transfer deductions, appearances and automatic substitutions.
- [Premier League: FPL basics — managing your team](https://www.premierleague.com/en/news/2174899/fpl-basics-managing-your-team) — lineup, bench priority and formation rules.
- [Premier League: 2026/27 FPL chips](https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627) — current-season chip effects.

## Paired policy comparison

For each deadline, include the same policy set (for example `hold`, `conventional`, `cta_informed`) and the same `starting_state_id`. Each policy may submit a different frozen action, but all actions are evaluated against the same official outcome maps.

The evaluator rejects:
- missing or duplicated policies within a deadline;
- different policy sets across deadlines;
- mismatched starting-state IDs;
- missing or post-deadline decision timestamps;
- invalid lineups or unverified actions/chips.

Outputs include per-policy net points, mean and total delta versus the baseline, and the proportion of deadlines won/lost/tied against the baseline.

## Important interpretation limits

- This is **one-step realized decision value**, not sequential policy value.
- It does not yet transition squad, bank, purchase prices, free transfers, chips or Free Hit restoration to the next deadline.
- It does not calculate rank gain or field-relative points.
- Regret against a shortlist is not global feasible-set regret.
- Timestamp ordering does not independently prove that all source data were available at the deadline.
- The current tests are synthetic unit tests. Before historical performance claims, validate replay scores against known official FPL team histories and autosub/chip examples, then assemble a point-in-time historical decision archive.
- No decision strategy is claimed to outperform another until a matched chronological evaluation is completed.
