# M4 CoVar — Full-Gameweek FPL Rules Audit

**Audit date:** 2026-11-21  
**Season scope:** 2026/27  
**Status:** PASS for the lineup-resolution rules listed below; independent real-world replay validation remains required.  
**Release status:** Synthetic research only. `decision_weight=0`; `production_eligible=false`.

## Sources reviewed

1. Premier League, **FPL Rules Copilot**, published 18 May 2026:  
   https://www.premierleague.com/ar/news/4661029
2. The Scout, **FPL basics explained: Managing your team**, published 20 July 2026:  
   https://www.premierleague.com/en/news/2174899
3. Official Fantasy Premier League Help / FAQs:  
   https://fantasy.premierleague.com/help/faqs

The current 2026/27 rules and management guide were preferred over older season explanations.

## Rule-by-rule findings

| Rule | Official guidance | Implementation assessment |
|---|---|---|
| Starting formation | One GK, at least 3 DEF, at least 2 MID and at least 1 FWD. The 2026/27 management guide states all four requirements. | **Pass.** Contract and resolver validate the same 3/2/1 outfield minimums and one goalkeeper. |
| What counts as playing | An appearance on the pitch or receiving a yellow/red card counts as playing in the Gameweek. | **Pass.** Inputs require explicit `played` booleans. A card-only zero-minute appearance may be `played=true`; positive minutes require `played=true`. |
| Goalkeeper autosub | If the starting GK does not play, the reserve GK replaces them if the reserve GK played. | **Pass.** Implemented as a distinct goalkeeper-only replacement. |
| Outfield autosubs | Process substitutes in submitted bench priority; the highest-priority substitute who played and does not break formation enters. | **Pass.** Resolver iterates bench order and skips an unavailable or formation-ineligible substitute; a later eligible substitute can enter. |
| Captain fallback | Vice-captain takes the armband only if the captain does not play; no bonus if neither plays. | **Pass.** Uses the Gameweek played flag, not minutes alone. |
| Triple Captain | Captain points are tripled rather than doubled. | **Pass.** Active captain/vice fallback receives a 3x total multiplier. |
| Bench Boost | Bench players' points are included in the Gameweek total. | **Pass.** All 15 players are scored once; captaincy remains active. |
| One chip per Gameweek | Only one chip can be played in a Gameweek. | **Input contract.** Each portfolio carries one `active_chip` value. The builder does not model multiple simultaneous chips. |
| Double Gameweeks | A player who appears in any scheduled fixture in the Gameweek does not qualify for an autosub; the same applies to captaincy. | **Represented.** One explicit Gameweek-level `played` flag governs all fixtures in that Gameweek. Scenario generation must aggregate all scheduled fixtures before setting this flag and total points. |
| Processing time | Autosubs and captain changes are processed after all Gameweek matches. | **Represented.** Resolver runs once per complete Gameweek scenario, not per fixture. |

## Implementation locations

- `scripts/m4_covar_lineup_resolver.py`
- `tests/test_m4_covar_lineup_resolver.py`
- `scripts/m4_covar_full_gameweek_contract.py`
- `tests/test_m4_covar_full_gameweek_contract.py`
- `scripts/m4_covar_full_gameweek_scoring.py`
- `tests/test_m4_covar_full_gameweek_scoring.py`

Specific resolver tests cover goalkeeper replacement, reserve goalkeeper absence, bench priority, skipping an illegal substitute, multiple absences, captain fallback, neither captain playing, a player appearing briefly, card-only appearance, Triple Captain, Bench Boost, and explicit Free Hit mode.

## Interpretation and boundaries

- The 2026/27 management guide explicitly includes the minimum of two midfielders. The shorter rules summary lists the goalkeeper, defender and forward minimums but does not repeat the midfielder minimum; the implementation follows the more explicit 2026/27 formation guide.
- The `played` flag is a required scenario input. It must be derived from complete Gameweek match evidence, including card-only appearances and all fixtures in a Double Gameweek. It must not be inferred solely from a positive-minutes check.
- `FREE_HIT` is a mode label and is accepted only when explicitly supplied. It does not alter lineup scoring; Free Hit's transfer/reset mechanics are outside this scorer.
- The resolver consumes supplied FPL points. It does not establish that the scenario's event-to-points calculation is complete or accurate.
- This audit does not validate the representativeness of the manager sample, field-relative tail probabilities, event-based BPS, set-piece attribution, or forecast quality.

## Remaining acceptance work

1. **Real-world replay baseline completed:** 10 officially finished Gameweeks (GW1-GW10) were captured and passed against the official FPL picks, player points and manager Gameweek points. This sample contained no automatic substitutions, so autosub edge cases still need real-world coverage.
2. Expand the real replay sample to include at least one actual goalkeeper autosub, one outfield autosub, captain fallback, and a Double/Triple Gameweek. Synthetic tests cover the mechanics, but do not replace those observations.
3. Independently verify the event/scenario layer's fixture aggregation and full-Gameweek event scoring against official realized data, including BPS and any missing event fields.
4. Raw manager picks payloads must not be committed or uploaded. The cloud workflow uploads only the normalized replay artifact with manager entry identity, manager name and rank omitted; roster combinations can still be cross-referenced against public data.
5. Keep all CoVar outputs research-only with `decision_weight=0` and `production_eligible=false`.

**Conclusion:** No conflict was found between the reviewed 2026/27 official lineup, autosubstitution, captaincy and chip rules and the implemented deterministic resolver. This is a rules-specification audit, not production certification.

## Private official-result replay harness

A local replay validator is implemented in
`scripts/m4_covar_fpl_replay_validation.py`, with tests in
`tests/test_m4_covar_fpl_replay_validation.py`.

It accepts a normalized local replay case containing the submitted lineup,
complete Gameweek player outcomes, official final FPL pick multipliers and
official per-player Gameweek points. It compares all 15 official pick
multipliers with the resolver's expected multipliers, checks active captain
fallback, checks per-player points and reconciles the official team total
from player points multiplied by official pick multipliers. It also provides
a helper to derive the explicit Gameweek `played` flag from official minutes
and yellow/red-card counts.

The input validator rejects manager IDs, names and exact ranks. The CLI
requires a private input file outside the repository and prints a local report;
it does not write replay files, call external services, or upload data. No real
manager-level replay file is included in the repository. Synthetic unit tests
validate the comparison mechanics only; they are not evidence of a successful
real-world FPL replay.

## Official FPL API replay normalizer

A pure local adapter is implemented in
`scripts/m4_covar_fpl_api_replay_adapter.py`, with tests in
`tests/test_m4_covar_fpl_api_replay_adapter.py`. It accepts three caller-
supplied official API payloads: the manager's event-picks response, the event
live response, and bootstrap-static player metadata. It makes no network
requests.

The adapter reconstructs positions 1-15, starting XI, reserve goalkeeper,
outfield bench order, player positions, captain and vice-captain. It maps
bootstrap `element_type` values to FPL positions and derives Gameweek played
status from live minutes and yellow/red-card statistics. It retains official
final pick multipliers and per-player total points for comparison by the
existing replay validator.

The output deliberately excludes the picks response's manager entry identity,
manager name, rank and other unrelated fields. It validates complete 15-player
coverage, unique ordered positions, legal formation, goalkeeper slots,
captaincy, chips, and the presence of each selected player's live and bootstrap
records. Free Hit mode is inferred only from the explicit official
`active_chip=freehit` value; otherwise regular Gameweek mode is the default.

The adapter is a deterministic transformation, not an API fetcher. Actual
payload acquisition, private local replay execution, and a real completed-
Gameweek replay batch remain pending. No real manager data is stored in this
repository or sent to CI.

## Private official API acquisition CLI

A separate local-only fetcher is implemented in
`scripts/m4_covar_fpl_api_replay_fetch.py`, with mocked-network tests in
`tests/test_m4_covar_fpl_api_replay_fetch.py`. It retrieves only the three
official FPL API resources needed by the pure normalizer: one entry's completed
event picks, the event live payload, and bootstrap-static metadata.

The manager entry ID is requested through a hidden interactive prompt and is
not printed, persisted, or included in the normalized output. The fetcher checks
that the official picks response identifies the requested Gameweek and that
bootstrap-static marks that Gameweek as finished; it rejects missing, duplicated,
mismatched or unfinished event metadata. The output must be an absolute path
outside the repository, is created with owner-only permissions, and cannot
overwrite an existing file. The script makes no GitHub calls and is not invoked
by CI. API errors fail closed; no raw API payloads are written to disk.

Example local workflow (run from the engineering workbench scripts directory
or set the corresponding Python path):

```bash
python m4_covar_fpl_api_replay_fetch.py --event 10 --output /secure/private/gw10_replay.json
python m4_covar_fpl_replay_validation.py --input /secure/private/gw10_replay.json
```

Use only completed Gameweeks. A successful download is not itself a replay
pass: the replay validator's report must show `PASS`. The one-Gameweek local CLI remains available. A cloud batch workflow now
captures multiple completed Gameweeks and validates them; see the real-world
coverage section below.


## Multi-Gameweek replay coverage report

The private replay validator now emits a batch-level coverage summary
(schema `1.1.0`) alongside case-level results. Normalized API replay cases
carry an explicit `event_id`; the validator rejects non-positive or
non-integer event identities.

The batch report includes:
- total, passed and failed replay counts;
- number and list of distinct Gameweeks represented;
- per-Gameweek replay, pass and fail counts;
- counts by resolver mode and active chip;
- number of replays with multiplier, player-points, captain-fallback or
  official-team-total reconciliation mismatches.

These summaries make multi-Gameweek validation auditable without treating a
single successful Gameweek as broad evidence. They do not establish sample
representativeness: multiple managers from one Gameweek are still one
Gameweek of rule coverage, not independent temporal validation. The report
remains private/local, and its production eligibility remains false with
decision weight zero. Synthetic batch tests verify aggregation mechanics only;
no real completed-Gameweek replay has yet been run.

## Real-world multi-Gameweek replay — 2026-11-22

A branch-scoped GitHub Actions workflow acquired the official picks, event-live
and bootstrap-static responses for the user-authorized public manager entry,
then normalized them in memory. Raw manager API payloads were not written to
the artifact. The uploaded 30-day artifact contains only the normalized replay
cases and validation report; it omits manager entry ID, manager name and rank.
Player IDs and squad combinations remain cross-referenceable with public FPL
data, so this should be described as identity-field-stripped rather than
irreversibly anonymous.

- Requested Gameweeks: GW1-GW11.
- Captured and validated: **10 completed Gameweeks, GW1-GW10**.
- GW11: skipped because official bootstrap metadata did not yet mark it finished.
- Replay results: **10 PASS, 0 FAIL**.
- Official player-point mismatches: 0.
- Official pick-multiplier/autosub mismatches: 0.
- Captain/vice-captain mismatches: 0.
- Official `entry_history.points` reconciliations: **10/10**, 0 failures.
- Chip coverage: 8 without a chip, 1 Free Hit, 1 Wildcard.
- Actual autosubs in this manager sample: **3** across GW4-GW5:
  one outfield substitution in GW4, then one goalkeeper and one outfield
  substitution in GW5. All three official pairs match the resolver exactly.
- Completed-Gameweek API positions are post-autosub. The adapter reverses each
  official `automatic_subs` pair to reconstruct the submitted deadline XI,
  reserve goalkeeper and bench order, while retaining final scoring multipliers.
  This also restores captain/vice positions when a starter was replaced.
- Double-Gameweek aggregate-minute handling: the resolver now accepts
  Gameweek totals above 120 minutes; the per-fixture scenario and event-scoring
  contracts retain the 120-minute per-match bound. A full-Gameweek scoring
  regression test covers a 165-minute aggregate.

The batch capture now treats an unfinished Gameweek as an expected skip, not
a capture failure. The replay validator also distinguishes reported
`entry_history.points` from the alternative net-of-hit convention and accepts
a team-total reconciliation only when either the reported score itself or
reported score plus explicit transfer cost matches the lineup score.

Workflow and evidence:
- [Cloud replay + focused CoVar workflow run 44998292049](https://github.com/uasir/CTA-FPL-Model/actions/runs/44998292049)
- [Full engineering CI run 44998292016 — 871 tests and 3 subtests](https://github.com/uasir/CTA-FPL-Model/actions/runs/44998292016)
- Focused CoVar tests: **155 passed** in run 44998292049.

This is a single-manager temporal validation set, not a representative field
sample or a calibrated forward joint forecast. It now exercises real
goalkeeper and outfield autosubs, captaincy, chips and team-score reconciliation.
All CoVar outputs remain `decision_weight=0` and `production_eligible=false`.

## Official event-scoring reconciliation — 2026-11-22

The 2026/27 event scorer was independently checked against the official FPL
`event/{event}/live/` per-fixture `explain` breakdown for every player in
10 final-scored Gameweeks (GW1-GW10).

- Official player rows: **6,562**.
- Player-fixture explain rows scored: **6,562**.
- Fixture rows matching the local event scorer: **6,562 / 6,562**.
- Mismatches: **0**.
- Unmapped positive scoring identifiers: **0**.
- Official points sum: **9,145**.
- Locally calculated points sum: **9,145**.
- GW11 was skipped because it was not yet final-scored.

The reconciliation maps per-fixture minutes, goals, assists, clean sheets,
goals conceded, own goals, penalty saves/misses, yellow/red cards, saves,
defensive contributions and official bonus points. This validates the
fixture-level point arithmetic against official outcomes for the observed
sample. It does **not** validate a predictive BPS model: official bonus points
are consumed as an observed input, not generated by this scorer. The 10-GW
sample contains no demonstrated Double Gameweek fixture rows; synthetic
coverage verifies fixture-by-fixture aggregation and the 165-minute
Gameweek-total case.

The 2026/27 official scoring rules and BPS changes are documented by the
Premier League:
- [FPL scoring points](https://www.premierleague.com/en/news/2174909/fpl-basics-scoring)
- [2026/27 Bonus Points System changes](https://www.premierleague.com/en/news/4679946/whats-new-in-202627-fantasy-changes-to-bonus-points-system)
- [Official FPL FAQ](https://www.premierleague.com/en/news/4661030)

Validation:
- [Focused CoVar + official event-scoring + replay workflow run 44998292049](https://github.com/uasir/CTA-FPL-Model/actions/runs/44998292049)
- [Full engineering CI run 44998292016 — 871 tests and 3 subtests](https://github.com/uasir/CTA-FPL-Model/actions/runs/44998292016)
- Focused CoVar tests: **155 passed**.

This is retrospective realized-score reconciliation, not point-in-time
forecast validation or a forward joint distribution. CoVar remains
`decision_weight=0` and `production_eligible=false`.

## Public Overall-league replay stress test — 2026-11-22

A second, aggregate-only audit sampled 25 public managers from five separated
Overall classic-league standings pages and replayed GW6-GW10. Entry IDs, names,
exact ranks and individual picks were used only in memory and are not retained
in the report.

- Manager sample: **25** across five rank pages.
- Manager-Gameweek replays: **125/125 PASS** across GW6-GW10.
- Capture failures: **0**.
- Official final multipliers and team totals: **125/125 reconciled**.
- Autosub replays: **52**, involving **68** incoming players.
- Captain fallbacks: **6**.
- Chip coverage: 6 Triple Captain, 5 Bench Boost, 2 Free Hit, 5 Wildcard and
  107 without a chip.
- Six records had different exact pair assignments between the resolver and
  API metadata, but every one retained the same incoming and outgoing player
  sets and the same final scoring multipliers. These are pair-mapping
  diagnostics, not scoring failures. No autosub player-set mismatches occurred.
- No goalkeeper autosub occurred in this 25-manager sample; the private
  manager replay above independently exercises a real goalkeeper autosub.

This is a rank-stratified resolver stress-test, not a representative estimate
of the global field, not a pre-deadline portfolio census, and not a
field-relative score forecast. It validates lineup reconstruction and
scoring behavior over observed completed Gameweeks. CoVar remains
`decision_weight=0` and `production_eligible=false`.

Evidence: [public field replay + CoVar validation run 44998292049](https://github.com/uasir/CTA-FPL-Model/actions/runs/44998292049).
