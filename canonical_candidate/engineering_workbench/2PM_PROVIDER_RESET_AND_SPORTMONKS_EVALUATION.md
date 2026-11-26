# 2PM — Provider Reset and Sportmonks Evaluation

**Decision date:** 2026-11-26  
**Status:** Provider candidate under evaluation; no provider selected for production acquisition  
**Scope:** Replace the 2PM external football-statistics foundation from scratch

## 1. Governing reset decision

The previous Dastan/Understat 286-feature candidate foundation is abandoned for this 2PM experiment.

This is a complete reset of the external football-statistics dataset design:
- Do not migrate, preserve, or use the 286-column Dastan/Understat feature contract as the new provider's template.
- Do not treat the prior 116- or 286-feature counts as targets.
- Do not reuse Understat-derived player/team metrics, Understat mappings, or Understat acquisition code in the new provider pipeline.
- Keep the previous Understat/Dastan work only as historical engineering records; it is not an input dependency or a migration source.
- Continue to use the 2PM model's existing architecture and player-points prediction responsibility. This decision changes the statistics-data foundation, not the Transformer or M3/M4 responsibilities.
- Official FPL data remains the source of FPL player identity, fixtures, deadline context and target labels unless a separate decision changes that.

The new dataset must be designed from the selected provider's actual statistic catalogue and verified Premier League responses. Its feature count is intentionally unset.

## 2. First provider candidate: Sportmonks Football API v3

Sportmonks is the first candidate to evaluate, not yet an approved production provider.

### 2.1 Evidence from provider documentation

The current Sportmonks documentation establishes the following capabilities:

1. A completed Premier League fixture response is advertised as containing 63 player-statistic types and 42 team-statistic types. The provider describes the player fields as including minutes, touches, passing, final-third passes, dribbles, duels, aerials, clearances, tackles, shots, goals, assists and rating.
2. Player statistics at fixture grain are returned through GET /v3/football/fixtures/{fixture_id} with include=lineups.details (and optionally .type while exploring). Each lineup detail identifies a fixture, player, team, lineup and statistic type, with the value nested under data.value.
3. Team match statistics are returned separately through include=statistics.
4. Player statistic types have stable type IDs and codes in the public catalogue. Examples include tackles (78), interceptions (100), clearances (101), key passes (117), minutes played (119), touches (120), ball recovery (27271), tackles won (27267), and passes in final third (27269). The full catalogue must be captured from the API/type reference rather than hardcoded from this short list.
5. The Premier League coverage page lists advanced player statistics, lineups, match statistics and historical data. The provider's Premier League page identifies 2025/26 as season ID 25583.
6. Sportmonks states that the depth of historical statistic types varies by league and season. Public marketing claims of 63 player-statistic types on a completed Premier League fixture do not prove that the same types exist in every historical season.

### 2.2 API acquisition shape to test

The first technical sample should use a single completed Premier League fixture and request:
- fixture identity and season;
- participants / team IDs;
- lineups and player IDs;
- lineup participation type (starter/substitute);
- lineups.details for per-player match statistics;
- statistics for team-level match statistics;
- fixture state, kickoff timestamp and last-processed timestamp.

During exploration, request statistic type metadata or retrieve the provider's type catalogue separately. For production acquisition, persist the type catalogue and use IDs/codes rather than repeatedly including verbose type objects.

The target raw grain is one player × fixture × statistic type, plus separate fixture/team-statistic records. Do not begin with a wide, manually chosen feature matrix. First preserve the provider's full verified raw catalogue, then build a versioned feature inventory from observed data.

### 2.3 Relevant player statistics visible in the public type catalogue

Examples with documented type IDs:
- Tackles: 78
- Interceptions: 100
- Clearances: 101
- Key passes: 117
- Minutes played: 119
- Touches: 120
- Tackles won: 27267
- Passes in final third: 27269
- Ball recovery: 27271

These examples are not a complete list and do not establish season-by-season availability. Statistic definitions, units, aggregation semantics and source coverage must be captured from the current catalogue and actual fixture responses.

## 3. Access, pricing and historical-data caveats

As checked on 2026-11-26:
- The free plan covers the Danish Superliga and Scottish Premiership, not the Premier League.
- The Starter plan is advertised from €29/month (or €24/month billed yearly), permits five selected leagues, includes the standard professional data features and has a 14-day paid-plan trial.
- The Growth plan is advertised from €99/month (or €79/month billed yearly) and permits 30 leagues. It is not necessary merely to test one league if Starter can select the Premier League.
- The pricing page says historical data older than three seasons requires a one-time historical-data add-on for Starter/Growth/Pro; it advertises the add-on from €29. Enterprise includes full historical access.
- The paid-plan trial FAQ says a payment method is charged after the 14-day trial unless the plan is cancelled in time. Do not start a paid trial or incur charges without the user's explicit approval.
- The Premier League page lists 2025/26 as season ID 25583. The 2026/27 season ID must be enumerated from the API when credentials are available.

For the current 2PM plan (2025/26 training and 2026/27 out-of-time evaluation), older-than-three-season historical access may not be required, but this must be confirmed against the exact desired training sample window and the provider's entitlement rules.

## 4. Mandatory empirical validation before provider selection

No code should assume Sportmonks is suitable until all of the following are tested against actual Premier League API responses:

### A. Access and entitlements
- Confirm the Premier League can be selected on the intended plan.
- Confirm whether completed historical fixture lineups.details are accessible for both 2025/26 and 2026/27.
- Confirm rate limits, pagination, request cost and any historical endpoint restrictions.
- Confirm retention and machine-learning/training rights for acquired data. API access alone is not proof of model-training or long-term storage rights.

### B. Coverage by season
- Enumerate the exact Premier League season IDs required.
- Enumerate every completed fixture in each season.
- Sample early-, middle- and late-season fixtures, plus fixtures with substitutions, red cards, own goals, penalties and double-gameweek/rescheduled contexts.
- Compare the returned player-statistic type IDs across seasons and fixtures.
- Quantify fixture coverage, lineup coverage, player-stat completeness and per-statistic missingness.
- Distinguish a true zero from an absent statistic, unavailable statistic type, missing lineup record or provider-side null.

### C. Identity and participation
- Build a new Sportmonks player-ID ↔ official FPL element-ID crosswalk from independently verified identity evidence.
- Preserve provider player IDs, team IDs, fixture IDs and season IDs as source-native keys.
- Handle transfers, name variants, duplicate names, promoted/relegated clubs and players with multiple team spells.
- Do not reuse Understat identity assignments.
- Validate minutes, starter/substitute status and appearance against official FPL records and fixture events.

### D. Temporal integrity
- Historical match statistics are post-match observations. They may enter a later target prediction only after the source fixture has finished and the data was available by that target's cutoff.
- Record fixture kickoff, completion/state, provider last_processed_at (where supplied), retrieval time and immutable raw-response hash.
- Do not assume a historical endpoint reproduces exactly what was known at an earlier deadline; measure correction/update behavior and preserve acquisition vintages.
- Never include target-fixture or later-fixture statistics in that target's inputs.

### E. Data quality and usefulness
- Check consistency of player and team totals, minutes, lineup participation and event-derived counts.
- Investigate outliers, negative/compound values, percentage denominators and definition changes.
- Compare a sample of key statistics against official FPL fields where overlapping definitions exist, without assuming definitions are identical.
- Assess whether the provider's catalogue supports a useful new player-match representation for 2PM. Do not optimize for a large feature count.

## 5. Dataset design direction after validation

If Sportmonks passes the gates, implement a provider-specific, resumable acquisition layer that:
- stores original JSON responses unchanged, with request parameters, response hash, retrieval timestamp, provider version and source IDs;
- checkpoints every successful fixture response immediately;
- restores and validates existing responses before making new requests;
- re-downloads only missing, corrupt or explicitly version-invalid records;
- uses source/season/fixture/request-aware cache keys;
- supports retries and rate limiting without losing completed work;
- stores the statistic type catalogue as a versioned source artifact;
- builds normalized player-fixture and team-fixture tables from the immutable raw responses;
- generates a new versioned 2PM feature inventory only after coverage and semantics are measured.

No paid bulk acquisition, full-season download, or model training is authorized by this evaluation decision.

## 6. Current conclusion

**Sportmonks is a promising first candidate, but not yet selected.**

The strongest positive evidence is that its documented fixture API provides player-level match statistics through lineups.details, alongside team match statistics, and that the Premier League is a covered competition.

The key unresolved risk is historical depth and consistency of those player-match statistics across the exact seasons required by 2PM. Public documentation does not settle that question. The provider's 63-stat claim must be validated against actual historical Premier League fixture responses.

## 7. Next action

Run a small, read-only sample audit after an API token is configured securely for the repository workflow or local environment. Do not paste the token into source files, commits, logs, or chat. The audit should fetch only a handful of completed Premier League fixtures across the required seasons, save each response and manifest, and report:
- season/fixture identity;
- lineup/player count;
- statistic type IDs and codes;
- per-player statistic coverage;
- null/absent-vs-zero distinctions;
- request usage and response hashes.

Only after this report should the team decide whether to adopt Sportmonks and design the new feature inventory.
