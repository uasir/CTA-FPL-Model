"""Paper-governed two-component Poisson-mixture Transformer for 2PM.

This is a clean implementation. It does not import or reuse the legacy categorical
TwoPMTransformer, Dastan model code, weights, preprocessing or prediction heads.
The 286-feature / six-token input is the current candidate adaptation contract; the
feature and sequence admission gates remain separate from this model module.
"""
from __future__ import annotations

from typing import Any

try:
    import torch
    from torch import nn
    from torch.nn import functional as F
except ImportError:  # Keep non-model engineering tools usable without PyTorch.
    torch = None
    nn = None
    F = None


MODEL_NAME = "2PM-PoissonMixture-Transformer"
MODEL_ARCHITECTURE_VERSION = "0.1.0"


if nn is not None:
    class SinusoidalPositionEncoding(nn.Module):
        """Fixed sinusoidal positions for the ordered played-fixture/query tokens."""

        def __init__(self, width: int, max_length: int):
            super().__init__()
            if width <= 0 or max_length <= 0:
                raise ValueError("width and max_length must be positive")
            position = torch.arange(max_length, dtype=torch.float32).unsqueeze(1)
            scale = torch.exp(
                torch.arange(0, width, 2, dtype=torch.float32)
                * (-torch.log(torch.tensor(10000.0)) / width)
            )
            encoding = torch.zeros(max_length, width, dtype=torch.float32)
            encoding[:, 0::2] = torch.sin(position * scale)
            if width > 1:
                encoding[:, 1::2] = torch.cos(
                    position * scale[: encoding[:, 1::2].shape[1]]
                )
            self.register_buffer("encoding", encoding.unsqueeze(0), persistent=False)

        def forward(self, values: torch.Tensor) -> torch.Tensor:
            if values.ndim != 3:
                raise ValueError("position encoding expects [batch, sequence, width]")
            if values.shape[1] > self.encoding.shape[1]:
                raise ValueError("input sequence exceeds configured maximum length")
            return values + self.encoding[:, : values.shape[1], :].to(values.dtype)


    class PaperTwoComponentPoissonTransformer(nn.Module):
        """Encoder-only Transformer with a two-component Poisson-mixture output.

        Input:  [batch, sequence_length, feature_count]
        Output: mixture probability p and positive Poisson rates lambda1/lambda2.

        The final token is the target-fixture query token in the current Dastan
        adaptation. The sequence length and encoder layer count are explicit config
        values; the paper does not clearly report its selected layer count.
        """

        def __init__(
            self,
            feature_count: int,
            *,
            sequence_length: int,
            num_layers: int,
            d_model: int = 256,
            nhead: int = 8,
            dim_feedforward: int = 1024,
            dropout: float = 0.22,
            epsilon: float = 1e-6,
        ):
            super().__init__()
            if feature_count <= 0 or sequence_length <= 0 or num_layers <= 0:
                raise ValueError("feature_count, sequence_length and num_layers must be positive")
            if d_model <= 0 or nhead <= 0 or d_model % nhead:
                raise ValueError("d_model must be positive and divisible by nhead")
            if dim_feedforward <= 0:
                raise ValueError("dim_feedforward must be positive")
            if not 0.0 <= dropout < 1.0:
                raise ValueError("dropout must be in [0, 1)")
            if epsilon <= 0:
                raise ValueError("epsilon must be positive")

            self.feature_count = int(feature_count)
            self.sequence_length = int(sequence_length)
            self.d_model = int(d_model)
            self.epsilon = float(epsilon)

            self.input_embedding = nn.Linear(self.feature_count, self.d_model)
            self.position_encoding = SinusoidalPositionEncoding(
                self.d_model, self.sequence_length
            )
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=self.d_model,
                nhead=int(nhead),
                dim_feedforward=int(dim_feedforward),
                dropout=float(dropout),
                activation="gelu",
                batch_first=True,
                norm_first=True,
            )
            self.encoder = nn.TransformerEncoder(
                encoder_layer,
                num_layers=int(num_layers),
                enable_nested_tensor=False,
            )
            self.output_norm = nn.LayerNorm(self.d_model)
            self.mixture_head = nn.Linear(self.d_model, 3)

        def forward(self, sequence: torch.Tensor) -> dict[str, torch.Tensor]:
            if sequence.ndim != 3:
                raise ValueError("sequence must have [batch, sequence, features] shape")
            if sequence.shape[1] != self.sequence_length:
                raise ValueError(
                    f"expected sequence length {self.sequence_length}, got {sequence.shape[1]}"
                )
            if sequence.shape[2] != self.feature_count:
                raise ValueError(
                    f"expected {self.feature_count} features, got {sequence.shape[2]}"
                )
            if not torch.isfinite(sequence).all():
                raise ValueError("model input contains NaN or infinite values")

            embedded = self.input_embedding(sequence)
            encoded = self.encoder(self.position_encoding(embedded))
            target_context = self.output_norm(encoded[:, -1, :])
            raw = self.mixture_head(target_context)

            mixture_logit = raw[:, 0]
            mixture_probability = torch.sigmoid(mixture_logit)
            lambda_1 = F.softplus(raw[:, 1]) + self.epsilon
            lambda_2 = F.softplus(raw[:, 2]) + self.epsilon

            expected_points = (
                mixture_probability * lambda_1
                + (1.0 - mixture_probability) * lambda_2
            )
            second_moment = (
                mixture_probability * (lambda_1 + lambda_1.square())
                + (1.0 - mixture_probability) * (lambda_2 + lambda_2.square())
            )
            variance = (second_moment - expected_points.square()).clamp_min(0.0)

            return {
                "mixture_logit": mixture_logit,
                "p": mixture_probability,
                "lambda_1": lambda_1,
                "lambda_2": lambda_2,
                "expected_points": expected_points,
                "variance": variance,
                "standard_deviation": torch.sqrt(variance),
            }
else:
    class PaperTwoComponentPoissonTransformer:  # pragma: no cover
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Install the optional PyTorch dependency to use the 2PM Poisson-mixture model"
            )


def poisson_mixture_negative_log_likelihood(
    output: dict[str, Any],
    targets,
    *,
    reduction: str = "mean",
):
    """Stable negative log-likelihood for the two-component Poisson mixture."""
    if torch is None:
        raise ImportError("PyTorch is required for the 2PM mixture likelihood")
    if reduction not in {"none", "mean", "sum"}:
        raise ValueError("reduction must be one of: none, mean, sum")

    y = torch.as_tensor(targets, dtype=output["lambda_1"].dtype,
                        device=output["lambda_1"].device)
    if not torch.isfinite(y).all():
        raise ValueError("targets must be finite")
    if (y < 0).any():
        raise ValueError("Poisson targets must be non-negative")
    if not torch.equal(y, torch.round(y)):
        raise ValueError("Poisson targets must be integer-valued")

    log_factorial = torch.lgamma(y + 1.0)
    log_component_1 = (
        F.logsigmoid(output["mixture_logit"])
        + y * torch.log(output["lambda_1"])
        - output["lambda_1"]
        - log_factorial
    )
    log_component_2 = (
        F.logsigmoid(-output["mixture_logit"])
        + y * torch.log(output["lambda_2"])
        - output["lambda_2"]
        - log_factorial
    )
    losses = -torch.logaddexp(log_component_1, log_component_2)
    if reduction == "mean":
        return losses.mean()
    if reduction == "sum":
        return losses.sum()
    return losses


def prepare_paper_targets(raw_targets):
    """Apply the paper's negative-to-zero target rule without mutating raw scores.

    Returns (model_targets, transformed_mask). Keep raw_targets separately for
    evaluation and reporting; the transformation must never overwrite actual points.
    """
    if torch is None:
        raise ImportError("PyTorch is required for target preparation")
    raw = torch.as_tensor(raw_targets, dtype=torch.float32)
    if not torch.isfinite(raw).all():
        raise ValueError("raw target points must be finite")
    if not torch.equal(raw, torch.round(raw)):
        raise ValueError("raw FPL points must be integer-valued")
    transformed = raw.lt(0)
    return raw.clamp_min(0), transformed


def build_model(feature_count: int, **kwargs):
    """Construct a new paper-governed 2PM model; num_layers is deliberately required."""
    return PaperTwoComponentPoissonTransformer(
        feature_count=feature_count, **kwargs
    )
