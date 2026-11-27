import math

import pytest
torch = pytest.importorskip("torch")

from two_component_poisson_transformer import (
    PaperTwoComponentPoissonTransformer,
    fit_training_poisson_mixture_mle,
    initialize_mixture_head_from_training_targets,
    poisson_mixture_negative_log_likelihood,
    poisson_mixture_tail_probability,
    prepare_paper_targets,
)



def run_model(model, values):
    observed = torch.ones_like(values, dtype=torch.bool)
    availability = torch.ones_like(values, dtype=torch.long)
    regime = torch.ones(values.shape[0], dtype=torch.long)
    return model(values, observed, availability, regime)


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
    output = run_model(model, torch.randn(4, 6, 286))
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
    output = run_model(model, x)
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
        run_model(model, torch.randn(2, 5, 4))
    bad = torch.randn(2, 6, 4)
    bad[0, 0, 0] = float("nan")
    with pytest.raises(ValueError, match="NaN"):
        run_model(model, bad)

    output = run_model(model, torch.randn(2, 6, 4))
    with pytest.raises(ValueError, match="non-negative"):
        poisson_mixture_negative_log_likelihood(output, [-1, 2])
    with pytest.raises(ValueError, match="integer-valued"):
        poisson_mixture_negative_log_likelihood(output, [1.5, 2.0])


def test_num_layers_is_explicit_not_assumed_from_branch_name():
    with pytest.raises(TypeError):
        PaperTwoComponentPoissonTransformer(
            feature_count=4, sequence_length=6
        )



def test_mixture_tail_probability_matches_direct_poisson_sum():
    model = PaperTwoComponentPoissonTransformer(
        feature_count=2,
        sequence_length=6,
        num_layers=1,
        d_model=16,
        nhead=4,
        dim_feedforward=32,
        dropout=0.0,
    )
    output = run_model(model, torch.randn(3, 6, 2))
    for threshold in (6, 8, 10):
        tail = poisson_mixture_tail_probability(output, threshold)
        support = torch.arange(threshold, dtype=output["lambda_1"].dtype)
        pmf_1 = torch.exp(
            -output["lambda_1"].unsqueeze(-1)
            + support * torch.log(output["lambda_1"].unsqueeze(-1))
            - torch.lgamma(support + 1)
        )
        pmf_2 = torch.exp(
            -output["lambda_2"].unsqueeze(-1)
            + support * torch.log(output["lambda_2"].unsqueeze(-1))
            - torch.lgamma(support + 1)
        )
        direct = (
            output["p"] * (1 - pmf_1.sum(-1))
            + (1 - output["p"]) * (1 - pmf_2.sum(-1))
        )
        assert torch.allclose(tail, direct, atol=1e-6)


def test_training_only_em_mle_initialization_is_valid_and_sets_head_biases():
    training_targets = [0, 0, 1, 1, 2, 3, 5, 7, 9, 12, 15]
    fitted = fit_training_poisson_mixture_mle(training_targets)
    assert fitted["training_rows"] == len(training_targets)
    assert 0 < fitted["p"] < 1
    assert fitted["lambda_1"] > 0
    assert fitted["lambda_2"] > 0
    assert fitted["initialization"] == "training_only_quantile_seeded_two_poisson_em_mle"

    model = PaperTwoComponentPoissonTransformer(
        feature_count=3,
        sequence_length=6,
        num_layers=1,
        d_model=16,
        nhead=4,
        dim_feedforward=32,
    )
    report = initialize_mixture_head_from_training_targets(model, training_targets)
    output = run_model(model, torch.zeros(1, 6, 3))
    assert report["training_rows"] == len(training_targets)
    assert 0 < output["p"].item() < 1
    assert output["lambda_1"].item() > 0
    assert output["lambda_2"].item() > 0


def test_training_mle_rejects_validation_style_invalid_values():
    with pytest.raises(ValueError, match="non-negative integer"):
        fit_training_poisson_mixture_mle([0, 1, -1])
    with pytest.raises(ValueError, match="non-negative integer"):
        fit_training_poisson_mixture_mle([0, 1.5, 2])


def test_model_uses_five_feature_channel_blocks_and_scoring_regime_embedding():
    model = PaperTwoComponentPoissonTransformer(
        feature_count=7,
        sequence_length=6,
        num_layers=1,
        d_model=16,
        nhead=4,
        dim_feedforward=32,
    )
    assert model.input_embedding.in_features == 35
    assert model.scoring_regime_embedding.num_embeddings == 2


def test_model_rejects_observed_values_for_structurally_unavailable_features():
    model = PaperTwoComponentPoissonTransformer(
        feature_count=2,
        sequence_length=6,
        num_layers=1,
        d_model=16,
        nhead=4,
        dim_feedforward=32,
    )
    values = torch.zeros(1, 6, 2)
    observed = torch.ones_like(values, dtype=torch.bool)
    availability = torch.ones_like(values, dtype=torch.long)
    availability[..., 0] = 0
    with pytest.raises(ValueError, match="UNAVAILABLE"):
        model(values, observed, availability, torch.tensor([1]))


def test_model_rejects_invalid_availability_or_scoring_regime_codes():
    model = PaperTwoComponentPoissonTransformer(
        feature_count=2,
        sequence_length=6,
        num_layers=1,
        d_model=16,
        nhead=4,
        dim_feedforward=32,
    )
    values = torch.zeros(1, 6, 2)
    observed = torch.ones_like(values, dtype=torch.bool)
    availability = torch.ones_like(values, dtype=torch.long)
    availability[..., 0] = 3
    with pytest.raises(ValueError, match="availability_state"):
        model(values, observed, availability, torch.tensor([1]))
    availability.fill_(1)
    with pytest.raises(ValueError, match="scoring_regime"):
        model(values, observed, availability, torch.tensor([2]))
