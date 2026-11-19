# 11footy historical-to-current FPL identity evidence

Status: **CANDIDATE CROSS-SEASON CORROBORATION / NO AUTOMATIC VERIFICATION**

## Scope

This pipeline checks whether 11footy provider identities can be corroborated against historical FPL records and then linked, by the same canonical 11footy provider ID, to current 2026/27 FPL candidate mappings.

It uses:
- 11footy release `11footy-2026-11-10`, including the historical EPL match database and player catalogue.
- Vaastav Anand's historical FPL archive pinned to commit `d7b05b51d137bfefef4b692386d18c610975b9b9`.
- The current official FPL `bootstrap-static` response captured during the workflow.
- The 11footy `player_merges` map to canonicalize historical provider IDs before joining current candidates.

## 2017/18 historical identity results

The real-data run produced:
- 602 canonical 11footy players with match records.
- 647 historical FPL player records.
- 543 unique exact-normalized-full-name candidates; zero ambiguous exact-name matches and 59 unmatched.
- 380/380 historical EPL matches mapped to FPL fixtures using exact UTC date, opponent and home/away context.
- 12,291 11footy player-match rows joined to historical FPL player-fixture rows.
- Zero duplicate FPL player-fixture keys and zero duplicate provider merge keys.

Review priorities:
- P1: 356 candidates with exact minutes/goals/own-goals/assists signatures across at least three matches and team corroboration.
- P2: 66 candidates with at least one exact full signature and team corroboration.
- P3: 121 historical candidates requiring further review.
- P5: 59 unmatched identities.

All candidates remain PENDING. These statistics are corroborating evidence, not proof.

## Cross-season link to current 2026/27 FPL

The same workflow generated current candidates from the 11footy player catalogue and official FPL bootstrap:
- 672 current FPL players.
- 490 exact normalized-name/team candidates.
- 340 high-confidence exact name/team/birth-date candidates.
- 150 candidates with one or both birth dates unavailable.
- Two birth-date conflicts excluded.
- One ambiguous name/identity case.

Cross-season join by canonical 11footy provider ID:
- 49 provider IDs overlap between historical 2017/18 player records and current candidate mappings.
- 46 of those have a current high-confidence FPL candidate.
- 30 are P1: historical multi-match signature corroboration plus a current high-confidence name/team/birth-date candidate.
- Five are P2: historical full-signature corroboration plus current high-confidence candidate, but below the P1 historical threshold.
- Eleven are P3: current high-confidence candidate with weaker historical match evidence.
- Two have P1 historical evidence but only a current review-required candidate.
- The remaining historical IDs are historical-only, unmatched or have no current candidate.

The 30 P1 cross-season cases are the highest-priority manual review subset. They are **not verified identities** and must not enter the canonical verified crosswalk until independent identity evidence is recorded.

## Safeguards and limitations

- Candidate mappings are exact-name based; no fuzzy name matching is used.
- Team, birth date and match-stat agreement are evidence, not proof.
- Historical FPL data contains no birth date, so the historical join cannot independently validate DOB.
- Current high confidence is an automated evidence grade, not human verification.
- Player-level candidate CSVs remain inside the Actions runner. Only aggregate reports and source hashes are uploaded.
- The canonical `11footy_fpl_identity_crosswalk.csv` remains unchanged.
- Historical FPL archive data may contain retrospective corrections; it is used for identity corroboration only, not point-in-time prediction training.
- 11footy data is CC BY-NC 4.0 and restricted to non-commercial use. The Vaastav repository's MIT code licence does not grant rights to underlying FPL data, which remains property of Fantasy Premier League.
- No commercial reuse rights are claimed.
- Predictive validation remains NOT_EVALUATED.

## Next steps

1. Independently verify the 30 P1 cross-season candidates first, using authoritative player profiles or another reliable identifier.
2. Review the five P2 candidates and eleven P3 candidates next.
3. Record source, evidence, reviewer, verification date and confidence in a season-scoped crosswalk.
4. Only then use verified IDs in the common player-match layer; keep all other records isolated.
5. Repeat the process on additional historical seasons to increase coverage without weakening the verification standard.
