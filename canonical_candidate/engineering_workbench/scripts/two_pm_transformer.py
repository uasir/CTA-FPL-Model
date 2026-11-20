#!/usr/bin/env python3
"""Optional PyTorch 2PM-Transformer research model.

The model has a shared temporal encoder and two explicitly separated heads:
(1) appearance/minutes-band distribution; (2) conditional FPL points-band
distribution given appearance. It emits probabilities, not exact haul claims.
PyTorch is an optional research dependency and is not required by base CI.
"""
from __future__ import annotations

try:
    import torch
    from torch import nn
except ImportError:  # Keep the engineering workbench usable without PyTorch.
    torch = None
    nn = None


POINTS_BANDS = 6  # negative, zero, 1-2, 3-5, 6-9, 10+
MINUTES_BANDS = 5  # 0, 1-29, 30-59, 60-89, 90+


if nn is not None:
    class SinusoidalPositionEncoding(nn.Module):
        def __init__(self, width: int, max_length: int = 64):
            super().__init__()
            import math
            position = torch.arange(max_length, dtype=torch.float32).unsqueeze(1)
            div = torch.exp(torch.arange(0, width, 2, dtype=torch.float32) *
                            (-math.log(10000.0) / width))
            pe = torch.zeros(max_length, width)
            pe[:, 0::2] = torch.sin(position * div)
            if width > 1:
                pe[:, 1::2] = torch.cos(position * div[:pe[:, 1::2].shape[1]])
            self.register_buffer("encoding", pe.unsqueeze(0), persistent=False)

        def forward(self, x):
            if x.shape[1] > self.encoding.shape[1]:
                raise ValueError("Sequence exceeds configured max_length")
            return x + self.encoding[:, :x.shape[1], :]


    class TwoPMTransformer(nn.Module):
        """Two-Part Minutes/Points temporal transformer.

        Input shape: [batch, history_length, feature_count].
        Padding mask shape: [batch, history_length], True means padding.
        """
        def __init__(self, feature_count: int, width: int = 64, heads: int = 4,
                     layers: int = 2, dropout: float = 0.1, max_length: int = 64):
            super().__init__()
            if width % heads:
                raise ValueError("width must be divisible by heads")
            self.input_projection = nn.Linear(feature_count, width)
            self.position = SinusoidalPositionEncoding(width, max_length)
            block = nn.TransformerEncoderLayer(
                d_model=width, nhead=heads, dim_feedforward=width * 4,
                dropout=dropout, batch_first=True, norm_first=True,
                activation="gelu",
            )
            self.encoder = nn.TransformerEncoder(block, num_layers=layers,
                                                 enable_nested_tensor=False)
            self.norm = nn.LayerNorm(width)
            self.minutes_head = nn.Sequential(nn.Linear(width, width // 2),
                                               nn.GELU(), nn.Linear(width // 2, MINUTES_BANDS))
            self.conditional_points_head = nn.Sequential(
                nn.Linear(width, width // 2), nn.GELU(),
                nn.Linear(width // 2, POINTS_BANDS),
            )

        def forward(self, sequence, padding_mask=None):
            if sequence.ndim != 3:
                raise ValueError("sequence must have [batch, time, features] shape")
            x = self.position(self.input_projection(sequence))
            encoded = self.encoder(x, src_key_padding_mask=padding_mask)
            if padding_mask is None:
                pooled = encoded[:, -1, :]
            else:
                valid = (~padding_mask).to(encoded.dtype)
                last_index = valid.sum(dim=1).long().clamp(min=1) - 1
                pooled = encoded[torch.arange(encoded.shape[0], device=encoded.device), last_index]
            pooled = self.norm(pooled)
            return {
                "minutes_logits": self.minutes_head(pooled),
                "conditional_points_logits": self.conditional_points_head(pooled),
            }

        @staticmethod
        def probabilities(output):
            minutes = torch.softmax(output["minutes_logits"], dim=-1)
            conditional = torch.softmax(output["conditional_points_logits"], dim=-1)
            # Non-appearance probability is assigned to the exact-zero points class.
            appearance = 1.0 - minutes[..., 0]
            points = conditional * appearance.unsqueeze(-1)
            points[..., 1] = points[..., 1] + minutes[..., 0]
            return {"minutes": minutes, "conditional_points": conditional,
                    "appearance_probability": appearance, "points": points}
else:
    class TwoPMTransformer:  # pragma: no cover - exercised when dependency absent
        def __init__(self, *args, **kwargs):
            raise ImportError("Install the optional 'torch' dependency to use TwoPMTransformer")


def build_model(feature_count: int, **kwargs):
    return TwoPMTransformer(feature_count=feature_count, **kwargs)
