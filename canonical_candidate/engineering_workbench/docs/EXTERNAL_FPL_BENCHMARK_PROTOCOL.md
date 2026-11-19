# External FPL Prediction Benchmark Protocol

Status: PRIVATE ARCHIVE ACTIVE / PROSPECTIVE CAPTURES UNDERWAY / NO PERFORMANCE CLAIM

## Purpose

Evaluate CTA-FPL models against real, established FPL prediction outputs using achievable, comparable standards. Do not choose an arbitrary RMSE target, reconstruct unavailable forecasts with hindsight, or require the project to beat every source on every metric.

## Independent benchmark sources

| Source | Benchmark role | Capture rule |
|---|---|---|
| FPL Review Free | Established FPL points forecast | Archive its published player-level expected points before the deadline |
| FPL Review Premium / Massive Data Model | Established FPL points forecast | Keep separate from Free; archive actual published values |
| FPL Forecaster | Direct FPL bookmaker-market-derived points forecast | Use its published FPL points output directly; do not rebuild its odds conversion |
| FPL Lucho | Direct FPL bookmaker-market-derived points forecast | Use its published FPL points / Odds xP output directly; retain variant identity |
| Sideline Quant | Independent player-level FPL points forecast with published uncertainty and event probabilities | Capture its exact GW JSON; retain fixture grain and provider-supplied probabilities separately |
| FPL Cat | Independent conventional FPL points forecast | Capture its public API output with computed_at, player ID and xP |
| FPLRogue | Independent player-level FPL points forecast | Capture the accepted release CSV with capture time, engine version and player ID |
| FPL Wildcard | Independent player-level FPL expected-points forecast with minutes and event probabilities | Capture its published CSV before deadline; retain raw snapshot only in the private archive; do not redistribute raw projections |

| Fantasy Football Scout | Established FPL points forecast, if player-level pre-deadline values are accessible | Archive only the actual pre-deadline output |
| Fantasy Football Pundit | Established FPL points forecast, if accessible | Archive only the actual pre-deadline output |
| Fantasy Football Fix | Established FPL points forecast, if accessible | Archive only the actual pre-deadline output |
| Fantasy Football Hub | Established FPL points forecast, if accessible | Archive only the actual pre-deadline output |
| The Fantasy Tool | Established FPL points forecast, if accessible | Archive only the actual pre-deadline output |
| Official FPL API ep_next | Native FPL reference baseline | Capture the API value before deadline; do not assume historical values are recoverable |

The initial market-derived benchmarks are **FPL Forecaster and FPL Lucho**. They are used as complete, directly relevant FPL implementations. We will not substitute NBA, lottery, generic bookmaker, or other non-FPL odds models, and will not create a separate odds-to-FPL-points converter for this benchmark.

### Initial access audit (19 November 2026)

| Source | What is verified | Remaining limitation / next action |
|---|---|---|
| FPL Forecaster | Public GW11 page; player directory states 672 projected players across GW11–15; bookmaker-derived team goals are translated into player xPts. | Public player page is filterable, but a bulk CSV/API export was not verified in this audit. Test whether a complete, timestamped player-level snapshot can be captured reliably before deadline. |
| FPL Cat | Public no-key JSON/CSV API; one row per FPL player; response includes gameweek, deadline, computed_at, player ID and xP. API documentation explicitly permits research and model benchmarking with attribution. | Capture endpoint added to the raw snapshot collector. Verify live response coverage and timestamp before accepting each GW as a valid benchmark observation. |
| FPL Lucho | Player Forecast page explicitly offers a CSV of every player's xP and fixtures for the next four GWs. Performance page separately reports served xP, raw model, Odds xP and FPL ep_next, and says the scored values are the last snapshots before deadline. | The bulk CSV's exact variant needs confirmation: do not assume it contains the separate Odds xP series. Determine whether Odds xP player-level values can be captured or reconstructed from an actual published output without rebuilding the model. |
| FPL Review | Documentation confirms CSV export with FPL ID, player details, EV and xMins. | Export is documented as a Premium feature. Capture Free only if an actual player-level export is available; keep tiers distinct. |
| Football Meets Data Fantasy Forecasts | Public accuracy page says forecasts are written down before deadline; current GW11 cohort is listed as 514 predictions awaiting outcomes. | Verify whether the complete player-level pre-deadline snapshot is downloadable or otherwise retrievable and preserve its exact cutoff. |
| FPL Form | Public documentation offers generated CSV exports of predicted points and optional appearance probabilities. | Check account/access requirements and terms; preserve attribution and do not redistribute raw exports. |

The first practical capture candidates are FPL Lucho's published CSV, FPL Wildcard's published CSV, FPL Review's export where accessible, and Football Meets Data if its archived pre-deadline rows can be retrieved. FPL Forecaster remains a priority market-derived benchmark, but bulk capture is not yet verified. No collector should be implemented against an assumed endpoint.

Source availability, terms, paywall access, output granularity, update cadence, and historical archive availability must be checked before implementation. A source is not considered benchmarked merely because its website is known. If a source does not expose a player-level forecast in time, record it as unavailable for that deadline rather than estimating or fabricating its value.

## Forecast freeze and timestamp policy

For each source, preserve the raw forecast snapshot and a normalized player-level table. Record at minimum:

- source name, product/tier, forecast variant and source version where available;
- season, gameweek, FPL player ID, fixture ID;
- forecast value and units (expected FPL points);
- forecast generated/retrieved timestamp in UTC;
- official deadline and first fixture kickoff in UTC;
- retrieval URL, retrieval method, raw snapshot path, content hash and retrieval status;
- player/fixture mapping status and any normalization notes;
- missing-forecast reason, distinct from a numerical zero;
- post-deadline actual FPL points and minutes, joined only after the deadline.

Freeze each snapshot before the official deadline. Never overwrite a frozen forecast with a later update. If multiple snapshots are captured, label them as distinct forecast horizons (for example, T-minus-24h and final pre-deadline) and compare only like with like. Store raw source output where possible so normalized values can be audited.

A missing forecast is null with a reason/status, never silently converted to zero. Report source coverage alongside every score. Primary source comparisons use the common player-GW intersection; a separate coverage report describes the full eligible universe. Do not hide missingness by changing the evaluation population without reporting it.

## Evaluation population and fairness

- Match the exact season, gameweek, player, fixture, forecast horizon and target definition.
- Compare all models on the same player-GW rows for each head-to-head result.
- Publish at least two views: (1) common player-GW cohort and (2) source-specific coverage with missingness shown.
- Where external services publish only selected players, do not treat unlisted players as zero forecasts.
- Distinguish player-GW point prediction from squad/lineup optimization. FPL Bench-style squad scoring is a useful separate decision benchmark, not a replacement for player-level scoring.
- Use official realized FPL points as the outcome target. Preserve all outcomes, including exceptional hauls and blanks.

## Metrics

### Point forecast accuracy
- MAE and RMSE;
- signed bias / mean error;
- median and upper-quantile absolute error;
- rates and magnitudes of large errors (for example, absolute error >= 6 and >= 8);
- tail contribution to total squared error.

RMSE is important for large misses but is not the sole success criterion. MAE and RMSE must be presented together with bias and tail diagnostics.

### Ranking and FPL decision utility
- Spearman rank correlation;
- NDCG@10 and NDCG@15;
- top-10 / top-15 overlap;
- realized points among top-ranked picks;
- captain-pick performance and top-k regret where the forecast supports those decisions;
- a separate constrained squad/starting-XI decision evaluation when forecasts and rules permit.

### Probabilistic quality
Only score distribution metrics when a source actually supplies a probability distribution or enough probability outputs to define the event:
- Brier score and log loss for explicitly defined events;
- ranked probability score for points distributions;
- calibration and reliability for haul/blank thresholds.

Do not invent probability distributions from a single expected-points number and then score them as if the source supplied them.

## Statistical procedure

- Use chronological walk-forward evaluation; never random-split future and past player-GWs.
- Report results by season and forecast horizon as well as pooled results.
- Use player-season clustered bootstrap intervals for paired model differences; preserve gameweek/fixture structure where feasible.
- Track sample size, coverage and confidence intervals. A small early-season lead is descriptive, not evidence of durable superiority.
- Avoid choosing a winning model from a single metric or a single gameweek.

## Meaning of conventional historical FPL prediction

In this project, **conventional historical FPL prediction** means the established family of FPL points prediction methods used by specialist tools such as FPL Review and other established FPL forecasting services. It is not a requirement that we create a separate in-house model and call that the conventional benchmark.

This family generally uses historical FPL/player performance and availability information (for example points, minutes, appearances, goals, assists, xG/xA where available), plus relevant fixture, team and role context. Some services additionally incorporate bookmaker markets or other external information. The exact inputs differ by provider and must not be assumed without provider-specific documentation. FPL Forecaster and FPL Lucho are the direct market-derived examples in our benchmark set.

Our conventional 2PM-Transformer is **our own experimental implementation** of a conventional-history-based FPL predictor. It must be evaluated against the external services; it is not itself the external benchmark. The previously developed in-house statistical model may remain as a legacy internal comparator, but it should not be confused with the conventional approach used by established services.

## Relationship to our model tracks

Keep these as independent rows in the benchmark:

1. Simple persistence baselines (last GW, prior-3/prior-5 averages, and other justified simple baselines).
2. Legacy in-house conventional statistical model, retained as an internal comparator where useful.
3. External conventional FPL prediction services, including FPL Review and other accessible player-level forecasts.
4. Standalone integrated CTA A+B+C predictor.
5. Standalone conventional-history 2PM-Transformer.
6. Optional A/B/C-augmented 2PM-Transformer, only after tracks 4 and 5 have independently established results.

FPL Forecaster and FPL Lucho are external benchmarks, not components of CTA or 2PM. Do not blend their predictions into our model unless a separate, pre-registered experiment later demonstrates incremental value on a strictly held-out chronological sample.

## Achievable benchmark gates

1. **Capture validity:** demonstrate repeatable pre-deadline capture, timestamps, player mapping, immutable snapshots and coverage accounting.
2. **Comparable evaluation:** produce matched-cohort reports against the accessible external services and internal baselines.
3. **Competitive parity:** establish whether a model is broadly competitive with relevant services, without requiring it to win every metric.
4. **Evidence of improvement:** seek modest, repeatable gains in point accuracy, calibration or FPL decision utility, supported by paired uncertainty intervals across multiple gameweeks/seasons.
5. **Promotion:** only consider a model for recommendations after point-in-time validity, leakage controls, robustness and practical decision value are demonstrated.

Do not set a numerical RMSE target in advance. First collect a sufficiently large, comparable prospective benchmark sample. Then set a realistic target based on the observed baseline distribution, uncertainty and intended FPL use.

## Initial implementation sequence

1. Add a versioned source registry and normalized snapshot schema.
2. Complete the source-specific capture audit above, prioritizing FPL Lucho CSV, FPL Review export, Football Meets Data snapshots and a reliable FPL Forecaster player-level capture path.
3. Build a capture process that saves raw snapshots and normalized rows without modifying prior snapshots.
4. Add validation for deadline timestamps, duplicate player-fixture keys, missingness, units and player identity.
5. Join official outcomes only after the gameweek and generate matched-cohort reports.
6. Expand to other sources only where actual pre-deadline forecasts can be captured reliably.

No external benchmark score or model promotion is claimed until this process has run prospectively.


## Follow-up live-output access audit (19 November 2026, 15:47 UTC)

This follow-up checks the actual public forecast outputs and capture surfaces, not inferred model methodologies.

| Source | Actual output/access verified | Capture status and next action |
|---|---|---|
| FPL Lucho — served xP | The Player Forecast page exposes a direct all-player CSV export at `/export/predictions.csv`; its page says the CSV contains the same served xP values shown on the site for each player and fixture over four GWs. The performance page distinguishes this served Lucho xP from Raw, Odds xP and FPL ep_next. | **Output surface verified; automated raw capture not yet validated.** The CSV endpoint was identified, but the browser fetch could not render its `text/csv` response. Test direct HTTP retrieval in the collector. Treat the CSV as the served Lucho xP series only. Do not label it Odds xP. The performance page's Odds xP series is a distinct forecast variant; its player-level export path remains unverified. |
| FPL Forecaster | Public GW11 player page lists 672 projected players over GW11–15 and exposes individual player expected-points outputs. | **Bulk capture unverified.** The public player page is available, but no bulk CSV/API was established in this audit. Do not scrape a partial visible ranking and call it the full player universe. |
| Sideline Quant | Public GW11 JSON endpoint returns all 672 player-fixture rows, FPL player and fixture IDs, expected points, uncertainty, minutes/start probabilities and other forecast fields. Payload includes `generated_at=2026-11-18T03:33:09Z`, GW11 deadline `2026-11-21T11:00:00Z`, and 10,000 simulations. The provider page says each GW has a dedicated URL and old live feeds are removed after the feed advances. | **Strong capture candidate; immediate immutable archiving required.** Capture the raw JSON now and on each future GW before deadline; record the exact retrieval time and SHA-256. Preserve the provider's player-fixture grain and sum fixtures to player-GW only under an explicit aggregation rule. Keep provider's own stated eligible populations separate from our common-cohort scoring. |
| FPLRogue | Current accepted GW11 release exposes a downloadable 672-player CSV and a capture/update timestamp (19 Nov 2026, 09:45 GMT), plus a browseable archive page describing append-only frozen releases. The archive currently lists 13 releases from GW3–9 with dated CSV links. | **Strong capture candidate.** Download the current GW11 CSV and test its columns/player IDs. Archive page confirms historical release snapshots exist, but GW11 archive availability and exact pre-deadline timestamp semantics must be verified. Keep engine/version and each release distinct. |
| FPL Wildcard | Projection dataset page exposes a downloadable player-GW CSV with xPts, xMins and optional start/appearance/blank/haul probabilities; its data page reports a 19 Nov 2026 14:45 UK update and model v11. | **Capture candidate; snapshot policy needs verification.** Confirm the GW11 CSV's actual timestamp and whether dated immutable archives are available. Terms currently state no redistribution licence; retain only what is necessary for internal research and attribution/provenance. |
| FPL Vault | Public xPts page exposes an export CSV and a current table of 459 players; page describes the forecast as FPL-data-driven and not betting-odds-based. | **Secondary capture candidate.** Verify complete player coverage, forecast timestamp, and whether a stable pre-deadline snapshot can be frozen. |
| FPL Form | Existing documentation confirms predicted-points CSV export with optional appearance probabilities and clarifies the probability-adjusted forecast column. | Access, timestamp and complete player-GW capture still need verification. |

### Variant and comparison rules clarified by the audit

- A source's published CSV is benchmarked as the exact forecast it contains. Do not infer that a CSV includes a second variant merely because the website displays one elsewhere.
- FPL Lucho's served xP, raw model, and Odds xP are separate series. The served CSV is not evidence that the separate Odds xP series is exportable.
- Sideline Quant publishes fixture-grain forecasts; preserve those rows as supplied and document any player-GW aggregation. Do not compare fixture-grain and player-GW values without a consistent aggregation.
- Public performance scorecards are useful source context, not substitutes for our own matched-cohort evaluation. Their populations, thresholds and exclusions may differ.
- A visible forecast is not yet a valid benchmark observation until its exact raw output, generation/retrieval timestamp, deadline, player mapping, variant and hash are archived.
- The newly identified Sideline Quant and FPLRogue outputs expand the practical benchmark candidate set. They do not replace the specifically approved FPL Forecaster and FPL Lucho market-derived benchmarks.

### Immediate capture priority

1. Freeze the current Sideline Quant GW11 JSON and FPLRogue GW11 CSV while their published releases are still available.
2. Validate and freeze the FPL Lucho served-xP CSV; separately investigate whether its published Odds xP player rows can be retrieved.
3. Re-test FPL Forecaster for a complete player-level bulk output path; if none exists, record it as visible but not yet machine-capturable.
4. Add the remaining candidate sources only after confirming complete player-level coverage and pre-deadline snapshot reproducibility.
5. Do not calculate or report our own comparative scores until the captured snapshots have been joined to official realized points on matched player-GW cohorts.


## Raw snapshot collector implementation (19 November 2026)

A first capture-only implementation now exists:

- `scripts/capture_external_fpl_forecasts.py` retrieves the public Sideline Quant GW-specific JSON, FPLRogue accepted projection CSV, and FPL Lucho served-xP CSV.
- Raw response bytes are written unchanged; the manifest records retrieval time, requested/final URL, content type, source-reported generation time where available, row count, variant label and SHA-256.
- The Lucho export is explicitly labelled **served xP, not assumed Odds xP**. The collector does not derive Odds xP or translate bookmaker markets.
- Sideline Quant rows remain fixture-grain; no player-GW aggregation is performed during capture.
- Third-party CSV columns are preserved and inventoried rather than assumed. Their player IDs, point columns, grain and variant must be audited before normalization/scoring.
- The manual/push-triggered workflow `.github/workflows/cta-external-fpl-forecast-capture.yml` keeps raw bytes on the ephemeral runner for validation and publishes only the non-player-level capture manifest. Raw provider forecasts are not uploaded to this public repository or its Actions artifacts.

**Retention status:** restricted raw provider forecasts are not retained in this public repository or its public Actions artifacts. The access-controlled private archive `uasir/CTA-FPL-Private-Archive` is active for the FPL Wildcard research snapshot. Other providers remain subject to their own source-specific retention checks. The public manifest records capture provenance and hashes only; it cannot be used to reconstruct raw forecasts.

The collector's first automated run is a capture validation, not a performance evaluation. It must fail closed if a source returns HTML, an empty response, an invalid gameweek or malformed data. It does not convert missing rows to zero.


### FPL Cat access verification (19 November 2026)

FPL Cat documents `GET https://fplcat.com/api/v1/projections` and `?format=csv`. The JSON output includes the current gameweek, deadline, model `computed_at`, and one player object per FPL player with the official FPL ID and `xp`. Its documentation states that the API is intended for model benchmarking and allows research use with attribution. The capture script now archives the exact JSON response as a distinct FPL Cat forecast variant; it does not combine it with any other provider.


### FPL Wildcard access audit (19 November 2026)

FPL Wildcard exposes a direct CSV download at `https://fplwildcard.com/data/projections/current.csv`. Its documentation describes one row per selectable player per projected gameweek, with `gameweek`, `profile_url`, `xpts`, `xmins` and optional probability fields. The page reported GW11, 19 November 15:30 UK projection refresh and model v11. This is a useful additional independent forecast output.

The CSV endpoint and schema have been verified. FPL Wildcard is captured only into the access-controlled private archive for non-redistributive internal research; it is not included in the public capture pipeline. The source explicitly grants no redistribution licence for the dataset, so raw CSVs/player-level values must not be republished or uploaded into public artifacts. This private-research decision is not a claim that the provider granted permission or that private storage overrides its terms. Any external-facing report must use permitted aggregate findings and attribution.


### Public-repository artifact handling correction (19 November 2026)

The repository is public. An initial capture workflow uploaded raw third-party forecast CSV/JSON files as public-repository Actions artifacts. Those two artifacts were identified for deletion and the workflow was changed to delete them and upload only the non-player-level manifest. The FPL Wildcard dataset, whose page states that no redistribution licence is granted, was removed from the public capture pipeline entirely. Do not treat the temporary initial artifact as a valid long-term archive. Raw snapshots must remain runner-local until a private archive and provider-specific retention permissions are established.


## Private archive implementation update (19 November 2026)

The private repository `uasir/CTA-FPL-Private-Archive` is active. Its FPL Wildcard capture workflow completed successfully for 2026/27 GW11, and the private identity-normalization workflow has now completed.

- Capture time: 2026-11-19T16:15:38Z, before the GW11 deadline.
- Raw CSV: 5,660 rows spanning GW11–GW20; 566 player rows per gameweek.
- GW11 slice: 566 rows, 566 unique provider profile URLs, and no missing/non-numeric `xpts` values.
- Forecast variant: provider-published `xpts`; do not relabel as bookmaker-derived Odds xP.
- SHA-256: `0cb8f8cdaebfe8f62414551122d31566b4db6329a2bce1d8665954bb0a035264`.
- Private archive commit: `ba1921a63090076209f38af76b58f0acef095116`.
- Raw file and manifest remain in the private archive. The public project retains only provenance/hash metadata and aggregate validation findings.

This establishes capture and retention, not forecast accuracy. GW11 outcomes must be joined after completion, and only the GW11 rows from this pre-deadline snapshot should enter the GW11 accuracy cohort. Later gameweeks in the same CSV are prospective snapshots for their respective future deadlines only if the file was genuinely published and frozen before each deadline; the 19 November capture timestamp must remain attached to all of them.


### Private GW11 identity normalization update (19 November 2026)

The archived GW11 FPL Wildcard slice was resolved against the official FPL
`bootstrap-static` player/team records using exact normalized full name plus
team short name only.

- 566/566 source rows resolved to official FPL player IDs.
- 566 unique IDs; zero duplicate IDs; zero unresolved or ambiguous rows.
- All 566 xPts and xMins values remained numeric.
- The private audit records the official bootstrap capture time and SHA-256.
- Normalized player-level output and its audit remain private; this public
  repository records only aggregate validation results.

A private evaluator is implemented but deliberately refuses to score until
the official FPL event is marked finished and the source manifest confirms
capture before the deadline. No FPL Wildcard accuracy result is claimed yet.


### Private historical FPL Wildcard archive (GW1–GW10, 19 November 2026)

The private archive collector retrieved all ten frozen public gameweek pages and retained the normalized player-level rows privately. The public ledger records only each page's SHA-256, source forecast timestamp and aggregate row count; no raw or derived player-level projection rows are published.

- 50 ranked rows are exposed by each archived gameweek page: 500 player-GW forecasts in total.
- 497/500 rows resolved to official FPL IDs and had numeric actual points; three unresolved identities remain unscored.
- GW1–GW3 pages identify Model v10; GW4–GW10 identify Model v11.
- The pages explicitly label the forecasts as saved before deadline and frozen after deadline. The source page update timestamps were preserved.
- The private pooled top-50 subset result is MAE 3.055, RMSE 3.799, forecast-minus-actual bias -0.403, Spearman 0.096 and top-10 overlap 0 (pooled player-GW keys).

**Critical coverage qualification:** these are provider-selected top-50 rows, not the complete player universe. They must not be compared directly with the provider's all-player scorecard or with an all-player CTA/2PM metric. The next comparison must intersect our model's point-in-time forecasts with the exact same resolved player-GW rows and report the matched sample. A separate all-player comparison remains pending until full historical provider coverage is verified.

The private archive now contains the acquired rows, per-gameweek source hashes/audits, pooled/per-gameweek scorecard and an identical-cohort comparison script. The comparator expects model predictions with `model,gameweek,fpl_player_id,predicted_points` and reports both model and FPL Wildcard on identical rows, including player-cluster bootstrap intervals. CTA/2PM comparison is pending model forecast export; no model-versus-provider result is claimed yet.


### First private FPL Wildcard / 2PM comparison (aggregate only)

A retrospective model reconstruction was run against the provider's frozen GW2–GW10 top-50 pages. The exact shared cohort contains 449 resolved player-GWs across nine gameweeks. Model predictions were trained on the ten prior seasons and use lagged 2026/27 features; the current API vintage is not independently frozen at each original deadline, so this is explicitly retrospective rather than a prospective forecast comparison.

| Forecast | MAE | RMSE |
|---|---:|---:|
| FPL Wildcard published xPts | 3.066 | **3.843** |
| 2PM-Transformer reconstruction | **2.982** | 4.099 |
| Direct Ridge | 3.010 | 4.155 |
| Calibrated two-part | 3.118 | 4.512 |
| Last-five persistence | 3.567 | 4.525 |

The Transformer MAE difference versus Wildcard is -0.084 (paired player-cluster bootstrap 95% CI -0.202 to +0.042; inconclusive). Its RMSE difference is +0.256 (95% CI +0.147 to +0.369; worse). No promotion decision is supported. Provider top-50 selection makes this a conditional cohort only; it is not an all-player ranking benchmark. Raw and derived player-level rows remain private.


A second GW11 full-player capture was completed at 2026-11-19T16:49:46Z (566 GW11 rows; 5,660 rows across GW11–GW20; SHA-256 `87561803e2d7632a2fb7103b6de742dab1b3aef8dea2a607f22818aff15de39d`). All 566 GW11 player identities resolved against the official FPL bootstrap. Raw and normalized player-level rows remain private. An automated private workflow now checks every six hours and captures the next FPL gameweek when it is within 48 hours of deadline; unchanged source hashes are skipped. This is a prospective capture process, not yet a forecast-accuracy result.


### evmax full-player benchmark (GW4–GW7, captured 19 November 2026)

Source: [evmax open FPL dataset](https://evmax.ai/data/) and its [public accuracy ledger](https://evmax.ai/fpl/accuracy/). The dataset publishes every projected player with official FPL element IDs, xPoints, and full simulated point distributions; the provider states projections are frozen before deadline and licenses the data CC BY 4.0 with attribution. Attribution: `Data: evmax (https://evmax.ai), CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/`.

Private archive capture:
- GW4: 655 players; source generated 2026-09-12T10:47:57Z; SHA-256 `d8ee41e1a954de1c2058b15bdf7f922a3f7aa33b8ae3dd6cdd17a9054d90fc4f`.
- GW5: 659 players; source generated 2026-09-17T13:12:25Z; SHA-256 `594a374adab9616bc726b990bc45af38960ceb0707b19b0594b5fc0c575900c8`.
- GW6: 667 players; source generated 2026-10-09T14:26:59Z; SHA-256 `fb44ea1dbfcda752f3d32bdd739a073d136739bcc04cf0519f7aa680aef0b7f4`.
- GW7: 667 players; source generated 2026-10-14T15:08:42Z; SHA-256 `279bb9664a494b98486fd2f0fc014cf685403ace56ea3a9407a4bd214e67a220`.
- 2,648 forecast rows; all 2,648 official FPL IDs resolved. Original projections and accuracy JSON remain in the private archive.

The independent evaluator uses official FPL `event/{gw}/live/` points only after the event is finished. Its MAE reproduces the provider's published per-week scorecard to rounding: GW4 1.207, GW5 1.148, GW6 1.103, GW7 1.080. Pooled: 2,648 player-GWs, MAE 1.1343, RMSE 2.1080, bias -0.1619, Spearman 0.6914. The provider's captured FPL `ep_next` baseline has MAE about 1.215 on 2,632 exact-name matched rows in the full EVMax cohort (2,631 in the 2PM common subset).

First identical all-player comparison against the retrospective 2PM reconstruction (2,647 common player-GWs):
- EVMax: MAE 1.1344, RMSE 2.1084.
- 2PM-Transformer: MAE 1.6340, RMSE 2.2754; model-minus-EVMax MAE delta +0.500 (95% player-cluster bootstrap CI +0.451 to +0.549), RMSE delta +0.167 (CI +0.118 to +0.216).
- Conventional two-part: MAE 1.1776, RMSE 2.3095.
- Direct Ridge: MAE 1.2345, RMSE 2.1796.
- Last-five persistence: MAE 1.2437, RMSE 2.2843.

This is a retrospective reconstruction from the current official FPL API, not an archived CTA pre-deadline forecast. No model is promoted from this result. The provider's full-player coverage makes this a much stronger comparison cohort than FPL Wildcard's historical top-50 pages.

**Distribution-count audit:** GW4–GW6 player distributions each contain 50,000 counts; GW7 distributions contain 10,000 counts per player, although the provider's method description says 50,000 simulations per gameweek. The evaluator normalizes each distribution by its own count total and records the count; the GW7 discrepancy is flagged for source clarification rather than silently assuming equal simulation counts.


A held-out prior-season affine expected-points calibration was also tested. It was fitted only on the latest 20% of prior training gameweeks (slope 1.0455, intercept -0.0023). It did not improve the 2026/27 reconstruction: across 5,890 current-season player-GWs, raw Transformer MAE/RMSE were 1.586/2.221 and affine-calibrated were 1.626/2.226. On the FPL Wildcard selected top-50 cohort, the affine variant's MAE was 2.985 and RMSE 4.053, versus raw 2.982/4.099; it remained significantly worse than Wildcard on RMSE. No promotion. A separate expanding current-season calibration using only earlier gameweeks is being evaluated; it will remain retrospective because historical feature vintages were not frozen at each deadline.


The prior-season affine-calibrated Transformer was also scored on the 2,647-row EVMax common cohort: MAE 1.6748, RMSE 2.2820, worse than raw Transformer (1.6340/2.2754) and EVMax (1.1344/2.1084). Its paired model-minus-EVMax 95% intervals were +0.491 to +0.591 MAE and +0.125 to +0.223 RMSE. This calibration variant is not promoted.


### 2PM walk-forward calibration revalidation

The standalone 2PM CI walk-forward run completed successfully: 9 expanding-season folds, 214,956 player-GWs, 6,645 player-season clusters.

- Raw 2PM-Transformer: MAE 1.1552, RMSE 2.1413.
- Held-out affine-calibrated 2PM-Transformer: MAE 1.1434, RMSE 2.1400.
- Conventional two-part: MAE 1.1583, RMSE 2.1514.
- Affine vs two-part paired player-season bootstrap: MAE delta 95% CI [-0.0164, -0.0132]; MSE delta CI [-0.0607, -0.0377].

The affine calibrator is fitted on held-out prior-training gameweeks only, so this is a valid walk-forward historical improvement. However, the same calibrator worsened the 2026/27 retrospective external comparisons. Treat this as evidence of historical improvement with a current-season transfer problem, not grounds for promotion. All 2PM variants remain research-only.


The captured official FPL `ep_next` baseline has MAE 1.2153 and RMSE 2.3497 on 2,632 exact-name-matched player-GWs in the full EVMax cohort (2,631 in the 2PM common subset). Paired player-cluster bootstrap versus EVMax in the 2PM common subset gives ep_next-minus-EVMax MAE difference 95% CI +0.032 to +0.127 and RMSE difference CI +0.170 to +0.304. Four names per GW were unmatched and retained as missing; no fuzzy name join was used.


### Expanding season-adaptive 2PM calibration on FPL Wildcard

The private reconstruction now includes a prequential affine calibration variant: for each target GW, calibration is fitted only on earlier current-season player-GWs (GW2 falls back to prior-season calibration). On the 449-row Wildcard common top-50 cohort, season-adaptive MAE/RMSE are 3.028/3.914 versus Wildcard 3.066/3.843. Paired player-cluster intervals for model-minus-Wildcard are MAE [-0.124, +0.045] and RMSE [-0.028, +0.172], both including zero. It closes much of the RMSE gap but does not establish superiority. Keep research-only. Its all-player EVMax comparison is pending.


### Season-adaptive 2PM calibration on EVMax all-player cohort

On 2,647 common player-GWs, the expanding calibration variant scored MAE 1.3117 and RMSE 2.1314 versus EVMax 1.1344/2.1084. Paired player-cluster bootstrap for model-minus-EVMax: MAE delta +0.177 (95% CI +0.144 to +0.211); RMSE delta +0.023 (CI -0.017 to +0.063). It is significantly worse on MAE but statistically indistinguishable on RMSE in this four-GW sample. It improves substantially over raw Transformer (1.6340/2.2754) and prior-season affine (1.6748/2.2820), while conventional two-part remains better on MAE (1.1776) but worse on RMSE (2.3095). This remains a retrospective reconstruction; no promotion. Future frozen prospective forecasts are required.


### FPL Wildcard GW1–GW10 official outcome verification and first 2PM comparison (private archive)

The private historical collector independently compared each provider-page actual-points value with official FPL `/api/event/{gw}/live/` `stats.total_points`, and now uses official points for final scoring only when the event is marked finished.

- All ten events are officially finished.
- 497/497 resolved player-gameweek actuals match official FPL exactly; zero mismatches.
- Three unresolved identities remain unscored; no zero imputation.
- Source actuals, official live response hashes and finished-state checks remain in the private archive.

First model comparison, GW2–GW10, on the exact common subset of 449 provider-top-50 player-GWs (49 GW2; 50 each GW3–GW10):
- FPL Wildcard: MAE 3.066, RMSE 3.843.
- 2PM-Transformer retrospective reconstruction: MAE 2.982, RMSE 4.099.
- Transformer-minus-Wildcard MAE paired player-cluster 95% CI: [-0.202, +0.042], inconclusive.
- Transformer-minus-Wildcard RMSE paired player-cluster 95% CI: [+0.147, +0.369], worse.
- Within-gameweek top-10 overlap over the nine top-50 cohorts: Transformer 17/90; FPL Wildcard 28/90.

**Limitations:** this is a provider-selected top-50 subset, not an all-player cohort. The 2026/27 model forecasts were reconstructed from a current official FPL API snapshot, not frozen before each historical deadline; historical API vintage is not independently verified. This is not prospective evidence and does not justify promotion. The full-player GW11 prospective Wildcard capture remains separate.
