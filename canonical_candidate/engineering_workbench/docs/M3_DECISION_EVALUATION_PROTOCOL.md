# M3.4 — External Benchmark Decision Evaluation Protocol

**Status:** Protocol specification; no provider or recommendation is promoted by this document.  
**Scope:** M3 only. M2 continues independently. M4 field-relative/EO intelligence and M5 release remain out of scope.

## 1. Evaluation objective

Evaluate whether a frozen, deadline-eligible external forecast snapshot produces useful conventional personal-squad decisions for the manager state available at that deadline. Evaluate the complete decision, not only the incoming player's forecast.

The initial deliverable remains exactly one product: a conventional, squad-specific recommendation. CTA/ABC/2PM outputs, squad-independent rankings, provider consensus, EO/CoVar optimisation and public release are excluded until their own gates are met.

## 2. Unit of evaluation and cohort construction

The primary unit is a manager-deadline decision record:
- one manager/team ID and target gameweek;
- one immutable 15-player squad snapshot, bank, free transfers, purchase/selling prices and strategy inputs as known before the deadline;
- one provider, product, variant and immutable forecast snapshot;
- one decision timestamp strictly before the official deadline;
- one deterministic recommendation output and its complete provenance.

A decision cohort is eligible only when every required input can be shown to have existed before that gameweek's deadline. Retrospectively collected current prices, later provider revisions, post-deadline forecasts, final lineups and realised points must never enter the decision input.

Keep provider/variant cohorts separate. Never average providers or fill one provider's missing forecasts with another provider's values. Publish coverage and exclusions alongside every score.

## 3. Required archived evidence

For each evaluated deadline, retain and hash:
1. raw provider response, provider identity/variant, disclosed generation time, capture time and source URL;
2. raw official FPL metadata used at that time, including element IDs, positions, teams and prices;
3. manager squad state, bank, free transfers, purchase prices and their source/provenance;
4. official deadline and the decision as-of timestamp;
5. canonical decision input and complete output, including software commit and contract version;
6. post-deadline official FPL event data needed to calculate realised points and autosubs.

If an exact historical manager squad, bank, free-transfer count or purchase/selling-price state cannot be reconstructed from timestamp-valid evidence, that manager-deadline is not eligible for the primary personal-squad backtest. It may be retained in a clearly labelled diagnostic cohort, never silently repaired with current values.

A single live GW11 capture is an operational integration test, not a historical evaluation cohort.

## 4. Decision comparators

For every eligible manager-deadline, calculate at least:

- **Recommended action:** the frozen engine's single chosen action and resulting legal squad plan.
- **Hold baseline:** the same starting squad, no transfer, same deadline and scoring rules; optimise only the starting XI/bench/captain if that is explicitly part of the engine's decision policy. Do not give the hold baseline hindsight information.
- **Decision regret diagnostic:** compare the realised result with the best legal action discoverable after the deadline only as an explicitly hindsight-only upper bound. It is not a deployable benchmark and must not be used to claim predictive skill.

If additional conventional external decision systems are introduced later, each must have its own frozen input/output and provider-specific cohort. Do not create an undocumented consensus baseline.

## 5. Outcome calculation

Use official FPL gameweek scoring and the actual realised player points for the target gameweek. Reproduce the submitted decision's formation, starting XI, captain, vice-captain, bench order, reserve goalkeeper, automatic substitutions and captaincy fallback under the official rules.

For each recommendation, report:
- realised squad points after official substitutions and captain multipliers;
- transfer cost/hit points, if any, separately and net of squad points;
- realised net points delta versus the hold baseline;
- transfer outcome: incoming and outgoing player realised points, with the squad-level delta remaining the primary metric;
- whether the recommendation was legal and executable using the archived manager state.

Do not score a transfer by simply subtracting the outgoing player's points from the incoming player's points: the outgoing player may be on the bench, the incoming player may alter formation/substitutions, and captaincy/bench effects matter.

## 6. Forecast diagnostics (separate from decision outcomes)

At player-GW grain, score each provider only on the exact matched player-GW rows in its own eligible snapshots. Report:
- matched row count and player coverage;
- MAE and RMSE for xP;
- rank correlation (with tie handling stated);
- calibration diagnostics only where the provider's output semantics support them;
- missingness and exclusions by reason.

Do not interpret xP MAE as proof of transfer-decision value. A provider may rank players well but still produce poor manager-specific actions due to price, squad composition, constraints or captaincy.

## 7. Aggregation and uncertainty

Show per-gameweek results and pooled results. Keep all decisions from the same gameweek grouped when calculating uncertainty; player rows within a gameweek are not independent decision samples.

For paired recommendation-versus-hold comparisons, report:
- number of eligible manager-deadlines and number of distinct gameweeks;
- mean and median net-points delta;
- distribution and win/tie/loss counts;
- a gameweek-clustered bootstrap confidence interval, resampling gameweeks rather than individual players.

Do not declare superiority from one deadline, one gameweek, a small unclustered sample or a confidence interval that includes zero. Pre-register any minimum sample size, material-effect threshold and promotion rule before looking at comparative results; until that rule is approved and met, status remains **NOT VALIDATED**.

## 8. Determinism and leakage tests

The evaluation harness must reject:
- provider generation/capture at or after deadline;
- decision timestamps at or after deadline;
- missing generation time where the contract marks the snapshot diagnostic-only;
- source-hash mismatch or missing raw source archive;
- duplicate player-GW rows, unmapped player IDs or ambiguous forecast grain;
- manager-state rows that do not reconcile to 15 unique legal players;
- retrospective or post-deadline metadata in decision inputs;
- incomplete realised-points coverage for a scored squad;
- a recommendation output whose transfer and post-transfer 15-player plan disagree.

Identical frozen inputs, software commit and configuration must reproduce an identical decision payload (excluding explicitly non-deterministic execution metadata). Store the input and output hashes.

## 9. Promotion gates

No provider or recommendation policy is promoted until all of the following are evidenced:
1. repeatable, deadline-eligible archived captures across multiple gameweeks;
2. exact player identity and metadata joins with traceable raw hashes;
3. complete manager-state evidence for the evaluated personal-squad cohort;
4. deterministic replay and FPL-legal post-action plans;
5. official realised-points calculation independently checked against FPL scoring rules;
6. paired recommendation-versus-hold results with gameweek-clustered uncertainty;
7. provider-specific coverage, forecast diagnostics and decision outcomes disclosed together;
8. a pre-registered minimum sample and material-effect rule met;
9. all limitations and exclusions preserved in the decision output.

Software tests establish implementation behaviour, not forecast accuracy, decision value or rank improvement. A provider's website visibility, a single positive GW delta or an isolated xP metric is not a promotion criterion.

## 10. Current evidence status (2026-11-20)

- One successful live GW11 FPL Cat capture and manager-backed execution exists.
- The manager context used reconstructed purchase prices because the GW10 picks response did not expose purchase_price fields.
- The live run is useful for integration and provenance checks, but it is not a multi-gameweek backtest.
- Historical pre-deadline FPL Cat snapshots and exact historical manager states have not yet been established as a complete cohort.
- Therefore provider decision accuracy, recommendation value and release eligibility remain **NOT VALIDATED**.

## 11. Next implementation task

Implement a fail-closed evaluation input contract and deterministic scoring harness against synthetic fixtures first. The harness must encode the rules above without pretending synthetic fixtures are historical evidence. Only after its tests pass should archived real gameweeks be admitted, one at a time, with source and eligibility audits.


## Manager strategy constraints — fixed XI and budget bench

The personal-squad decision engine must represent the manager's actual operating policy, not assume a routinely rotated 15-player squad.

- The manager supplies the intended starting XI separately from the 15-player squad.
- The starting XI is held fixed across a recommendation. A transfer of a starter replaces that starter; a transfer of a bench player may displace only the weakest starter in the same position, and only when the incoming forecast improves the starting XI.
- A bench-to-bench points upgrade is not a sufficient reason to recommend a transfer.
- Goalkeeper transfers are excluded. The designated starting goalkeeper is preserved in the post-transfer XI; the reserve goalkeeper is emergency cover, not a rotation option.
- The three outfield substitutes are treated as budget emergency cover. Bench order remains relevant for automatic substitutions, not routine rotation.
- The workflow captures the manager-confirmed starting XI as a separate input. The lineup must contain 11 unique players from the confirmed 15-player squad and must pass the normal formation/position checks.

These are manager-specific constraints, not universal FPL rules. They do not imply that a transfer is worthwhile merely because it can change the XI; affordability, legal squad construction, hit cost and positive starting-XI gain still apply.


## 10. Initial deterministic scorer contract (synthetic-only implementation)

The first scorer is implemented in `scripts/evaluate_external_benchmark_decisions.py`. It validates a frozen record before scoring and currently admits only `SYNTHETIC_TEST` records. `REAL_CANDIDATE` records fail closed until a separate historical-evidence admission process is implemented.

Required evidence archives are separately hashed for:
- provider forecast (including provider generation timestamp);
- pre-deadline official player metadata;
- pre-deadline manager state;
- post-deadline realised player points, captured only after the Gameweek is finalised.

The frozen decision is independently SHA-256 sealed. The contract checks deadline ordering, raw archive hashes, full 15-player squad composition, team limits, prices, legal formation, captain/vice, reserve goalkeeper, transfer legality, exact post-transfer roster, fixed starting-XI replacement constraints, and realised-points coverage. A transfer comparison requires realised rows for the 15 original players plus the incoming player (16 rows), so the outgoing player's hold-baseline score is not lost.

The scorer uses official FPL per-player `total_points` as its realised points input; it does not independently reconstruct goals, assists, clean sheets, bonus points or other player-level scoring events. It applies the manager-level effects: ordered automatic substitutions, reserve-goalkeeper substitution, captain/vice fallback and the one-transfer four-point hit rule. It rejects chips in this initial implementation.

The appearance flag follows FPL's published definition: a player counts as having played if they appeared or received a yellow/red card. Therefore zero minutes alone is not enough to qualify a player as absent. Official rule references:
- https://fantasy.premierleague.com/help/faqs
- https://www.premierleague.com/en/news/2174899

The scoring implementation remains provisional until independently reconciled against completed official FPL manager Gameweek scores and substitution outcomes. Synthetic test success demonstrates deterministic software behaviour only; it is not evidence of historical decision value or release eligibility.

The transfer validator also enforces the manager strategy’s no-goalkeeper-transfer rule, exact incoming/outgoing position match, three-per-club squad limit, one-transfer free-transfer/hit treatment, and affordability using captured bank plus FPL half-profit selling-price rounding. The output retains the frozen decision hash, evaluation-input hash, source archive IDs/hashes, software commit and transfer financials.

For a transfer comparison, the realised-points cohort must contain all 15 original squad players plus the incoming player. This is necessary to score both the recommendation and the no-transfer hold baseline against the same Gameweek. The outgoing player is retained in that comparison even though he is absent from the post-transfer squad.

The initial implementation rejects malformed transfer IDs, invalid or incomplete source archives, unaffordable transfers, changed designated goalkeepers, incomplete realised rows, unsupported chips and all real-world candidate records pending admission.
Each record also binds the manager team ID, provider snapshot ID, decision-contract version, software commit, requested formation and personal risk profile. The risk profile is retained for provenance but is explicitly marked not applied by this initial engine.

The realised-points archive must carry a Gameweek finalisation timestamp and be captured after finalisation. A post-deadline but pre-finalisation points snapshot is not eligible for scoring. Player rows require official integer `total_points`, minutes, yellow cards and red cards; the appearance test follows the official FPL rule that a player counts as having played if they appeared or received a yellow/red card.

For a one-transfer action, the contract verifies the transfer hit (zero when a free transfer is available, otherwise four points), outgoing selling price using FPL half-profit rounding, incoming price and non-negative post-transfer bank. It returns the calculated financials alongside the paired score.

## 12. Independent official-manager reconciliation harness

The separate `scripts/reconcile_official_fpl_manager_result.py` module compares a local hold-plan score with the completed official manager picks response and official event-live points. It checks:
- the official manager event number and exact frozen starting XI, outfield bench order, reserve goalkeeper, captain and vice-captain;
- the official `automatic_subs` pairs against the locally simulated outfield and goalkeeper substitutions;
- the effective captain selected by the official player multipliers against local captain/vice fallback;
- the official multiplier-weighted gross score against the local gross score;
- the official multiplier-weighted gross score against `entry_history.points`; `event_transfers_cost` is a separate deduction and net points are reported as gross minus that cost.

Chip gameweeks, unsupported multipliers, missing player live points, duplicate picks, gross-score mismatches and lineup mismatches fail closed. The official `entry_history.points` field is compared to gross event points; the separate `event_transfers_cost` is not subtracted for that comparison. The output is labelled `RECONCILED` only for that specific manager/gameweek score comparison and explicitly sets `historical_evidence_admitted: false`; it does not by itself admit a record into the historical cohort or validate forecast quality.

Synthetic contract tests are added in `tests/test_reconcile_official_fpl_manager_result.py`, including a test that locks gross event points and transfer hits as separate values. The first completed official reconciliation (manager 421025, GW10; run 44773107029) passed: local and official gross points both 70, transfer cost 8, derived net 62, effective captain 411, and no automatic substitutions. The exact official XI, bench order, reserve goalkeeper, captain and vice-captain also matched. The raw official bootstrap, manager picks and event-live responses are archived with SHA-256 hashes in the workflow artifact. This validates the scorer against that one completed manager/Gameweek outcome only; `historical_evidence_admitted` remains false, and it does not validate forecast quality or recommendation value.


The manual workflow `.github/workflows/reconcile-official-fpl-manager.yml` runs `scripts/capture_and_reconcile_official_fpl_manager_result.py` for a selected manager and completed Gameweek (defaults: manager 421025, GW10). It fetches the official bootstrap, manager picks and event-live endpoints, requires the event to be both finished and data-checked, preserves each raw response as base64 with SHA-256 and capture time, derives the actual deadline XI/bench/captain state, and runs the independent comparison. The uploaded artifact is a reconciliation record only; historical evidence admission remains false. This workflow must be run and its artifact inspected before claiming real-world reconciliation.


## 13. Multi-Gameweek official manager reconciliation

The manual workflow now accepts a comma-separated list of completed Gameweeks (default manager 421025; default requested events 1–8 and 10) and runs the independent official scorer for each event. The batch runner preserves each successful Gameweek's raw source archives and reports, separately and explicitly, any requested Gameweek excluded because its official data is unavailable, unfinished, chip-based or otherwise unsupported. A partial batch still uploads its diagnostic artifact and then fails the workflow so exclusions cannot be mistaken for a complete pass.

The batch summary identifies which reconciled events contained official automatic substitutions and which incurred transfer costs. Each event remains an independent reconciliation; no aggregate score is treated as forecast or decision validation. `historical_evidence_admitted` remains false for the batch and every child record. The batch harness has synthetic tests for ordered input parsing, duplicate/invalid event rejection, explicit exclusions, autosub identification and transfer-hit identification. Real multi-event results must be inspected before this task can be marked complete.


### Autosub ordering correction from the first multi-GW batch

The first manager 421025 batch reconciled GW1, GW2, GW3, GW6, GW7, GW8 and GW10. GW4 was correctly excluded as a chip event. GW5 exposed an important API representation detail: the historical picks `position` fields reflected the post-autosub lineup, while `automatic_subs` identifies the incoming XI player and outgoing bench player. The initial capture treated post-autosub positions as the deadline lineup, producing a false mismatch. The batch artifact retained raw GW5 evidence after the diagnostic-capture patch; it showed official pairs 497→110 (reserve goalkeeper) and 165→127 (outfield). The capture and reconciliation code now reverses those pairs to reconstruct the deadline XI/bench before independently simulating autosubs. Synthetic tests now model post-autosub positions. This correction must pass CI and a fresh official GW5 reconciliation before the autosub path is considered verified.


### Multi-Gameweek reconciliation outcome and archive audit

Manager 421025's requested GW1–8 and GW10 batch now reconciles eight events (GW1, GW2, GW3, GW5, GW6, GW7, GW8 and GW10); GW4 is excluded because it used a chip. GW5 independently reconciles both official automatic substitutions: reserve goalkeeper 497→110 and outfield player 165→127. Transfer-cost cases are GW6 (4), GW7 (4) and GW10 (8); GW1, GW2, GW3, GW5 and GW8 have zero transfer cost. All eight local gross scores match the official multiplier-weighted gross totals. This is manager scoring/substitution reconciliation, not forecast or recommendation validation.

The next automated gate is `audit_official_fpl_manager_batch.py`. It decodes each archived official payload, recomputes SHA-256, checks timezone-aware capture timestamps and source URLs, verifies event finalisation and manager/Gameweek identity, and recomputes batch coverage summaries. It also preserves the rule that historical evidence admission is false. The workflow now runs this audit and uploads both the batch evidence and audit report. A successful archive audit verifies integrity/provenance only; it does not promote historical records into the decision-evaluation cohort.


## 14. Historical evidence admission classification (M3)

The admission classifier is `scripts/classify_historical_fpl_evidence.py`. It is deliberately separate from official score reconciliation and archive-integrity auditing. It does not infer historical manager state from current APIs, reconstructed prices, post-deadline captures or final picks positions.

Every manager/Gameweek record receives exactly one classification:

- `DECISION_BACKTEST_ELIGIBLE`: official scoring reconciliation passed and a separate evidence manifest proves that all decision inputs were captured/generated strictly before the deadline.
- `SCORING_RECONCILIATION_ONLY`: official scoring reconciliation passed, but one or more decision-input requirements are absent or unproven. This is not eligible for transfer-decision backtesting.
- `DIAGNOSTIC_ONLY`: reserved for explicitly retained diagnostic records that cannot support scoring or decision evaluation. It is never included in the primary cohort.
- `EXCLUDED`: scoring reconciliation failed, the event is outside the supported contract (including chip events), or the record is otherwise invalid.

A decision manifest must bind the manager ID and target Gameweek and include:
1. official deadline and decision-as-of timestamps, both timezone-aware, with the decision strictly before deadline;
2. raw provider forecast archive, provider generation time, capture time, snapshot ID and SHA-256, all strictly pre-deadline;
3. raw player metadata archive with pre-deadline capture time, snapshot ID and SHA-256;
4. raw manager deadline-state archive with pre-deadline capture time, snapshot ID and SHA-256;
5. exact 15-player squad, bank, free transfers, purchase and selling prices for every squad player, chip state, intended starting XI, ordered bench, reserve goalkeeper, captain and vice-captain;
6. an explicit point-in-time evidence attestation;
7. the raw payload bytes (base64) for all three decision sources, alongside their exact snapshot IDs, hashes, capture timestamps and source URLs; the provider source also requires its generation timestamp.

Missing purchase/selling prices, prices reconstructed without a complete independently replayable pre-deadline official FPL source chain, missing bank/free-transfer state, post-deadline manager captures, provider snapshots without a pre-deadline generation timestamp, or incomplete player metadata prevent decision-backtest admission. The manifest must carry the raw decision-source payloads so the independent auditor can decode them, recompute SHA-256, validate source URLs and identity, and return exact archive references. The classifier compares each manifest source type, snapshot ID, hash, capture time and URL against that audit report. A caller-supplied `archives_verified` boolean is not trusted. Importantly, the post-deadline official scoring archives (event-live, finalized bootstrap and historical picks used for score reconciliation) are kept separate and cannot stand in for pre-deadline decision inputs.

Scoring-only records may support tests of the official points/substitution reconciliation harness, but must never be passed to the recommendation-vs-hold decision scorer as historical decision records. Synthetic fixtures remain synthetic and cannot be promoted by this classifier.

The existing batch of requested GWs 1,2,3,4,5,6,7,8,10 therefore remains non-admitted until per-Gameweek point-in-time manifests are produced and audited. The eight reconciled events can be classified as scoring-only in the absence of such manifests; GW4 remains excluded for chip use. No forecast quality, decision value, rank improvement or release eligibility is established.


The workflow accepts an optional `official-fpl-decision-evidence-manifests.json` input file. When present, the batch auditor independently verifies the three raw decision-source archives for each supplied Gameweek and the classifier admits a record only when the audit report matches the manifest field-for-field. When absent, reconciled events remain scoring-only. The existing manager 421025 batch has no such pre-deadline decision-source archives, so it must remain non-admitted.


## 15. Prospective pre-deadline decision evidence capture

The prospective capture command is `scripts/capture_predeadline_decision_bundle.py`, exposed through the manual workflow `.github/workflows/capture-predeadline-decision-evidence.yml`. It creates the per-Gameweek manifest consumed by the historical evidence auditor and classifier. The workflow then runs `scripts/run_predeadline_m3_decision.py` to generate and hash-freeze the single conventional personal-squad recommendation from that exact captured input.

The workflow takes a manager-confirmed JSON state containing the exact 15-player squad, bank, free transfers, intended formation, starting XI, ordered three-player outfield bench, reserve goalkeeper, captain, vice-captain and chip state. Its default is the latest manager-confirmed GW11 state; it must be updated if the squad, bank, free transfers or lineup changes before the target deadline.

The capture is deliberately fail-closed:
- FPL Cat must return the requested target Gameweek, an explicit timezone-aware `computed_at`, and the same deadline as official FPL bootstrap metadata.
- Provider generation, provider retrieval, player-metadata retrieval and manager-state retrieval must all occur strictly before the official deadline.
- If the target-Gameweek manager picks endpoint is available, its exact squad, bank, prices, lineup, bench, captain/vice and chip state are checked against the supplied manager state.
- If the target-Gameweek picks endpoint is not yet available, the capture uses the official previous-Gameweek picks and manager history. If those picks include purchase prices, they must match the confirmed squad exactly. Otherwise it archives GW1 picks, the complete official transfer history, manager chip history and bootstrap prices, then reconstructs purchase prices deterministically.
- In the history-reconstruction path, the raw source archive is preserved. The independent auditor replays the price reconstruction from the archived official payloads and rejects any mismatch. Selling prices are independently recomputed from captured official current prices and purchase prices using the FPL half-profit rounding rule.
- The confirmed starting XI must contain 11 unique squad players and match the requested legal formation. The three ordered outfield substitutes and reserve goalkeeper must partition the remaining four squad places. Captain and vice-captain must be distinct squad players. Chip state must be NONE.
- After the Gameweek, the auditor verifies the finalized official manager state against either the captured hold baseline or the exact frozen recommendation. For the recommendation path it checks the one-transfer roster, expected bank, official transfer count and hit cost; it also verifies the recommended starting XI, ordered emergency bench, reserve goalkeeper, captain/vice and formation. Automatic substitutions are reversed before comparison. A different post-capture transfer or lineup fails admission.
- Free transfers are explicitly manager-confirmed because the public picks/history endpoints do not expose a direct authoritative pre-deadline free-transfer count in this capture contract. It remains an attested input and must be supplied accurately.
- All raw payloads are embedded in the artifact manifest with independently recomputed SHA-256, source URL, snapshot ID and capture timestamp. Provider identity, variant and generation timestamp are also bound.

A missing provider generation timestamp, unavailable or incomplete official price history, missing prices, a chip event, invalid squad/lineup, timestamp/hash inconsistency, or a post-deadline mismatch causes capture or admission to fail closed. No price value is silently invented.

The workflow exposes only the best transfer candidate in its recommendation output; secondary transfer alternatives are suppressed. It also writes a frozen evaluation candidate containing the recommendation hash, manager hold baseline and three pre-deadline source archives. The recommendation remains exploratory and `release_eligible=false`; the candidate is not scored until finalized official points and evidence admission are available. The post-Gameweek audit receives this recommendation artifact and accepts the manager's final state only if it matches either the original hold baseline or the exact frozen recommendation. The classifier requires that recommendation verification before assigning `DECISION_BACKTEST_ELIGIBLE`. It also requires the independently generated replay report from the same capture artifact. The post-Gameweek auditor binds replay status, replay type, manager ID, target Gameweek, exact software commit, frozen decision hash, raw-archive verification flags and non-release status to the recommendation candidate. Missing or mismatched replay evidence leaves the event scoring-only.

The capture workflow uploads a 90-day artifact named `predeadline-decision-evidence-manager-<manager>-gw<gameweek>`, containing both the capture manifest and `predeadline-m3-recommendation.json`. It does not itself admit a historical record or evaluate realized outcomes. After the Gameweek is finalized, the reconciliation workflow can retrieve that artifact by its workflow run ID using the optional `decision_evidence_run_id` input. For this initial integration, provide one target Gameweek and its matching capture run ID per reconciliation dispatch.

The manifest retains `evidence_is_point_in_time=true` as an attestation, but eligibility is determined only after the independent auditor verifies the embedded raw bytes, replays official price reconstruction where used, validates the frozen recommendation hash and its source bindings, and matches finalized official manager records to either the hold baseline or the recommendation. Capture success alone is not forecast validation, decision value, or release eligibility.

## 16. Realised-points archive binding

A real evaluation record's `realised_points` source is not trusted merely because its payload hash is internally consistent. The evaluator requires its snapshot ID, SHA-256, capture timestamp and source URL to match the independently audited post-finalisation `event_live` archive for the same Gameweek. It then decodes that exact official event-live payload and compares every scored cohort player's minutes, yellow cards, red cards and total points against the normalized `realised_player_points` rows used by the hold-versus-recommendation scorer. Missing players, duplicate IDs, missing stats, altered rows, or an unrelated but otherwise valid archive fail closed.

This closes the scoring-input provenance chain: the frozen pre-deadline decision inputs are bound to the independently audited decision archives, while the realised outcomes are bound to the independently audited official event-live scoring archive. The official reconciliation batch still independently verifies manager gross points, transfer cost, autosubs and captain multiplier. Passing these integrity gates permits an event to be scored as a real decision-backtest candidate; it does not establish forecast quality, positive decision value, rank improvement or release eligibility.

## 17. Evaluation manager-state binding

For a real candidate, the evaluator decodes the manager-state archive whose raw bytes were independently audited and binds its manager/Gameweek identity and capture timestamp to the evaluation record. The archived 15-player squad, bank, free-transfer count, formation, starting XI, ordered outfield bench, reserve goalkeeper, captain, vice-captain and no-chip state must match the evaluator's hold baseline exactly. Each player's purchase price must match the archived manager state, and the archived selling price is independently recomputed using the official FPL half-profit rule. This prevents a valid, audited manager archive from being paired with a detached roster, lineup, budget or purchase-price table when scoring the recommendation against hold.

## 18. Official player-metadata binding

For a real candidate, the evaluator decodes the exact official bootstrap archive independently audited as the pre-deadline player-metadata source. Every player in the 15-player hold roster—and the incoming player for a transfer—is checked against that archive for official FPL element ID, position, club and current price. Missing or duplicate official IDs, incomplete metadata, or any detached evaluation attribute fails closed. This ensures the scoring roster and incoming transfer candidate cannot carry substituted position, club or price metadata while referencing an otherwise valid bootstrap archive.

## 18. Deterministic frozen-decision replay

The pre-deadline capture workflow re-executes the frozen M3 recommendation and independently reconstructs its canonical decision inputs from the archived raw sources. The replay step:

- requires the replay software commit to equal the commit recorded in the frozen evaluation candidate;
- decodes all three source archives, recomputes SHA-256, and requires each snapshot ID to be exactly bound to its digest;
- rebuilds the FPL Cat player-gameweek forecast records, provider identity, generation/capture/deadline timestamps, snapshot ID and coverage from the raw provider JSON;
- rebuilds each forecast player's official FPL price, position and club ID from the archived bootstrap elements and element-type dictionary, then compares the full normalized metadata list and provenance with the manifest;
- checks the provider deadline against the matching official bootstrap event deadline and verifies provider generation, provider capture and metadata capture are strictly pre-deadline;
- rebuilds manager state from the archived manager envelope and checks it against the canonical manifest; when target-Gameweek picks exist, it independently checks squad, starting XI, ordered outfield bench, reserve goalkeeper, captain, vice-captain, bank, purchase prices and chip state against those official picks;
- when target-Gameweek picks are unavailable, it checks the archived prior-picks/history source identities, independently reconstructs purchase prices from previous-Gameweek picks or from GW1 picks plus official transfer history/bootstrap, and verifies the target event is not a chip event;
- independently recalculates every manager selling price from the official current bootstrap price and the reconstructed purchase price using the FPL half-profit rule;
- reruns the same M3 personal-squad recommendation runner from the reconstructed-and-verified canonical inputs and compares the complete frozen decision and presented recommendation with the archived outputs;
- writes a replay report into the same immutable workflow artifact, labelled `DETERMINISTIC_RAW_AND_CANONICAL_INPUT_REEXECUTION`.

A failed reconstruction or replay fails the capture workflow and prevents a passing replay report from being archived. The post-Gameweek batch auditor now requires this replay report whenever a frozen predeadline recommendation is supplied. It independently binds the report to the exact manager, Gameweek, candidate software commit and frozen decision hash; the admission classifier and real scorer both require the audit's `predeadline_replay: VERIFIED` result. Missing replay reports, changed decision hashes, wrong commits or failed raw-archive flags fail closed and prevent decision-backtest admission. The replay is a source-to-canonical consistency and deterministic reproduction gate; it does not establish forecast accuracy, recommendation value, or release eligibility. The recorded commit is checked against the workflow's exact checkout commit; a later replay must check out that exact commit rather than silently using current branch code.

**Attestation boundary:** the free-transfer count remains manager-confirmed because the selected public FPL endpoints do not provide a direct authoritative pre-deadline value. In fallback capture modes, bank and intended XI/bench/captain state are also explicitly manager-attested rather than inferred from prior-week picks. The replay binds those values to the archived manager attestation and validates every field that the corresponding official source can independently corroborate; it does not claim to prove user-attested fields that are absent from official raw endpoints. The manager's squad identity and purchase prices are checked against the archived official picks/history source chain, and selling prices are recalculated from official bootstrap prices.



## 19. Real evaluation-record assembly

`assemble_m3_real_evaluation_record.py` assembles, but does not score or admit, a real candidate from the frozen predeadline recommendation, official reconciliation batch, independent archive audit and historical-evidence admission report. It fails closed unless the target event is `DECISION_BACKTEST_ELIGIBLE`, the exact frozen decision and deterministic replay are independently verified, and the manager/Gameweek identities agree across every input.

The assembler reads the archived official bootstrap, manager-picks and event-live payloads from the reconciled batch, verifies their raw SHA-256 hashes and matches their snapshot IDs, hashes, capture timestamps and source URLs to the independent audit. It requires the bootstrap to show both `finished=true` and `data_checked=true`; the bootstrap capture timestamp is recorded as the conservative observation time at which finalized status was confirmed. The event-live archive must have been captured no earlier than that observation. The scorer-ready realized-points cohort contains all 15 hold-baseline players plus the incoming player for a transfer decision (16 players), or the 15 owned players for HOLD.

Example after the target Gameweek has finalized and passed reconciliation, audit and admission:

```bash
python scripts/assemble_m3_real_evaluation_record.py \
  official-fpl-predeadline-m3-recommendation.json \
  --batch official-fpl-manager-reconciliation-batch.json \
  --audit-report official-fpl-manager-reconciliation-audit.json \
  --admission-report official-fpl-historical-evidence-admission.json \
  --output official-fpl-m3-evaluation-record.json

python scripts/evaluate_external_benchmark_decisions.py \
  official-fpl-m3-evaluation-record.json \
  --admission-report official-fpl-historical-evidence-admission.json \
  --audit-report official-fpl-manager-reconciliation-audit.json \
  --batch official-fpl-manager-reconciliation-batch.json \
  --output official-fpl-m3-evaluation-result.json
```

The assembler explicitly reports `scoring_performed=false` and `historical_evidence_admitted_by_assembler=false`. Only the evaluator can produce an event score, and even a real event score remains non-promotion evidence until the separate M3 acceptance protocol is satisfied. The personal risk profile is carried as metadata; no unvalidated CoVar or risk adjustment is applied.


## 20. Multi-Gameweek real-decision performance aggregation

`aggregate_m3_multigameweek_evaluations.py` consumes event-level outputs from the real evaluator; it does not consume raw candidate records and does not perform admission or scoring. Every input must already be labelled `REAL_CANDIDATE` with the exact real-event-scored status, remain explicitly non-promotion evidence, and include source provenance, provider identity, decision/input hashes, and internally consistent recommended/hold net points.

The aggregator fails closed on synthetic or unadmitted records, mixed manager IDs, duplicate manager/Gameweek/provider variants, duplicate evaluation-input hashes, malformed/non-finite scores, inconsistent net deltas, and invalid hit costs. Provider name/product/variant cohorts remain separate; it never invents a consensus or pools unlike forecast products.

For each provider cohort it reports:
- number of scored Gameweeks and action counts (HOLD/TRANSFER);
- positive, negative and neutral net-point deltas versus hold;
- cumulative, mean and median net-point delta versus hold;
- population standard deviation and positive-delta event rate;
- total transfer-hit points and separate mean deltas for HOLD and TRANSFER events.

The output is descriptive only. It sets both `promotion_eligible=false` and `historical_performance_validated=false`. It does not establish causal value, forecast accuracy, rank improvement, robustness, or release eligibility. Minimum sample-size requirements, uncertainty intervals, matched provider cohorts, and separate acceptance gates remain necessary before any promotion decision.

Example:

```bash
python scripts/aggregate_m3_multigameweek_evaluations.py \
  gw11-evaluation-result.json gw12-evaluation-result.json \
  --output m3-multigameweek-performance.json
```

Only independently admitted real event outputs from the same manager should be supplied. Do not include synthetic test results or unadmitted scoring-reconciliation-only events.
