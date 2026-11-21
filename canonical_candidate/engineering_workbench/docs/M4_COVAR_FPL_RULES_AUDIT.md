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

1. Run the private replay harness against actual completed Gameweeks and compare resolver output with official FPL final pick multipliers, including Double Gameweeks, card-only appearances and multiple simultaneous no-shows. The harness is implemented; no real replay batch has yet been supplied or validated.
2. Independently verify that the event/scenario layer aggregates all fixtures and points at Gameweek level before invoking the resolver.
3. Keep all real manager-level pick artifacts private and local. Never commit or upload them.
4. Keep all CoVar outputs research-only with `decision_weight=0` and `production_eligible=false`.

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
pass: the replay validator's report must show `PASS`. Real replay execution
and a multi-Gameweek validation batch remain pending.
