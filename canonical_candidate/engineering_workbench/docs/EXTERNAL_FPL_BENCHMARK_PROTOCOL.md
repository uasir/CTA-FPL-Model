# External FPL Prediction Benchmark Protocol

Status: RAW CAPTURE VALIDATION IMPLEMENTED / PRIVATE ARCHIVE PENDING / NO PERFORMANCE CLAIM

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
| FPL Cat | Independent conventional FPL points forecast | Capture its public player-level JSON/CSV output and retain computed_at and API version |
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

The first practical capture candidates are FPL Lucho's published CSV, FPL Review's export where accessible, and Football Meets Data if its archived pre-deadline rows can be retrieved. FPL Forecaster remains a priority market-derived benchmark, but bulk capture is not yet verified. No collector should be implemented against an assumed endpoint.

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

**Important retention limitation:** raw provider forecasts are currently captured and hashed on the ephemeral runner but are not durably archived. A durable, access-controlled private research archive is still required. The public manifest records capture provenance and hashes only; it cannot be used to reconstruct raw forecasts.

The collector's first automated run is a capture validation, not a performance evaluation. It must fail closed if a source returns HTML, an empty response, an invalid gameweek or malformed data. It does not convert missing rows to zero.


### FPL Cat access verification (19 November 2026)

FPL Cat documents `GET https://fplcat.com/api/v1/projections` and `?format=csv`. The JSON output includes the current gameweek, deadline, model `computed_at`, and one player object per FPL player with the official FPL ID and `xp`. Its documentation states that the API is intended for model benchmarking and allows research use with attribution. The capture script now archives the exact JSON response as a distinct FPL Cat forecast variant; it does not combine it with any other provider.


### FPL Wildcard access audit (19 November 2026)

FPL Wildcard exposes a direct CSV download at `https://fplwildcard.com/data/projections/current.csv`. Its documentation describes one row per selectable player per projected gameweek, with `gameweek`, `profile_url`, `xpts`, `xmins` and optional probability fields. The page reported GW11, 19 November 15:30 UK projection refresh and model v11. This is a useful additional independent forecast output.

The CSV endpoint and schema have been verified, but this source is **not included in the public capture pipeline**. The source explicitly grants no redistribution licence for the dataset, so raw CSVs/player-level values must not be republished or uploaded into public artifacts. It can only be considered for a future private research archive after provider-specific terms and access are checked. Any external-facing report must use permitted aggregate findings and attribution.


### Public-repository artifact handling correction (19 November 2026)

The repository is public. An initial capture workflow uploaded raw third-party forecast CSV/JSON files as public-repository Actions artifacts. Those two artifacts were identified for deletion and the workflow was changed to delete them and upload only the non-player-level manifest. The FPL Wildcard dataset, whose page states that no redistribution licence is granted, was removed from the public capture pipeline entirely. Do not treat the temporary initial artifact as a valid long-term archive. Raw snapshots must remain runner-local until a private archive and provider-specific retention permissions are established.
