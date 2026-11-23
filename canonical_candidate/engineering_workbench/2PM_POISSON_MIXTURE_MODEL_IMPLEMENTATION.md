# 2PM — Clean Poisson-Mixture Transformer Implementation

**Status:** Core model module implemented; research-only; no training or forecast evaluation  
**Implementation:** `scripts/two_component_poisson_transformer.py`  
**Configuration:** `config/2pm_poisson_transformer_candidate.json`

## Scope

This is a new, independent implementation of the published paper's two-component Poisson-mixture Transformer core. It does not import or reuse the frozen categorical `TwoPMTransformer`, its training/evaluation code, or Dastan's predictive model.

The module implements:

- Input projection from the candidate 286-feature tokens.
- Fixed sinusoidal positional encoding.
- Encoder-only Transformer blocks.
- A three-parameter output head: mixture logit, `lambda_1` and `lambda_2`.
- Sigmoid mixture probability and positive Poisson rates via softplus.
- Analytic mixture expected points and variance.
- Mixture tail probabilities for arbitrary non-negative integer thresholds (including 6+, 8+ and 10+).
- Numerically stable mixture negative log-likelihood using log-sigmoid, log-add-exp and `lgamma(y + 1)`.
- A deterministic, training-target-only two-Poisson EM/MLE initialization candidate for the mixture head; its quantile seed and component ordering are explicit adaptations, not a claimed exact reproduction of an unspecified author routine.
- The paper's negative-points-to-zero target transformation as a separate function that returns a transformation mask and never mutates raw scores.

## Input adaptation

The candidate input is six tokens × 286 features: five previous played-fixture tokens plus a target-query token. This is the approved candidate Dastan input direction, not the paper's original five-token × 116-feature representation.

The current sequence builder's pre-match-row semantics remain provisional. The recommended post-match historical-state representation is still an open design decision. The model accepts the tensor contract; it does not certify the underlying features or token semantics.

## Explicit implementation choices

- Embedding width 256, eight attention heads and dropout 0.22 follow the paper's reported tuned configuration.
- Feed-forward width 1024, GELU activation, pre-normalization and sinusoidal positional encoding are recorded as implementation choices where the paper does not fully specify them.
- The encoder layer count is deliberately **required at construction time** and has no default. The paper does not clearly report its selected layer count; the branch name is not evidence.
- The final target-query token representation is used for the distribution head. This is the current documented adaptation choice, not a claim that the paper explicitly prescribes this exact pooling method.
- Gumbel-Softmax is not inserted into the forward path until its role and temperature in the paper are resolved.

The test suite instantiates a two-layer model only as a small shape/gradient smoke test. That does not select two layers for the research model.

## Not yet implemented

- Full training loop and chronological split integration; the rate initialization helper exists but is not yet wired into a training pipeline.
- Sequence-token semantic freeze and full 286-feature admission.
- Residual-NaN tensor preparation under the pinned Dastan preprocessing policy.
- Threshold survival probabilities and the final M3 forecast adapter.
- Artifact serialization, calibration and model evaluation.

No model training is authorized by this implementation. Production weight remains zero and `production_eligible=false`.
