# 2PM Transformer — Paper Architecture Compliance Specification

**Status:** specification / implementation plan  
**Governing publication:** Wiechno, Duch and Bartosik (2026), *Modeling Fantasy Premier League Player Performance with a Two-Component Poisson Mixture Transformer*, ICAART 2026, pp. 3093–3100, DOI: 10.5220/0014358000004052.  
**Repository branch audited:** `feat/four-layer-2pm-transformer-evaluation`  
**Scope:** player-level FPL points forecasting only. This document does not authorize model promotion, production use, PR merge, or changes to M3/M4 decision logic.

## 1. Architectural decision

The published 2PM-Transformer paper is the governing architecture for the repository's 2PM forecasting model. The existing minutes/points categorical model is retained as a historical experimental baseline; it is not to be relabelled as the paper's 2PM-Transformer.

Responsibilities remain separated:

- **2PM Transformer:** estimates a predictive distribution for a player's next-Gameweek FPL points and derives player-level forecast quantities from it.
- **M3 Integrated Decision Engine:** consumes forecasts and performs EV/EO, coverage, variance, CoVar and portfolio decision calculations.
- **M4:** delivers the established recommendation products. The 2PM-powered squad-specific product is named **2PM Squad Recommendations**.

The forecasting model must not implement transfers, squad selection, captaincy, ownership/EO, CoVar, or recommendation policy.

## 2. What the paper specifies

The paper describes:

1. A sequence of five consecutive matches played by a player, with no more than 21 days between selected matches.
2. A 116-feature vector for each match, representing player performance and FPL-relevant actions.
3. An encoder-only Transformer with input embedding, positional encoding, self-attention and feed-forward processing.
4. A two-component Poisson mixture output with parameters:
   - (p): probability assigned to component 1;
   - (lambda_1): Poisson rate for component 1;
   - (lambda_2): Poisson rate for component 2.
5. Maximum-likelihood training by minimizing mixture negative log-likelihood.
6. Training-only maximum-likelihood initialization of the Poisson rates to improve convergence.
7. A chronological train/validation/test design, rather than random row splitting.
8. A paper-specific treatment of negative FPL point totals: negative totals are treated as non-appearance because a Poisson distribution has support only on non-negative integers.

The paper reports a tuned configuration of 8 attention heads, embedding dimension 256, batch size 32, dropout approximately 0.22, and training up to 60 epochs with early stopping (patience 5; minimum improvement 0.0001). The paper discusses tuning the number of layers but does not clearly report the selected layer count. These values are a reproduction starting point, not guaranteed optimal settings for our data.

## 3. Current repository implementation — baseline, not compliant

The audited files on this branch are:

- `canonical_candidate/engineering_workbench/scripts/two_pm_transformer.py`
- `canonical_candidate/engineering_workbench/scripts/evaluate_two_pm_transformer_walk_forward.py`

The current model has a shared temporal encoder with two categorical heads: five minutes bands and six conditional-points bands. It trains with cross-entropy losses and reconstructs expected points using empirical band representatives. The evaluator currently uses a six-snapshot history window, conventional lagged FPL features plus optional position indicators, and a one-layer configuration (the model class default is two layers). This is materially different from the paper's two-component Poisson mixture output.

**Preserve this implementation and its historical results as a baseline.** Do not silently change its semantics or overwrite its artifacts when introducing the paper-governed implementation.

## 4. Paper-governed data contract

### 4.1 Forecasting observation

One supervised example represents one player's next FPL Gameweek outcome:

- Input: exactly five eligible prior player-match observations.
- Target: that player's actual FPL points for the forecast Gameweek.
- Prediction cutoff: strictly before the official FPL deadline for that target Gameweek.
- All input features must be available by that cutoff. No target-match or post-deadline information may enter the sequence.

### 4.2 Sequence construction

- Select five consecutive matches actually played by the player, not five calendar Gameweeks.
- Enforce the paper's maximum 21-day gap between selected observations. The handling of a longer gap must be explicit: do not silently bridge it. The initial reproduction rule is to start a new eligible history after the gap and require five new qualifying observations.
- Order observations chronologically.
- Preserve match identifiers, player identifiers, competition, kickoff timestamp, source snapshot, and feature provenance alongside the tensor.
- Do not treat a blank Gameweek as a played match. A player's no-appearance in the target Gameweek remains a target outcome, not a fabricated historical match.
- Double Gameweeks require an explicit mapping rule: each actual match is a match-level historical observation; the target remains the official player-Gameweek FPL points total. Document and test this grain conversion.
- No cross-season or cross-competition history may be joined without an explicit player identity and competition mapping. The first implementation may be EPL-only and must be labelled an adaptation of the paper's multi-league data design.

### 4.3 Feature contract

The paper specifies 116 features per match and describes categories including minutes, position, goals, assists, penalties, cards, own goals, saves, tackles, blocks, clearances, interceptions, pass types, shot/goal-creating actions and save percentage.

The paper's accessible feature description does not provide a sufficiently complete, machine-readable 116-column dictionary. Therefore:

- Do not invent the missing feature names or claim a feature set is paper-identical without evidence.
- Create a versioned 116-feature mapping only after locating the authors' full schema or documenting a source-backed reconstruction.
- For every feature, record canonical name, definition, source/provider, unit, match grain, availability timestamp, missingness semantics, transformation, and whether it is directly observed or derived.
- Distinguish unavailable, structurally inapplicable, and true zero values.
- Feature selection and preprocessing parameters must be fitted using training data only and frozen for validation/test/inference.
- Do not add ABC or other experimental feature families to this paper-governed model unless a separately versioned ablation is approved. The default 2PM remains conventional football/FPL feature forecasting.

### 4.4 Point-in-time safety

The existing evaluator's history builder currently selects rows with Gameweek less than or equal to the target Gameweek. Before reuse, audit whether those rows contain lagged-only values or same-Gameweek realized statistics. The new builder must use match timestamps and deadline cutoffs, not assume that a row labelled with a Gameweek is automatically safe.

Fail closed if any input observation or feature was published after the target deadline.

## 5. Model architecture

The paper-governed model must implement:

1. Input projection/embedding from the 116-feature per-match vector to the model embedding width.
2. Positional encoding for the five ordered observations.
3. Encoder-only Transformer self-attention and feed-forward blocks.
4. A documented sequence-to-context representation. The paper does not fully specify pooling/selection mechanics; choose and record a deterministic implementation, then test it. Do not imply the pooling detail is explicitly dictated by the paper.
5. A distribution head producing three unconstrained raw outputs transformed into valid parameters:
   - (p = \operatorname{sigmoid}(a)), with (0 < p < 1);
   - (lambda_1 = \operatorname{softplus}(b) + \epsilon);
   - (lambda_2 = \operatorname{softplus}(c) + \epsilon).
6. The architecture must not contain a minutes classification head or a separate conditional-points classification head. Those belong to the retained legacy baseline, not the paper-governed model.

The paper reports 8 heads, width 256, batch 32, dropout ~0.22, up to 60 epochs, patience 5 and minimum improvement 0.0001. Implement these as the reproduction configuration, with the layer count marked **unspecified by paper** and selected through a documented, training/validation-only decision. Do not infer a four-layer model merely from a branch name.

## 6. Predictive distribution and forecast interface

For integer points (k \geq 0), the probability mass function is:

```text
P(Y=k | X) = p * Pois(k; lambda_1) + (1-p) * Pois(k; lambda_2)
```

The expected points forecast is:

```text
EP = p * lambda_1 + (1-p) * lambda_2
```

The predictive variance is:

```text
Var(Y) = p*(lambda_1 + lambda_1^2)
       + (1-p)*(lambda_2 + lambda_2^2)
       - EP^2
```

The interface should expose, at minimum:

- player and target-Gameweek identifiers;
- expected points;
- mixture probability (p);
- rates (lambda_1) and (lambda_2);
- predictive variance and standard deviation;
- probabilities for useful thresholds (for example 6+, 8+, 10+), calculated from the mixture PMF/survival function;
- model/version, feature-schema version, training cutoff, forecast as-of time, data snapshot identifiers/hashes, and eligibility/quality status.

The interface should preserve the full distribution parameters. Do not collapse the output to one sampled point value. Sampling may be used for diagnostics or simulation, but the canonical player forecast is the analytic expectation and predictive distribution.

**Gumbel-Softmax note:** the paper describes a Gumbel-Softmax sampling mechanism, but the written description does not make its role in the final point estimate fully clear. We must inspect the authors' intended implementation or document our interpretation. It must not replace the deterministic expectation in the production forecast interface.

## 7. Training objective and numerical requirements

For observed non-negative integer target (y):

```text
NLL(y) = -log( p * Pois(y; lambda_1)
             + (1-p) * Pois(y; lambda_2) )
```

Implementation requirements:

- Compute the mixture log-likelihood with log-sum-exp/logaddexp for numerical stability.
- Use `lgamma(y + 1)` for the log-factorial term.
- Validate finite outputs, positive rates, valid mixture probabilities, non-negative integer targets and finite loss/gradients.
- Initialize component rates using maximum-likelihood estimates from the fitting partition only. Document how the two initial component rates are separated/assigned; do not use validation/test targets.
- Use deterministic seeds and record optimizer, learning rate, weight decay, scheduler, gradient clipping and early-stopping configuration.
- Keep training, validation and test partitions chronological and disjoint by target Gameweek. Any calibration must use a separate earlier calibration block and must not leak into fitting or test outcomes.

## 8. Negative FPL points — explicit reproduction decision

A Poisson mixture cannot assign probability to negative points. The paper's reproduction choice is to map negative actual point totals to the non-appearance/zero target for model training.

We will preserve two clearly separated datasets/labels:

1. **Paper-faithful target:** apply the paper's negative-to-non-appearance mapping for the reproduction experiment. Retain a flag identifying every transformed observation and preserve the original actual points.
2. **Sensitivity target:** retain original negative actual points for evaluation and report the frequency and impact of transformed cases. Do not claim the Poisson model predicts negative outcomes.

Do not silently discard negative rows, silently convert them in the canonical raw data, or conflate the transformed target with actual FPL outcomes. Any alternative likelihood capable of negative support would be a separate model variant, not the paper-faithful 2PM implementation.

## 9. Shared pipeline and downstream boundary

The 2PM forecast adapter must emit a validated player-Gameweek forecast record through the existing forecasting interface. M3 consumes it as one forecast input.

M3 remains the only place for:
- expected-value and field-relative calculations;
- ownership and effective ownership;
- coverage and variance/CoVar;
- portfolio and transfer decision logic;
- squad, XI, bench and captaincy optimization.

M4 owns the established recommendation products. The 2PM-powered squad-specific product is **2PM Squad Recommendations**. This specification does not alter M3/M4 contracts or release scope.

## 10. Essential acceptance tests

### Data and point-in-time
- Exactly five prior played-match observations per sample.
- Chronological order and correct player/match identity.
- Maximum 21-day inter-observation gap enforced.
- Blank Gameweeks are not treated as played matches.
- Double Gameweek history/target aggregation is explicit and correct.
- Every feature is available before the target deadline.
- No target leakage through same-Gameweek realized statistics.
- Train-only preprocessing and initialization; chronological disjoint partitions.

### Architecture and distribution
- Input shape is `[batch, 5, 116]` for the paper-schema reproduction.
- Encoder output and three-parameter distribution head have expected shapes.
- (0 < p < 1), (lambda_1 > 0), (lambda_2 > 0), all finite.
- PMF is non-negative and sums to one within numerical tolerance over a sufficiently large support.
- Analytic expected value and variance match hand-calculated cases.
- Threshold probabilities agree with direct PMF summation/survival calculations.
- Mixture NLL matches a trusted hand-calculated example and remains finite for extreme valid inputs.
- Gradients are finite and a small training run reduces training NLL.

### Artifact and inference
- Save/load round trip preserves architecture, weights, feature schema, preprocessing, training metadata and model version.
- Inference is deterministic for fixed inputs when using analytic outputs.
- Inference rejects wrong feature count/order, wrong sequence length, stale/missing required metadata and invalid values.
- Forecast adapter emits the agreed canonical schema and preserves provenance.
- M3 integration is interface-only; no M3 decision logic is copied into 2PM.

## 11. Work sequence

1. Freeze this specification and record its version.
2. Inspect the complete existing data panel, feature definitions and target-generation code. Resolve point-in-time and match-vs-Gameweek grain before implementing the new sequence builder.
3. Establish the paper's 116-feature dictionary or a clearly labelled, source-backed 116-feature reconstruction. Do not proceed under a false claim of exact reproduction.
4. Implement and test the match-sequence builder.
5. Implement the paper-governed Poisson-mixture Transformer as a distinct model module; retain the current categorical model as a baseline.
6. Implement stable mixture NLL, train-only rate initialization, training loop and artifact metadata.
7. Add the canonical forecast adapter and connect it to the established M3 interface.
8. Run essential acceptance tests and a controlled historical reproduction.
9. Keep production weight at 0 and `production_eligible=false` until the project's separate M2 validation and approval gates are satisfied.

## 12. Known reproduction limits and unresolved details

The following are not fully specified in the paper and must remain explicit implementation decisions:

- complete machine-readable names/definitions of all 116 features;
- exact sequence pooling/representation passed to the output head;
- selected number of Transformer encoder layers;
- detailed optimizer and learning-rate configuration;
- exact Gumbel-Softmax role and temperature handling;
- how the two MLE-initialized component rates are assigned to the low/high regimes.

Any choice made for these must be documented, versioned and evaluated without using test outcomes. The paper's reported performance is a research benchmark, not a guarantee that the same performance will transfer to our data.

## References

- Wiechno, W., Duch, P. and Bartosik, B. (2026). *Modeling Fantasy Premier League Player Performance with a Two-Component Poisson Mixture Transformer*. Proceedings of ICAART 2026, Volume 4, pp. 3093–3100. DOI: 10.5220/0014358000004052.
- Published paper PDF: https://www.scitepress.org/Papers/2026/143580/143580.pdf
- Existing experimental model: https://github.com/uasir/CTA-FPL-Model/blob/feat/four-layer-2pm-transformer-evaluation/canonical_candidate/engineering_workbench/scripts/two_pm_transformer.py
- Existing walk-forward evaluator: https://github.com/uasir/CTA-FPL-Model/blob/feat/four-layer-2pm-transformer-evaluation/canonical_candidate/engineering_workbench/scripts/evaluate_two_pm_transformer_walk_forward.py
