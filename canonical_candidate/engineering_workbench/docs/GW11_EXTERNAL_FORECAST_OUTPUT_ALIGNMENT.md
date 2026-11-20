# GW11 external forecast output alignment audit

Status: DESCRIPTIVE OUTPUT COMPARISON ONLY / NOT AN ACCURACY EVALUATION

Capture: 2026-11-19 15:57:29 UTC  
Target: 2026/27 GW11  
Common player IDs: 672  
Sources: Sideline Quant, FPL Cat, FPLRogue accepted xpts_v1, FPL Lucho served xP

## Capture integrity

Each of the four source outputs contained 672 rows and 672 unique FPL player IDs. The common player-ID intersection was 672/672. No player IDs were missing or duplicated in these four captured outputs.

- Sideline Quant: fixture-level JSON, 672 rows, `player_id`, `fixture_id`, `xP`. GW11 is a single fixture per player in this snapshot; do not generalize that to double gameweeks.
- FPL Cat: player-gameweek JSON, 672 players, `id`, `xp`.
- FPLRogue: player-gameweek CSV, 672 rows, `player_id`, `next_gw_xpts`, release capture time and `xpts_v1` model version.
- FPL Lucho: player-gameweek CSV, 672 rows, `id`, `xp_gw11`. This is the served xP output, not the separately reported Odds xP series.

Raw-output SHA-256 values for the exact 15:57 capture:

| Source | SHA-256 |
|---|---|
| Sideline Quant | `9e47b20962f04d6ae607de809e91f9c6681cea6dde2c690ad66ffbb518f04b5a` |
| FPL Cat | `423e19a26e53d67c02c89a4201dd903777cce575fa657bdbe2d36a6e3e93d097` |
| FPLRogue | `bd63ab6ecafc84cbd94abde8d407869efe4036296c48c1f854a897047dc740f4` |
| FPL Lucho served xP | `6c26ced90560eb66a02d717415c8e16d6576f51ffc8015a00a3b849cc51de8ef` |

## Pairwise agreement across actual forecasts

All pairwise comparisons use the same 672 FPL player IDs. Mean absolute xP difference is the average absolute difference between two providers' published expected-points values. Top-k overlap is the number of common players in each provider's own ranking.

| Provider pair | Spearman rank correlation | Pearson correlation | Mean absolute xP difference | Top 10 overlap | Top 20 overlap |
|---|---:|---:|---:|---:|---:|
| Sideline Quant – FPL Cat | 0.968 | 0.970 | 0.235 | 7/10 | 11/20 |
| Sideline Quant – FPLRogue | 0.909 | 0.896 | 0.591 | 4/10 | 12/20 |
| Sideline Quant – FPL Lucho | 0.948 | 0.957 | 0.268 | 7/10 | 12/20 |
| FPL Cat – FPLRogue | 0.939 | 0.918 | 0.526 | 7/10 | 16/20 |
| FPL Cat – FPL Lucho | 0.973 | 0.973 | 0.222 | 9/10 | 15/20 |
| FPLRogue – FPL Lucho | 0.949 | 0.908 | 0.525 | 6/10 | 15/20 |

## Interpretation

1. The providers' outputs are broadly aligned in their overall ordering, but not interchangeable.
2. The largest observed disagreement in this snapshot is between Sideline Quant and FPLRogue: Spearman 0.909, mean absolute xP difference 0.591, and only four shared names in the top ten.
3. FPL Cat and FPL Lucho are the closest pair in this snapshot: Spearman 0.973 and 9/10 top-ten overlap.
4. These are **forecast-to-forecast agreement statistics**, not evidence of which provider is more accurate. No GW11 realized points existed at capture time, so no provider is declared better.
5. We will score each actual output against official realized FPL points after the gameweek, on the same player-GW cohort. Source coverage and variants remain separate.

## Retention and reproducibility note

The initial raw snapshot was inspected locally to verify schemas, unique IDs and common coverage. Because the repository is public and not all providers grant explicit redistribution permission, raw provider files were removed from public Actions artifacts. The public repository retains this aggregate audit and the hash-only capture ledger; raw snapshots are not currently durably archived. A private, access-controlled archive is still required for repeatable prospective evaluation.
