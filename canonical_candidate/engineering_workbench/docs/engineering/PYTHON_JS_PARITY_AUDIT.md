# Python–JavaScript Feature Parity Audit

**Status:** Engineering specification  
**Stage:** CTA feature-engineering validation  
**Predecessors:** StatsBomb event ingestion; event/360 joining; pressure and support feature generation; JavaScript reproduction  
**Next gate:** 34-match audit, then independent xT/VAEP baselines and CTA incremental evaluation

> For direct parity with the existing CTA-FPL v1.0.2 core, use
> `CTA_CORE_PARITY_CONTRACT.md` and
> `config/cta_core_parity_contract.json`. That contract compares possession,
> player-per-single-match-run, and xT-cell outputs at their actual grains.
> The event-key examples below apply only to event-level implementations; do
> not reshape possession or player aggregates into event-keyed rows.

## 1. Objective

Demonstrate that the Python and JavaScript implementations produce equivalent row-level outputs from the same canonical match inputs. The audit must detect differences in row identity, event/360 joins, feature definitions, null handling, numeric calculations, and aggregation.

Parity is a correctness gate, not evidence that the features are predictive. Predictive value is evaluated separately during CTA incremental testing.

## 2. Scope

The first parity pass covers:

- StatsBomb event ingestion and canonical event identity.
- Event ordering and possession identifiers.
- Event-to-360 frame association and coverage indicators.
- Pressure features.
- Support / teammate-availability features.
- Any derived columns already emitted by both implementations.
- Match- and possession-level aggregates derived from those columns.

The audit must not silently expand or shrink scope based on whichever columns happen to match. Maintain an explicit feature registry (Section 5).

## 3. Inputs and execution contract

Both implementations must receive the same immutable input snapshot for each match:

1. Raw event records.
2. 360 frames and their event associations.
3. Match metadata and competition / season identifiers.
4. A versioned feature configuration.
5. A declared implementation version or commit SHA.

Record input file hashes, match IDs, row counts, schema versions, and run timestamps. The two implementations must not independently fetch or preprocess different source data during a parity run.

## 4. Canonical row identity and join integrity

Use the source event ID as the primary row key wherever it is present and unique. If a source does not provide a usable event ID, define and document a deterministic composite key before comparison (for example: match ID, period, event index, and source sequence).

Required checks:

- No duplicate canonical keys within a match output.
- No unexplained missing or additional keys between runtimes.
- Stable event ordering after sorting by the canonical key / documented event order.
- Explicit accounting for events without a linked 360 frame.
- Explicit accounting for 360 frames that cannot be linked to an event.
- Join cardinality must match the declared relationship; accidental many-to-many joins fail the audit.

Do not compare rows by array position alone.

## 5. Feature registry

Maintain a machine-readable registry for every audited feature with:

| Field | Requirement |
|---|---|
| `feature_name` | Stable canonical name |
| `definition_version` | Version of the mathematical / logical definition |
| `data_type` | Numeric, integer, boolean, categorical, or identifier |
| `nullable` | Whether null is valid |
| `unit` | Metres, seconds, count, probability, dimensionless, or not applicable |
| `source_fields` | Raw fields and derived dependencies |
| `aggregation` | None or explicit aggregation rule |
| `tolerance_class` | Exact, numeric, or domain-specific |

A feature is not considered covered merely because a similarly named column exists in both outputs. Its definition and dependencies must match.

## 6. Comparison rules

### 6.1 Structural checks

- Canonical key sets must be identical.
- Required columns must exist in both outputs.
- Data types must be compatible with the registry.
- Row counts and per-match counts must reconcile.
- Null counts and null locations must reconcile, except for explicitly approved runtime-specific representations that normalize to the same canonical null.

### 6.2 Exact comparisons

Identifiers, booleans, categorical labels, event types, period labels, possession IDs, and join-presence flags require exact equality after canonical normalization.

Do not coerce missing values to zero, false, empty strings, or a valid category.

### 6.3 Numeric comparisons

Use a documented tolerance per feature. Initial default for continuous features:

- Relative tolerance: `1e-7`
- Absolute tolerance: `1e-9`

These are starting defaults, not permission to hide systematic drift. Counts and integer-valued features require exact equality. Probability-like or bounded features may require domain-specific bounds and must remain within their mathematical range.

For each numeric feature report:

- Number and percentage of compared values.
- Exact-match count.
- Within-tolerance count.
- Maximum absolute error.
- Maximum relative error where defined.
- Mean absolute error and RMSE.
- Signed mean error (bias).
- 50th, 95th, and 99th percentile absolute error.
- Worst offending row keys and values.

### 6.4 Null and non-finite handling

Normalize null representations before comparison, while preserving the distinction between null, zero, and not-applicable. NaN and infinity must be reported explicitly; they must not be silently dropped from metrics. Any non-finite value not permitted by the feature definition fails the gate.

## 7. Required audit outputs

Produce the following artifacts for every run:

1. **Run manifest:** input hashes, match IDs, runtime versions, feature-registry version, and configuration.
2. **Schema report:** missing, additional, and incompatible columns.
3. **Row-integrity report:** duplicate, missing, and extra canonical keys.
4. **Join report:** event/360 matched and unmatched counts with coverage rates.
5. **Feature parity report:** per-feature metrics and pass/fail status.
6. **Mismatch sample:** bounded examples keyed by canonical event ID.
7. **Summary:** overall gate, failed checks, and reproducible command / configuration.

Reports must be machine-readable (JSON or CSV) as well as human-readable (Markdown).

## 8. Match-level and 34-match validation

First establish row-level parity on the pilot match (Bayer Leverkusen–Stuttgart). The recorded pilot snapshot contains 3,771 events, 176 possessions, 32 players, and 84.46% 360 coverage; verify these figures against the immutable input manifest before using them as audit denominators.

After the pilot passes, run the same unchanged audit over the agreed 34-match sample. Do not tune tolerances match-by-match. Any exception must be documented, justified, and approved in the feature registry or audit configuration before rerunning.

The 34-match report must include per-match results and a pooled result. A pooled pass must not conceal a failed individual match.

## 9. Acceptance criteria

The parity gate passes only when all of the following hold:

- 100% canonical row-key agreement for the declared comparison population.
- Zero duplicate canonical keys.
- Zero unexplained missing or extra rows.
- Exact equality for identifiers, booleans, and categorical features.
- All numeric features meet their registered tolerances.
- Null locations reconcile and all non-finite values are explained and permitted.
- Event/360 join counts and coverage reconcile.
- All audited features are present in the registry and have matching definitions.
- Reports and manifests are reproducible from the recorded inputs and versions.

A failed gate blocks downstream CTA evaluation. Do not repair parity by dropping difficult rows, widening tolerances without evidence, or changing feature definitions in only one runtime.

## 10. Failure triage

Classify each mismatch as one of:

1. Input snapshot / version mismatch.
2. Canonical key or ordering mismatch.
3. Join cardinality or event/360 association mismatch.
4. Feature-definition mismatch.
5. Null / type / coercion mismatch.
6. Floating-point or rounding mismatch.
7. Aggregation-window or grouping mismatch.

Fix the underlying cause in the relevant implementation, then rerun the full affected audit. Preserve the failed report for regression tracking.

## 11. Downstream sequence

1. Complete pilot Python–JavaScript parity.
2. Freeze the feature registry and audit configuration.
3. Execute the 34-match audit.
4. Build independent xT and VAEP baselines on the same time-safe data splits.
5. Measure CTA incremental value over those baselines.
6. Only after those gates pass, proceed to FPL feature mapping and FBL integration.

**Important:** Parity establishes implementation consistency. It does not establish causal validity, calibration, predictive lift, or FPL usefulness; those require separate evaluation.

## 12. Raw-data contract preflight (added)

Before feature generation, validate each raw source independently against a versioned contract. The current event and 360 contract files are explicitly marked templates because the actual provider payload has not yet been inspected. A preflight failure blocks ingestion. A preflight pass confirms only the declared schema and row-level constraints; it does not prove event/360 join correctness, feature validity, or runtime parity. Null canonical keys and duplicate canonical keys are hard failures.

## 13. Independent baseline implementation (xT prototype)

A provider-neutral empirical grid xT trainer has been added. Its action schema is deliberately configurable. It treats each canonical action row as one attempt, estimates shot probability and goal rate by start cell, and estimates continuation value from successful pass/carry destination cells. Failed moves and non-configured actions contribute no continuation value. The baseline is unsmoothed and should be treated as an engineering reference, not a calibrated production model. Train only on training matches and freeze the grid before held-out scoring. The xT implementation must not be used for CTA incremental-lift claims until source mappings, split strategy, and baseline evaluation are locked.
