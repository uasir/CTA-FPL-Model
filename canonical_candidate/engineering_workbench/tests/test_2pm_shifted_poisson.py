import pytest
torch = pytest.importorskip("torch")

from two_component_poisson_transformer import (
    PaperTwoComponentPoissonTransformer,
    fit_training_poisson_mixture_mle,
    forward_player_gameweek_batch,
    independent_fixture_gameweek_negative_log_likelihood,
    poisson_mixture_negative_log_likelihood,
    poisson_mixture_tail_probability,
    prepare_shifted_poisson_targets,
    select_training_support_shift,
)


def test_training_fold_support_shift_preserves_negative_points():
    assert select_training_support_shift([-3, 0, 2, 8]) == 20
    assert select_training_support_shift([-22, 0, 2], safety_margin=5) == 27
    assert prepare_shifted_poisson_targets([-3, 0, 4], 20).tolist() == [17.0, 20.0, 24.0]
    with pytest.raises(ValueError, match="support floor"):
        prepare_shifted_poisson_targets([-21], 20)


def test_shifted_model_expected_points_variance_and_signed_nll():
    model = PaperTwoComponentPoissonTransformer(
        feature_count=4,
        sequence_length=6,
        num_layers=1,
        d_model=16,
        nhead=4,
        dim_feedforward=32,
        dropout=0.0,
        support_shift=20,
    )
    output = model(torch.randn(3, 6, 4))
    count_mean = output["p"] * output["lambda_1"] + (
        1.0 - output["p"]
    ) * output["lambda_2"]
    assert torch.allclose(output["expected_points"], count_mean - 20)
    assert output["support_lower_bound"] == -20
    count_second_moment = (
        output["p"] * (output["lambda_1"] + output["lambda_1"].square())
        + (1.0 - output["p"]) * (
            output["lambda_2"] + output["lambda_2"].square()
        )
    )
    assert torch.allclose(
        output["variance"], count_second_moment - count_mean.square(), atol=1e-6
    )
    targets = torch.tensor([-3.0, 0.0, 7.0])
    losses = poisson_mixture_negative_log_likelihood(
        output, targets, reduction="none"
    )
    shifted = targets + 20
    log_1 = (
        torch.nn.functional.logsigmoid(output["mixture_logit"])
        + shifted * torch.log(output["lambda_1"])
        - output["lambda_1"]
        - torch.lgamma(shifted + 1)
    )
    log_2 = (
        torch.nn.functional.logsigmoid(-output["mixture_logit"])
        + shifted * torch.log(output["lambda_2"])
        - output["lambda_2"]
        - torch.lgamma(shifted + 1)
    )
    assert torch.allclose(losses, -torch.logaddexp(log_1, log_2), atol=1e-6)
    assert torch.isfinite(losses).all()
    losses.mean().backward()
    assert all(
        torch.isfinite(parameter.grad).all()
        for parameter in model.parameters()
        if parameter.grad is not None
    )
    with pytest.raises(ValueError, match="support floor"):
        poisson_mixture_negative_log_likelihood(output, [-21, 0, 1])


def test_shifted_tail_probability_uses_points_plus_support_shift():
    model = PaperTwoComponentPoissonTransformer(
        feature_count=2,
        sequence_length=6,
        num_layers=1,
        d_model=16,
        nhead=4,
        dim_feedforward=32,
        dropout=0.0,
        support_shift=20,
    )
    output = model(torch.randn(2, 6, 2))
    tail = poisson_mixture_tail_probability(output, 6)
    threshold = 26
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
    direct = output["p"] * (1 - pmf_1.sum(-1)) + (
        1 - output["p"]
    ) * (1 - pmf_2.sum(-1))
    assert torch.allclose(tail, direct, atol=1e-6)


def test_shifted_training_em_uses_nonnegative_offset_counts():
    fitted = fit_training_poisson_mixture_mle(
        [-4, -2, 0, 1, 3, 5, 8], support_shift=20
    )
    assert fitted["support_shift"] == 20
    assert fitted["support_lower_bound"] == -20
    assert fitted["training_rows"] == 7
    assert fitted["lambda_1"] > 0
    with pytest.raises(ValueError, match="support"):
        fit_training_poisson_mixture_mle([-21, 0, 2], support_shift=20)


def test_gameweek_loss_aggregates_two_fixture_mixtures_once_and_backpropagates():
    p = torch.tensor([[0.6, 0.4]], requires_grad=True)
    lambda_1 = torch.tensor([[18.0, 21.0]], requires_grad=True)
    lambda_2 = torch.tensor([[24.0, 17.0]], requires_grad=True)
    output = {
        "p": p,
        "lambda_1": lambda_1,
        "lambda_2": lambda_2,
        "support_shift": 20,
    }
    mask = torch.tensor([[True, True]])
    target = torch.tensor([-5.0])
    loss = independent_fixture_gameweek_negative_log_likelihood(
        output, target, mask
    )
    # Four components; the aggregate target is shifted once by 20 per fixture.
    rates = torch.tensor([39.0, 45.0, 35.0, 41.0])
    weights = torch.tensor([0.24, 0.16, 0.36, 0.24])
    shifted_target = 35.0
    log_probs = (
        torch.log(weights)
        + shifted_target * torch.log(rates)
        - rates
        - torch.lgamma(torch.tensor(shifted_target + 1.0))
    )
    expected = -torch.logsumexp(log_probs, dim=0)
    assert torch.allclose(loss, expected, atol=1e-5)
    loss.backward()
    assert p.grad is not None and torch.isfinite(p.grad).all()
    assert lambda_1.grad is not None and torch.isfinite(lambda_1.grad).all()
    assert lambda_2.grad is not None and torch.isfinite(lambda_2.grad).all()


def test_single_fixture_gameweek_loss_matches_fixture_nll():
    output = {
        "p": torch.tensor([[0.7]]),
        "lambda_1": torch.tensor([[19.0]]),
        "lambda_2": torch.tensor([[23.0]]),
        "support_shift": 20,
    }
    target = torch.tensor([-2.0])
    gameweek_loss = independent_fixture_gameweek_negative_log_likelihood(
        output, target, torch.tensor([[True]])
    )
    fixture_loss = poisson_mixture_negative_log_likelihood(
        {
            "p": output["p"].reshape(1),
            "mixture_logit": torch.logit(output["p"].reshape(1)),
            "lambda_1": output["lambda_1"].reshape(1),
            "lambda_2": output["lambda_2"].reshape(1),
            "support_shift": 20,
        },
        target,
    )
    assert torch.allclose(gameweek_loss, fixture_loss, atol=1e-6)



def test_grouped_player_gameweek_forward_flattens_queries_and_returns_one_loss():
    model = PaperTwoComponentPoissonTransformer(
        feature_count=4,
        sequence_length=6,
        num_layers=1,
        d_model=16,
        nhead=4,
        dim_feedforward=32,
        dropout=0.0,
        support_shift=20,
    )
    inputs = torch.randn(2, 2, 6, 4)
    mask = torch.tensor([[True, True], [True, False]])
    targets = torch.tensor([-4.0, 5.0])
    result = forward_player_gameweek_batch(model, inputs, mask, targets)
    assert result["fixture_output"]["p"].shape == (2, 2)
    assert result["expected_points"].shape == (2,)
    assert result["nll_per_player_gameweek"].shape == (2,)
    expected = (
        result["fixture_expected_points"] * mask.to(torch.float32)
    ).sum(dim=1)
    variance = (
        result["fixture_variance"] * mask.to(torch.float32)
    ).sum(dim=1)
    assert torch.allclose(result["expected_points"], expected)
    assert torch.allclose(result["variance"], variance)
    result["loss"].backward()
    assert any(parameter.grad is not None for parameter in model.parameters())
