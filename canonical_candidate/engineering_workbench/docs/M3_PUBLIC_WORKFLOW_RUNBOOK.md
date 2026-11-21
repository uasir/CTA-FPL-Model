# M3 Public Workflow Runbook

The personal M3 evidence workflows are intentionally usable in this public repository. Manager IDs, confirmed squad state, frozen recommendations, and evidence artifacts are public. No repository secrets or private-repository setting are required.

## 1. Capture one pre-deadline decision

Run **Actions → Capture pre-deadline FPL decision evidence → Run workflow**.

Inputs:

- `gameweek`: target Gameweek number.
- `manager_team_id`: defaults to `421025`; change if needed.
- `season`: defaults to `2026-27`; must match the FPL Cat snapshot season.
- `manager_state_json`: confirmed manager state at the time of the decision.
- `field_eo_capture_run_id`: optional successful run ID from the provisional field-EO capture workflow for the same Gameweek.

The manager-state JSON contract is:

```json
{
  "squad_15": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
  "bank": 0.9,
  "free_transfers": 1,
  "formation": "4-3-3",
  "starting_xi": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
  "bench_order": [12, 13, 14],
  "reserve_goalkeeper_id": 15,
  "captain_id": 10,
  "vice_captain_id": 11,
  "chip_state": "NONE"
}
```

The numeric IDs above are schema examples only. Replace every ID with the current official FPL element ID for the corresponding player. The squad must contain 15 unique IDs; the XI, three ordered outfield substitutes and reserve goalkeeper must partition those 15 players. Captain and vice-captain must be distinct squad members. Bank is in £m. Only `chip_state: "NONE"` is supported by this initial decision contract.

The workflow captures the provider forecast, official player metadata, and official manager context; validates the point-in-time/deadline constraints; runs the conventional personal-squad decision; freezes the decision hash; and independently replays the decision with the same optional field-EO artifact. The field-EO artifact is provisional descriptive context, not observed post-lock EO and not a calibrated probability of beating the field.

The output artifact is named:

`predeadline-decision-evidence-manager-<team-id>-gw<gameweek>-run<workflow-run-id>`

It contains the evidence manifest, frozen recommendation, and replay report. The capture is not historical decision-evaluation eligible until official scoring is finalized and the independent admission/reconciliation checks pass.

## 2. Capture provisional field EO

Run **Actions → Capture provisional pre-deadline field EO → Run workflow**, or allow its scheduled capture to run. It emits aggregate player-level field exposure only. Use the successful workflow run ID as `field_eo_capture_run_id` in step 1. If no valid artifact is available, omit that optional input; the conventional recommendation still runs without provisional field context.

## 3. Reconcile completed Gameweeks

Run **Actions → Reconcile official FPL manager Gameweeks → Run workflow**.

- `manager_team_id`: defaults to `421025` and must match the manager in the evidence artifact.
- `gameweeks`: comma-separated completed Gameweeks, e.g. `12`.
- `decision_evidence_run_id`: optional run ID of the pre-deadline capture workflow. The artifact name includes manager ID and Gameweek, and the independent audit verifies that manager identity, timing, hashes, recommendation and replay all match.

Historical manager reconciliation without a pre-deadline decision artifact can still run, but it cannot be admitted as a genuine pre-deadline decision backtest. Do not attach a post-deadline capture as pre-deadline evidence.

## 4. Interpretation and gates

- A successful capture means evidence was captured and the recommendation was reproducibly frozen; it does not mean the model is validated or release-eligible.
- M3 historical decision evaluation requires finalized official points, successful reconciliation, archive/hash audit, and historical evidence admission.
- Forecast-performance evaluation (M2) and recommendation-product evaluation (new M4) remain deferred until the upcoming Gameweek's official scores are available.
- CoVar remains a separate research/validation gate and cannot silently change expected points, legality, transfer logic, or the frozen conventional decision.
