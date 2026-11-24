import pytest
torch = pytest.importorskip("torch")
from two_pm_transformer import TwoPMTransformer


def test_two_pm_transformer_emits_separate_minutes_and_conditional_points():
    model = TwoPMTransformer(feature_count=12, width=32, heads=4, layers=2, dropout=0.0)
    x = torch.randn(5, 8, 12)
    output = model(x)
    assert output["minutes_logits"].shape == (5, 5)
    assert output["conditional_points_logits"].shape == (5, 6)
    probs = model.probabilities(output)
    assert torch.allclose(probs["points"].sum(-1), torch.ones(5), atol=1e-6)
    assert torch.all(probs["points"] >= 0)
    assert torch.all(probs["appearance_probability"] >= 0)


def test_two_pm_transformer_padding_mask_and_sequence_guard():
    model = TwoPMTransformer(feature_count=4, width=16, heads=4, layers=1, max_length=5)
    x = torch.randn(2, 4, 4)
    mask = torch.tensor([[False, False, False, True], [False, False, False, False]])
    output = model(x, mask)
    assert output["minutes_logits"].shape == (2, 5)
    with pytest.raises(ValueError):
        model(torch.randn(1, 6, 4))
