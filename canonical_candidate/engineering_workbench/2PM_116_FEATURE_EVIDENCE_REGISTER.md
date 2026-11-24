# 2PM Transformer — 116-Feature Evidence Register

**Date:** 2026-11-23  
**Branch:** `feat/four-layer-2pm-transformer-evaluation`  
**Status:** Evidence register / not a model schema / data gate remains blocked  
**Governing source:** Wiechno, Duch and Bartosik (2026), *Modeling Fantasy Premier League Player Performance with a Two-Component Poisson Mixture Transformer*, ICAART 2026, DOI: 10.5220/0014358000004052.

## 1. Purpose and decision

This register records what can currently be established about the paper's 116 per-match inputs and what the audited project sources can support. It is deliberately **not** a proposed 116-column schema.

The publisher's paper record, full paper/PDF, conference listing and author institutional publication records were searched. No public author supplement, complete 116-column dictionary or companion implementation was located in those sources. The paper states that there are 116 features and names feature families, but does not enumerate all 116 columns in the accessible publication.

**Decision:** do not create 116 guessed columns, do not pad a shorter list with arbitrary variants, and do not describe any reconstructed schema as an exact reproduction. Seek author clarification/supplementary material first. If unavailable, produce a separately versioned, source-backed adaptation with every field documented.

## 2. What the paper actually confirms

The paper explicitly describes a 116-feature vector for each player-match observation. Its prose names the following feature families/examples:

- Minutes on the pitch and player position.
- Goals, assists, penalty kicks made/scored, yellow cards, red cards and own goals.
- Shot saves / goalkeeper saves.
- Defensive actions: tackles, blocks, clearances and interceptions.
- Passing types.
- Shot-creating and goal-creating actions.
- Save percentage.

The paper does **not** disclose the complete field names, exact operational definitions, units, aggregation conventions, missing-value semantics, or provider/source lineage for all 116 features in the accessible text. The above list is therefore a set of paper-confirmed concepts, not a complete list and not 116 distinct variables.

## 3. Audited source coverage — known facts only

### 3.1 Official FPL player-fixture history

Inspected source: `scripts/fetch_fpl_official_api.py`.

The adapter emits one player-fixture history row and preserves these match-level fields:

- Minutes and total FPL points.
- Goals, assists, clean sheets, goals conceded, own goals.
- Penalties saved and missed.
- Yellow and red cards.
- Goalkeeper saves.
- Bonus and BPS.
- Influence, creativity, threat and ICT index.
- Starts.
- Expected goals, expected assists, expected goal involvements and expected goals conceded.
- Selection, transfers and player value.

This is valuable for FPL outcome labels and overlapping match-level fields. It does not establish availability of the paper's full set of passing-type, shot-/goal-creating-action, tackle, block, clearance, interception and save-percentage fields. FPL fields such as bonus/BPS and ICT are not substitutes for those event-level action definitions.

The adapter's current API snapshots also do not by themselves prove that historical values were available before each historical deadline. Snapshot/vintage provenance must be independently established.

### 3.2 Wyscout EPL 2017/18 event data

Inspected source: `scripts/build_wyscout_cta_player_match_features.py` and `docs/WYSCOUT_CTA_INTEGRATION.md`.

The existing research adapter constructs provider-native player-match counts for:

- Pass attempts/completions.
- Key, smart, through and opportunity passes.
- Progressive passes and completions.
- Final-third and provisional danger-zone entries.
- Threat-creation pass attempts/completions.
- Progressive carries.
- Shot attempts and accurate shots.
- Goals, own goals, assists and shot-opportunity tags.
- Dangerous ball losses and offsides.
- Duels, won/lost duels, ground defensive duels and aerial duels.
- Clearances, fouls and interceptions (interceptions are nullable if the relevant subtype is not observed).

Important limitations:
- These are event-derived counts and provisional geometric proxies, not tracking metrics.
- The public schema does not provide pass-recipient identity; reception cannot be assigned to the intended receiver.
- This release does not provide xG.
- The adapter does not currently expose the paper's full set of tackle/block/save-percentage definitions as a validated feature contract.
- Its output is structural research only; the historical Wyscout-to-FPL player mappings remain candidates pending independent verification.
- The Wyscout season is 2017/18, while historical FPL target rights and point-in-time vintage provenance remain unresolved.

Consequently, Wyscout is a promising event source, not yet an approved 2PM training source.

### 3.3 Opta/PulseLive integration

The prior shared-data audit found verified player-season identity mappings and team-match context, but the inspected feed did not contain player-level per-match event rows. It therefore cannot presently satisfy the 116 player-match input contract.

### 3.4 Dastan historical frame

The audited Dastan release has player-fixture rows and 286 ordered engineered rolling features across 2020/21–2025/26. Those features are deadline-anchored player/team/opponent history summaries, not 116 raw per-match observations. The frame is not a drop-in 2PM sequence input and must not be relabelled as such.

## 4. Evidence matrix by paper-confirmed concept

Status meanings:
- **Directly present:** a corresponding match-level field is present in an audited adapter; definition equivalence to the paper still requires confirmation.
- **Partial/proxy:** related event-derived information exists, but does not establish the paper's exact definition.
- **Not established:** no sufficient evidence in the audited source files.
- **Unresolved:** possible source support, but provenance, coverage, rights, identity or point-in-time status is not cleared.

| Paper-confirmed concept | Official FPL player-fixture history | Wyscout 2017/18 player-match adapter | Current conclusion |
|---|---|---|---|
| Minutes | Directly present | Not established by current output | FPL provides a match-level value; source vintage still needs clearance |
| Position | Player-season/current roster metadata, not a verified historical match-position field | Not established | Historical match-specific position unresolved |
| Goals | Directly present | Event-derived goal tags | FPL target/stat field available; Wyscout attribution has a reconciliation issue |
| Assists | Directly present | Event-derived assist tags | Wyscout event tagging is a proxy; cross-source reconciliation required |
| Penalties made/scored | Penalties missed/saved present; penalty scored not separately established in inspected match schema | Not established as a distinct penalty outcome | Incomplete |
| Yellow/red cards | Directly present | Not separately exposed in current player-match output | FPL fields present |
| Own goals | Directly present | Event-derived own-goal tags | Wyscout player attribution needs reconciliation |
| Shot saves / goalkeeper saves | Saves directly present | Not exposed as goalkeeper saves in current output | FPL field present |
| Tackles | Not established | Duel counts are not equivalent to tackles | Not established |
| Blocks | Not established | Not established | Not established |
| Clearances | Not established | Event-derived clearance counts | Partial; provider definition needs verification |
| Interceptions | Not established | Event-derived subtype count, nullable when absent | Partial; availability and subtype coverage need verification |
| Passing types | Not established as a complete action taxonomy | Several event-tag/subtype pass categories | Partial; not a full paper-equivalent dictionary |
| Shot-creating actions | Not established | Key/opportunity pass and shot counts are not equivalent to an official SCA definition | Not established as exact metric |
| Goal-creating actions | Not established | Assists and selected pass tags are not equivalent to a GCA definition | Not established as exact metric |
| Save percentage | Not established | Not established | Not established |

This matrix intentionally does not infer that a field is absent from every possible source merely because it is absent from the inspected adapter.

## 5. Mandatory feature-level record before schema freeze

Every candidate column in any future reconstructed/adapted schema must have all of the following:

1. Stable canonical feature name.
2. Exact mathematical/operational definition.
3. Paper status: explicitly named, inferred from paper category, or adaptation-only.
4. Source/provider and source version.
5. Raw source fields and transformation code/reference.
6. Unit and numeric domain.
7. Observation grain: player-match, team-match, player-season, or other.
8. Match attribution rule, including event actor/receiver semantics.
9. Availability timestamp and proof it was known before the target FPL deadline.
10. Missingness semantics: true zero, structurally inapplicable, unavailable, not collected, or unknown.
11. Coverage by season, competition, player and match.
12. Identity mapping requirements and verification status.
13. Licensing/rights status.
14. Validation/reconciliation checks and tolerance.
15. Whether the feature is directly observed or derived/proxy.

No feature may enter the frozen schema with an undocumented definition or silently coerced missing value.

## 6. Current blockers and next actions

1. **Author clarification:** request the exact 116-column dictionary, source/provider details, preprocessing rules, and any code/supplement. The public publication pages identify the authors and institutional affiliations, but no public companion schema was found.
2. **Source coverage:** once the paper dictionary is received—or the adaptation route is explicitly chosen—map every column to an approved source. Do not start with an arbitrary count of 116.
3. **Identity and rights:** resolve the Wyscout-to-FPL player crosswalk and historical FPL target-data permissions before using the 2017/18 overlap.
4. **Point-in-time integrity:** prove feature values existed by the target deadline; current retrospective API snapshots are insufficient evidence.
5. **Adaptation decision:** if exact paper schema cannot be obtained, explicitly version an adapted EPL schema and disclose which paper concepts are represented, proxied, unavailable or replaced. Do not claim exact reproduction.
6. **Only after approval:** implement the clean five-actual-match sequence dataset with the paper's 21-day gap rule. Do not import the frozen legacy 2PM sequence builder or preprocessing.

## 7. Readiness

- Exact author 116-feature schema: **NOT LOCATED / UNRESOLVED**.
- Paper-confirmed feature concepts: **DOCUMENTED**.
- Official FPL match-level overlap: **PARTIAL**.
- Wyscout event-derived overlap: **PARTIAL / RESEARCH ONLY**.
- Complete lawful, point-in-time-safe 116-feature dataset: **NOT ESTABLISHED**.
- New 2PM model implementation: **NOT STARTED**.

**Overall decision: FEATURE_SCHEMA_GATE_NOT_CLEARED.** This register is evidence and planning documentation only. It does not authorize model implementation, training, data promotion or production use.
