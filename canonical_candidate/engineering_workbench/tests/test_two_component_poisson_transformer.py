import math

import pytest
torch = pytest.importorskip("torch")

from two_component_poisson_transformer import (
    PaperTwoComponentPoissonTransformer,
    poisson_mixture_negative_log_likelihood,
    prepare_paper_targets,
)


def test_paper_model_emits_valid_two_component_poisson_parameters():
    model = PaperTwoComponentPoissonTransformer(
        feature_count=286,
        sequence_length=6,
        num_layers=2,
        d_model=64,
        nhead=8,
        dim_feedforward=128,
        dropout=0.0,
    )
    output = model(torch.randn(4, 6, 286))
    assert output["p"].shape == (4,)
    assert output["lambda_1"].shape == (4,)
    assert output["lambda_2"].shape == (4,)
    assert output["expected_points"].shape == (4,)
    assert torch.all(output["p"] > 0)
    assert torch.all(output["p"] < 1)
    assert torch.all(output["lambda_1"] > 0)
    assert torch.all(output["lambda_2"] > 0)
    assert torch.all(output["variance"] >= 0)
    assert torch.isfinite(output["expected_points"]).all()


def test_mixture_nll_matches_direct_component_logaddexp_and_backpropagates():
    model = PaperTwoComponentPoissonTransformer(
        feature_count=3,
        sequence_length=6,
        num_layers=1,
        d_model=16,
        nhead=4,
        dim_feedforward=32,
        dropout=0.0,
    )
    x = torch.randn(5, 6, 3)
    targets = torch.tensor([0, 1, 2, 5, 10], dtype=torch.float32)
    output = model(x)
    losses = poisson_mixture_negative_log_likelihood(
        output, targets, reduction="none"
    )
    direct_1 = (
        torch.log(output["p"])
        + targets * torch.log(output["lambda_1"])
        - output["lambda_1"]
        - torch.lgamma(targets + 1)
    )
    direct_2 = (
        torch.log1p(-output["p"])
        + targets * torch.log(output["lambda_2"])
        - output["lambda_2"]
        - torch.lgamma(targets + 1)
    )
    expected = -torch.logaddexp(direct_1, direct_2)
    assert torch.allclose(losses, expected, atol=1e-6)
    loss = losses.mean()
    loss.backward()
    gradients = [p.grad for p in model.parameters() if p.grad is not None]
    assert gradients
    assert all(torch.isfinite(gradient).all() for gradient in gradients)


def test_paper_negative_target_rule_preserves_transformation_mask():
    raw = torch.tensor([-2, 0, 3, 8])
    transformed, mask = prepare_paper_targets(raw)
    assert transformed.tolist() == [0.0, 0.0, 3.0, 8.0]
    assert mask.tolist() == [True, False, False, False]
    assert raw.tolist() == [-2, 0, 3, 8]


def test_model_rejects_wrong_shape_nonfinite_input_and_invalid_targets():
    model = PaperTwoComponentPoissonTransformer(
        feature_count=4,
        sequence_length=6,
        num_layers=1,
        d_model=16,
        nhead=4,
        dim_feedforward=32,
    )
    with pytest.raises(ValueError, match="sequence length"):
        model(torch.randn(2, 5, 4))
    bad = torch.randn(2, 6, 4)
    bad[0, 0, 0] = float("nan")
    with pytest.raises(ValueError, match="NaN"):
        model(bad)

    output = model(torch.randn(2, 6, 4))
    with pytest.raises(ValueError, match="non-negative"):
        poisson_mixture_negative_log_likelihood(output, [-1, 2])
    with pytest.raises(ValueError, match="integer-valued"):
        poisson_mixture_negative_log_likelihood(output, [1.5, 2.0])


def test_num_layers_is_explicit_not_assumed_from_branch_name():
    with pytest.raises(TypeError):
        PaperTwoComponentPoissonTransformer(
            feature_count=4, sequence_length=6
        )
