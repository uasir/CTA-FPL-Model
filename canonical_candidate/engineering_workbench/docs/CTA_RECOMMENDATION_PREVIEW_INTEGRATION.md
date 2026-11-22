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
- `personal_squad_engine.recommend_personal_squad` receives only the first target-Gameweek panel plus an explicit manager context. For paired conventional-vs-CTA runs, the preferred CLI path extracts that exact context from a same-season, same-Gameweek, same-deadline conventional M3 run. It does not receive the five-Gameweek aggregate as single-Gameweek expected points.
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

To generate a manager-specific preview on the exact same squad/budget/transfer state as the conventional M3 run, pass that private conventional run output directly. The adapter checks the run type, season, target Gameweek and deadline, then verifies the manager context is internally consistent:

```bash
python canonical_candidate/engineering_workbench/scripts/run_cta_recommendation_products.py \\
  --bundle-dir /path/to/verified/cta-bundle \\
  --conventional-run /path/to/private/conventional-m3-run.json \\
  --output /path/to/private-output/cta-recommendation-previews.json
```

Alternatively, supply a private manager-context file:

```bash
python canonical_candidate/engineering_workbench/scripts/run_cta_recommendation_products.py \
  --bundle-dir /path/to/verified/cta-bundle \
  --manager-context /path/to/private-manager-context.json \
  --now-utc 2026-11-22T12:05:00Z \
  --output /path/to/private-output/cta-recommendation-previews.json
```

Optional post-lock EO can be supplied using `--eo-snapshot`. The manager context and full personal recommendation output are private manager data: do not publish them as public workflow artifacts. General CTA rankings do not depend on manager context.

## Real-data replay evidence

The real CTA-owned forecast archive was replayed through the recommendation runner without manager context:

- Forecast source run: `45059662965` (successful).
- Forecast artifact: `cta-five-gw-candidate-forecast`, GitHub artifact ID `14769361745`.
- Forecast snapshot: `ee6ad9f5a78c958a4851f573d95a212479982196c608333ae92c9f45a22ce181`.
- Season/horizon: 2026-27, GW12-GW16.
- Forecast universe: 674 players.
- Recommendation replay run: `45070408218` (successful).
- Recommendation artifact: `cta-general-recommendation-preview-gw12-16`, GitHub artifact ID `14773081160`.

The replay produced:
- A five-Gameweek cumulative overall ranking and value ranking.
- Five separate one-Gameweek general-market rankings, each with its own captaincy shortlist.
- No squad-specific output because no manager context was supplied.
- No EO input and no CoVar input.

This is a real-data integration/replay pass, not forecast-performance validation. The output remains `EXPLORATORY_ONLY`, with zero decision weight and `production_eligible=false`, because M2 validation and independent M4 outcome evaluation remain pending.

## Tests

- Adapter tests verify the candidate-only bundle, five-GW horizon, stable FPL identity mapping, provenance, optional EO rules, season consistency and exact cumulative-to-panel reconciliation.
- Runner tests verify cumulative and weekly horizons, per-Gameweek captaincy, general rankings without manager context and invariant to personal-state changes, exact conventional manager-state reuse and alignment, partial manager-context rejection, and zero CoVar decision weight.
