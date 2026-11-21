# GW11 manager-action annotation

**Status:** User-attested pre-deadline transaction; player IDs mapped against a public 2026/27 FPL player register. Exact execution timestamp and official transfer-history confirmation remain unavailable.

## Frozen GW11 recommendation and archived state

- Manager: FPL entry 421025
- Target: GW11
- Decision/evidence captured: 2026-11-20T20:14:42.975478Z
- Deadline: 2026-11-21T11:00:00Z
- Archived manager-state squad included player 229 and did not include players 504 or 112.
- Archived manager-state snapshot: 1 free transfer; bank £0.9m.
- Frozen recommendation: player 229 out, player 112 in.
- Frozen decision SHA-256: `25286ed37076d247a0839190394ec5d8258119bb669362b2aa5c5cba1195d49f`

## Manager-reported action and identity mapping

The manager confirmed that the following transaction was executed **after the archived snapshot and before the GW11 deadline**:

- James Tarkowski out — FPL player ID 229
- Luka Vušković in — FPL player ID 504

The 2026/27 Premier League GW10 FPL player register maps ID 229 to James Tarkowski, ID 504 to Luka Vušković, and ID 112 to Jan Paul van Hecke:
https://github.com/olbauday/FPL-Core-Insights/blob/main/data/2026-2027/By%20Tournament/Premier%20League/GW10/players.csv

Therefore, the reported manager action is **229 out / 504 in**, while the frozen conventional recommendation was **229 out / 112 in**. The outgoing player matches; the incoming player differs. This is recorded as a user-attested pre-deadline deviation from the frozen recommendation, not as execution of the recommended transfer.

The archived snapshot predates the reported action, which explains why it still contains player 229 and does not contain player 504. The exact transaction timestamp and official FPL transfer-history record have not been independently retrieved.

## Evaluation treatment

- Preserve the frozen GW11 recommendation, original squad snapshot and decision hash unchanged.
- Preserve 229 out / 504 in as a separate, user-attested GW11 manager action.
- Record recommendation adherence as a partial match on the outgoing player and a mismatch on the incoming player; do not label the recommended transfer as executed.
- Do not infer final bank, free transfers, hit cost, or complete post-transfer squad until the official transfer history or a fresh manager-state snapshot is available.
- Refresh the live manager squad before using it for later-Gameweek recommendations.

This annotation is descriptive evidence only. It does not change expected points, recommendation legality, EV/EO separation, CoVar status, or release eligibility.
