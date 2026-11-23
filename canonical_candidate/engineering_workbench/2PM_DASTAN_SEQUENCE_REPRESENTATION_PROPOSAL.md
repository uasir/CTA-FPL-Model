# 2PM — Dastan 286-Feature Sequence Representation Proposal

**Date:** 2026-11-23  
**Status:** Recommended adaptation design; not yet frozen or implemented  
**Governing references:** Published 2PM Transformer paper; `2PM_DASTAN_286_FEATURE_ADAPTATION_DECISION.md`; `2PM_DASTAN_SOURCE_SEMANTICS_AUDIT.md`.

## 1. Problem

The paper's input is five consecutive matches actually played by a player, represented by 116 features per match. Dastan's 286 columns are not raw match statistics. They are engineered player-fixture snapshots, mostly rolling histories and pre-deadline context.

Therefore, the 286-feature row cannot simply replace one 116-feature match vector without defining what each token means.

## 2. Recommended adaptation

Use a **six-token encoder input**:

- Tokens 1–5: the five most recent eligible previous player fixtures in which the player actually played (minutes > 0), ordered chronologically. Each token is the 286-feature Dastan-style vector that was available at the official FPL deadline for that historical fixture's Gameweek.
- Token 6: the current target-fixture query vector, containing the 286 Dastan-style features available at the target Gameweek's official deadline.

Tensor shape:

`[batch, sequence=6, features=286]`

The model reads the final target-query token's encoder representation and predicts the target fixture's player FPL points through the paper's two-component Poisson-mixture head.

This is a clearly labelled adaptation: five historical played-fixture snapshots plus a current target-context token. It is not the paper's original five-token/116-feature input contract.

## 3. Why use a target-query token

The current target fixture has information not present in the five historical fixture rows: its opponent, home/away status, target-date context, and deadline-specific market/availability snapshot. A dedicated target token keeps that context aligned with the prediction being made.

It also gives the Transformer a consistent representation:
- historical tokens represent the pre-match state at each of the five previous played fixtures;
- the target token represents the pre-match state at the fixture being forecast;
- every token uses the same ordered 286-feature schema.

No target outcome or post-deadline data may enter any token.

## 4. Played-match selection

- Select actual previous player fixtures using fixture-level FPL history and `minutes > 0`; calendar Gameweeks are not observations.
- A double Gameweek can contribute two previous played fixtures if the player played in both.
- A blank Gameweek contributes no played-match token.
- Order by actual kickoff timestamp, with fixture ID as a deterministic tie-break.
- Preserve the paper's maximum 21-day gap between selected observations. The exact interpretation of whether the target fixture is included in that gap check must be pinned from the paper/source implementation before the sequence builder is frozen.
- Default to requiring five eligible previous played fixtures; do not silently pad or replace missing observations with calendar-week rows. Any cold-start/padding adaptation requires a separate decision and evaluation.
- Do not cross player identities when constructing sequences. Use corrected, versioned player mapping and explicit transfer/alias handling.

## 5. Point-in-time semantics

Every historical token must be reconstructed using only information available at that historical Gameweek's official deadline. The target token must use only information available at the target Gameweek's official deadline.

The timestamp is the FPL deadline, not the fixture kickoff. In particular:
- opponent rolling features must be recomputed using opponent matches completed before that Gameweek deadline;
- own-team rolling features and ranks must be reconstructed as of the same deadline;
- defensive-allowance, congestion and rest features must not incorporate any post-deadline match;
- price, selected percentage, transfer balance, `ep_next` and availability signals must use archived pre-deadline snapshots;
- target fixture identity/context may vary by fixture, but its historical form values must be deadline-safe.

The current upstream Dastan frame has a structural deadline-guarantee gap documented in `2PM_DASTAN_SOURCE_SEMANTICS_AUDIT.md`. Do not construct these tokens from its released feature rows until the independent event-level deadline reconstruction is complete or the affected features are rebuilt safely.

## 6. Double Gameweeks and same-deadline tokens

When the player played in two fixtures in one Gameweek, both can appear among the five previous played fixtures. Both historical tokens are built from the same deadline-safe history snapshot for that Gameweek, while retaining their respective target fixture context (opponent and home/away).

The second fixture's token must not see the first fixture's result: both fixtures were locked at the same deadline. The first fixture's result becomes available only to a later Gameweek token whose deadline occurs after that match was completed.

For the current target Gameweek, a player with two target fixtures has two target-fixture prediction examples (one target query token per fixture), with the same common deadline history and fixture-specific context. M4 can aggregate the two fixture-level forecasts into the player-Gameweek decision view.

## 7. Leakage and label separation

- The target fixture's `total_points`, minutes, goals, assists, bonus, cards and other outcome fields are labels or evaluation metadata only.
- For a historical token, that historical fixture's own outcome is not available in its pre-match vector. It may affect later tokens only after the result is completed and available by the later token's deadline.
- Never use the target fixture's outcome to update rolling features before prediction.
- Never allow a later fixture's result from the same Gameweek into an earlier/common deadline snapshot.
- Fit all imputers, scalers, encoders and transformations on chronological training data only.
- Preserve missingness and unavailable-source semantics; do not collapse missing into genuine zero.

## 8. Trade-offs and required checks

This design has an important limitation: each historical token is a pre-match snapshot, not a post-match event vector. The latest target token's rolling Dastan features already summarise much of the player's prior history. The five historical tokens therefore add a trajectory of prior contexts, but also introduce redundancy.

Before accepting this design:
1. Verify the paper's precise five-match/21-day eligibility interpretation.
2. Rebuild all 286 feature families as deadline-safe historical snapshots.
3. Verify that each previous played fixture has one and only one valid token row.
4. Quantify repeated/identical token vectors in double Gameweeks.
5. Measure missing-token and player-identity coverage by season.
6. Confirm that the target token contains only target context and completed pre-deadline history.
7. After implementation, compare against a 286-feature target-snapshot baseline and a sequence ablation using the same chronological splits. This is a later model evaluation, not a reason to tune before the data gates pass.

## 9. Alternatives not selected as the default

- **One 286-feature vector only:** simple and naturally matches Dastan's target-fixture grain, but discards the paper's temporal sequence design.
- **Five historical rows only, no target token:** omits target-specific opponent, home/away and deadline context from the prediction input.
- **Five post-match state vectors:** potentially closer to event-observation semantics, but would require a newly defined 286-feature post-match schema and would no longer be a direct use of the Dastan deadline-snapshot contract.
- **Six calendar Gameweek rows:** invalid because blank Gameweeks are not played matches and double Gameweeks can contain two actual matches.

## 10. Decision requested before sequence implementation

This is the recommended design for the Dastan-input adaptation, but it remains a proposal until:
- the paper's gap rule is checked precisely;
- the deadline-safe 286-feature rebuild is established;
- feature admission and sequence coverage are measured.

No sequence builder or model code is authorized by this proposal.
