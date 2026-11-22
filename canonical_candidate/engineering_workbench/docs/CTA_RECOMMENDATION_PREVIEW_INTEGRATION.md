# CTA recommendation preview integration

Status: **EXPLORATORY INTEGRATION IMPLEMENTED / M2 VALIDATION AND M4 PRODUCT EVALUATION PENDING**

## Purpose

Connect the independently trained CTA five-Gameweek candidate forecast to both CTA recommendation products without changing the conventional FPL Cat/Sideline Quant path.

The integration emits two distinct products:

1. `general_cta_market`: squad-independent medium-term player rankings over the five-Gameweek cumulative CTA expected-points forecast.
2. `gameweek_cta_markets`: separate squad-independent one-Gameweek rankings and captaincy shortlists for each target Gameweek.
3. `cta_informed_personal_squad`: an optional squad-specific one-Gameweek diagnostic preview using the first target-Gameweek player forecast panel and an explicit manager squad snapshot.

## Data flow

`cta_forecast_recommendation_adapter.py` verifies the CTA candidate bundle, official bootstrap identity mapping, five consecutive Gameweeks, model/source manifest hashes, point-in-time timing and candidate-only safeguards. It emits:

- A five-Gameweek cumulative shared forecast for general-market ranking.
- Five separate player-Gameweek panels for squad-specific use, with each player's cumulative five-GW points and minutes reconciled to the sum of those panels.
- Current official price, team, position and FPL element identity on every panel record.
- Explicit `EXPLORATORY_ONLY`, `decision_weight=0`, `production_eligible=false` and `covar_used=false` metadata.

`run_cta_recommendation_products.py` then calls the existing deterministic recommendation engines:

- `general_market_engine.recommend_general_market` receives only shared forecast fields and filters. The cumulative five-GW ranking omits single-GW captaincy; each weekly panel gets its own one-GW market and captaincy shortlist. No manager/squad state is passed, and these products can run without manager context.
- `personal_squad_engine.recommend_personal_squad` receives only the first target-Gameweek panel plus the independently captured shared manager-state input. The same manager-state capture is an input to the conventional FPL Cat path, but CTA does not read, depend on, or consume the conventional recommendation output. It does not receive the five-Gameweek aggregate as single-Gameweek expected points.
- `build_personal_squad_product` wraps the squad-specific preview in the distinct `cta_informed_personal_squad` product contract.

## Decision and release limits

This integration is a structural and exploratory preview, not a release of CTA recommendations.

- CTA M2 forecast validation remains pending; recommendation status stays exploratory.
- The squad-specific engine currently performs a one-transfer, one-Gameweek diagnostic. Its output is not an actionable transfer decision.
- A five-plus-Gameweek transfer evaluation, independent forecast validation and governed M4 product promotion are still required before a decision can become eligible.
- General CTA rankings are independent of the manager's squad and must remain invariant to personal state.
- CTA expected points are never blended with conventional FPL Cat or Sideline Quant forecasts.
- LiveFPL observed EO remains separate from poll-implied EO. The adapter accepts only verified post-lock observed EO and labels it retrospective/descriptive; it must not be treated as information available for a pre-deadline decision or added to expected points.
- CoVar remains excluded: zero decision weight, not production eligible and not used by either recommendation engine.
- The conventional recommendation product remains a separate M3/M4 path.

## Execution

The general CTA market can be generated without a manager file:

```bash
python canonical_candidate/engineering_workbench/scripts/run_cta_recommendation_products.py \
  --bundle-dir /path/to/verified/cta-bundle \
  --now-utc 2026-11-22T12:05:00Z \
  --output /path/to/general-cta-market.json
```

To generate a manager-specific preview, pass the independent shared manager-state capture. This is the same source input used by the conventional FPL Cat path; it contains the verified 15-player squad, purchase prices, bank, free transfers, risk profile, formation and baseline starting XI. The CTA runner validates its manager identity, target Gameweek, capture timestamp and squad completeness. It does not require or accept a conventional recommendation output:

```bash
python canonical_candidate/engineering_workbench/scripts/run_cta_recommendation_products.py \
  --bundle-dir /path/to/verified/cta-bundle \
  --manager-context-capture /path/to/private-manager-state-capture.json \
  --now-utc 2026-11-22T12:05:00Z \
  --output /path/to/private-output/cta-recommendation-previews.json
```

For controlled tests only, `--manager-context` can accept a validated manager-context object directly; the real-data paired replay uses the timestamped capture artifact above.

Optional post-lock EO can be supplied using `--eo-snapshot`. The manager context and full personal recommendation output are private manager data: do not publish them as public workflow artifacts. General CTA rankings do not depend on manager context.

## Real-data replay evidence

The real CTA-owned forecast archive was replayed through the recommendation runner without manager context:

- Forecast source run: `45059662965` (successful).
- Forecast artifact: `cta-five-gw-candidate-forecast`, GitHub artifact ID `14769361745`.
- Forecast snapshot: `ee6ad9f5a78c958a4851f573d95a212479982196c608333ae92c9f45a22ce181`.
- Season/horizon: 2026-27, GW12-GW16.
- Forecast universe: 674 players.
- Latest recommendation replay run: `45070950617` (successful).
- Latest recommendation artifact: `cta-general-recommendation-preview-gw12-16`, GitHub artifact ID `14772998594`.

The replay produced:
- A five-Gameweek cumulative overall ranking and value ranking.
- Five separate one-Gameweek general-market rankings, each with its own captaincy shortlist.
- No squad-specific output because no manager context was supplied.
- No EO input and no CoVar input.

This is a real-data integration/replay pass, not forecast-performance validation. The output remains `EXPLORATORY_ONLY`, with zero decision weight and `production_eligible=false`, because M2 validation and independent M4 outcome evaluation remain pending.

## Tests

- Adapter tests verify the candidate-only bundle, five-GW horizon, stable FPL identity mapping, provenance, optional EO rules, season consistency and exact cumulative-to-panel reconciliation.
- Runner tests verify cumulative and weekly horizons, per-Gameweek captaincy, general rankings without manager context and invariant to personal-state changes, independent shared manager-capture validation, timestamp/Gameweek alignment, baseline-XI integrity, partial manager-context rejection, and zero CoVar decision weight.


## Five-Gameweek squad-specific CTA diagnostic

The CTA personal-squad preview now has a separate five-Gameweek HOLD-versus-
single-transfer diagnostic in `cta_multi_gameweek_squad_evaluator.py`. It
consumes the five ordered `gameweek_panels` already present in the verified
CTA candidate bundle and evaluates the manager's fixed baseline starting XI
over all five weeks. It enumerates affordable, same-position, outfield
transfers, applies the FPL selling-price rule using recorded purchase prices,
checks the three-player club limit, and reports weekly and cumulative expected
points deltas net of any transfer hit.

This does not mislabel the five panels as five independent provider snapshots
and does not fabricate fixture-level forecasts. Weekly lineup/captaincy
decisions remain distinct from the cumulative transfer comparison. The
diagnostic requires all 15 squad rows to carry exact `purchase_price` values;
if this manager-state evidence is absent, the personal product records an
explicit blocked-input status rather than estimating sale proceeds.

The diagnostic remains exploratory, zero-weight, non-production, and
CoVar-free. It evaluates one transfer at a time against a fixed baseline XI;
it does not optimize transfer sequences, future lineups, captaincy, chips,
future prices, or transfer-flexibility option value. It is not an M4 promotion
or a claim of validated performance. M2 forecast validation and M4 outcome
evaluation remain pending.


The five-Gameweek squad transfer assessment is sourced from the **same
immutable CTA candidate forecast bundle** as the general CTA market. Its
output carries the identical `forecast_snapshot_id`, `model_version`, and
ordered five-Gameweek horizon; it does not launch or consume a second forecast.
The result exposes `recommendation_basis=FIVE_GAMEWEEK_CUMULATIVE_EXPECTED_POINTS`
and a diagnostic `recommended_action` (HOLD/TRANSFER). This cumulative action
is separate from the one-Gameweek XI, bench and captaincy preview. Candidate
transfers must have forecast rows in all five panels with stable position,
team and price metadata; partial-horizon candidates are excluded and
inconsistent metadata blocks evaluation.

Manager purchase prices are sourced from the shared manager-state capture (also supplied to the conventional FPL Cat path):
exact prior-Gameweek official FPL picks when the squad identity matches and
that Gameweek was not a Free Hit, otherwise chronological season-history
reconstruction from GW1 picks and official transfer history. The five-GW
evaluator requires the resulting per-player purchase_price values and blocks
rather than approximating when they are absent.


### Paired real-data replay input contract

The shared manager-state capture is the common input contract for both
recommendation paths. It carries the complete verified 15-player
`squad_snapshot`, purchase prices, bank, free transfers, risk profile,
formation and baseline starting XI. The conventional FPL Cat product and the
CTA product each consume this input independently. CTA does not download,
parse, or depend on the conventional recommendation artifact.

A manually triggered workflow,
`.github/workflows/cta-m4-paired-personal-replay.yml`, downloads the exact
five-GW CTA forecast artifact and the shared manager-state capture artifact.
It reads only the `manager-context-*.json` file from the manager capture
artifact, runs the personal and general CTA products from the same forecast
bundle, and publishes only a privacy-safe manifest. The manager-specific
recommendation report remains ephemeral in the job workspace. The capture
must target GW12 and be timestamped before the GW12 deadline; the archived
GW11 capture is intentionally rejected.