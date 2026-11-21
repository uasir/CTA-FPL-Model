# GW11 manager-action annotation

**Status:** User-attested transaction; execution timestamp and Gameweek attribution not independently verified.

## Frozen GW11 recommendation

The archived GW11 conventional decision remains immutable:

- Manager: FPL entry 421025
- Target: GW11
- Decision captured: 2026-11-20T20:14:42.975478Z
- Deadline: 2026-11-21T11:00:00Z
- Frozen action: transfer player 229 out, player 112 in
- Frozen decision SHA-256: `25286ed37076d247a0839190394ec5d8258119bb669362b2aa5c5cba1195d49f`

## Manager-reported action

In a conversation message sent at 2026-11-21T18:47:46Z, the manager reported:

- Tarkowski out
- Vuskovic in

The message timestamp is after the GW11 deadline, but it is only the time the transaction was reported to the project. It does **not** establish when the FPL transfer was actually executed. Therefore, this annotation does not classify the move as a GW11 or GW12 transaction and does not map player IDs without an independently verified transaction record.

## Evaluation treatment

- Preserve the frozen GW11 recommendation and its decision hash unchanged.
- Preserve the manager-reported action as a separate, user-attested observation.
- Do not claim that the manager followed or rejected the frozen recommendation until the transaction timestamp and player IDs are verified.
- Refresh the live manager squad and transfer history before using this move as the current squad state for a later Gameweek recommendation.
- Do not infer bank, free transfers, hit cost, or the remaining 15-player squad from this single reported transaction.

This annotation is descriptive evidence only. It does not change expected points, recommendation legality, EV/EO separation, CoVar status, or release eligibility.
