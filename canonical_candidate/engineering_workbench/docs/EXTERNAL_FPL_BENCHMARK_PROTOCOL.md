# External FPL Prediction Benchmark Protocol

Status: APPROVED DESIGN / IMPLEMENTATION PENDING / NO PERFORMANCE CLAIM

## Purpose

Evaluate CTA-FPL models against real, established FPL prediction outputs using achievable, comparable standards. Do not choose an arbitrary RMSE target, reconstruct unavailable forecasts with hindsight, or require the project to beat every source on every metric.

## Independent benchmark sources

| Source | Benchmark role | Capture rule |
|---|---|---|
| FPL Review Free | Established FPL points forecast | Archive its published player-level expected points before the deadline |
| FPL Review Premium / Massive Data Model | Established FPL points forecast | Keep separate from Free; archive actual published values |
| FPL Forecaster | Direct FPL bookmaker-market-derived points forecast | Use its published FPL points output directly; do not rebuild its odds conversion |
| FPL Lucho | Direct FPL bookmaker-market-derived points forecast | Use its published FPL points / Odds xP output directly; retain variant identity |
| Fantasy Football Scout | Established FPL points forecast, if player-level pre-deadline values are accessible | Archive only the actual pre-deadline output |
| Fantasy Football Pundit | Established FPL points forecast, if accessible | Archive only the actual pre-deadline output |
| Fantasy Football Fix | Established FPL points forecast, if accessible | Archive only the actual pre-deadline output |
| Fantasy Football Hub | Established FPL points forecast, if accessible | Archive only the actual pre-deadline output |
| The Fantasy Tool | Established FPL points forecast, if accessible | Archive only the actual pre-deadline output |
| Official FPL API ep_next | Native FPL reference baseline | Capture the API value before deadline; do not assume historical values are recoverable |

The initial market-derived benchmarks are **FPL Forecaster and FPL Lucho**. They are used as complete, directly relevant FPL implementations. We will not substitute NBA, lottery, generic bookmaker, or other non-FPL odds models, and will not create a separate odds-to-FPL-points converter for this benchmark.

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

## Relationship to our model tracks

Keep these as independent rows in the benchmark:

1. Conventional persistence baselines (last GW, prior-3/prior-5 averages, and other justified simple baselines).
2. Existing conventional FPL statistical model.
3. Standalone integrated CTA A+B+C predictor.
4. Standalone conventional 2PM-Transformer.
5. Optional A/B/C-augmented 2PM-Transformer, only after tracks 3 and 4 have independently established results.
6. External FPL services listed above.

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
2. Audit whether FPL Forecaster, FPL Lucho and FPL Review expose capturable player-level forecasts before the next deadline; record access and coverage limitations.
3. Build a capture process that saves raw snapshots and normalized rows without modifying prior snapshots.
4. Add validation for deadline timestamps, duplicate player-fixture keys, missingness, units and player identity.
5. Join official outcomes only after the gameweek and generate matched-cohort reports.
6. Expand to other sources only where actual pre-deadline forecasts can be captured reliably.

No external benchmark score or model promotion is claimed until this process has run prospectively.
