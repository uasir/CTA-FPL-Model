from __future__ import annotations

import pytest

from m4_covar_field_portfolio_summary import (
    CovarFieldPortfolioSummaryError,
    summarize_field_portfolio_sample,
)


def sample_artifact():
    portfolios = []
    squads = [
        list(range(1, 16)),
        list(range(1, 11)) + list(range(16, 21)),
        list(range(6, 21)),
    ]
    for index, squad in enumerate(squads):
        starting = squad[:11]
        bench = squad[11:]
        roles = (
            ["GK"] + ["DEF"] * 4 + ["MID"] * 5 + ["FWD"]
            + ["GK", "DEF", "MID", "FWD"]
        )
        portfolios.append({
            "portfolio_id": f"field_sample_{index + 1:04d}",
            "player_ids": [str(pid) for pid in squad],
            "starting_player_ids": [str(pid) for pid in starting],
            "starting_goalkeeper_id": str(starting[0]),
            "reserve_goalkeeper_id": str(bench[0]),
            "bench_order": [str(pid) for pid in bench[1:]],
            "player_positions": {str(pid): role for pid, role in zip(squad, roles)},
            "captain_id": str(starting[0] if index == 0 else starting[1]),
            "vice_captain_id": str(starting[2]),
            "captain_multiplier": 3 if index == 0 else 2,
            "field_weight": 1 / 3,
            "rank_stratum": index + 1,
            "active_chip": "3xc" if index == 0 else None,
            "portfolio_role": "FIELD",
        })
    return {
        "schema_version": "1.1.0",
        "data_status": "MANAGER_ID_STRIPPED_MANAGER_PICK_SAMPLE",
        "metadata": {
            "gameweek": 12,
            "deadline_utc": "2026-11-27T18:30:00+00:00",
            "captured_at_utc": "2026-11-27T18:00:00+00:00",
            "evidence_role": "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
            "cohort": "overall global league rank",
            "rank_limit": 10000,
            "manager_count": 3,
            "rank_strata_count_observed": 3,
            "field_weighting": "normalized_existing_rank_stratified_sample_weights",
            "manager_entry_ids_retained": False,
        },
        "portfolios": portfolios,
    }


def test_summary_emits_weighted_exposure_and_co_selection_without_portfolios():
    artifact = sample_artifact()
    result = summarize_field_portfolio_sample(artifact)
    exposure = {row["player_id"]: row for row in result["player_exposure_top"]}
    assert result["data_status"] == "AGGREGATE_ONLY_PRE_DEADLINE_PORTFOLIO_STRUCTURE"
    assert result["metadata"]["manager_count"] == 3
    assert result["metadata"]["effective_sample_size"] == 3
    assert exposure["1"]["squad_exposure"] == pytest.approx(2 / 3)
    assert exposure["1"]["starting_xi_exposure"] == pytest.approx(2 / 3)
    assert exposure["1"]["captain_exposure"] == pytest.approx(1 / 3)
    assert exposure["1"]["triple_captain_exposure"] == pytest.approx(1 / 3)
    pair = next(row for row in result["positive_squad_co_selection"] if (row["player_id_a"], row["player_id_b"]) == ("1", "2"))
    assert pair["joint_exposure"] == pytest.approx(2 / 3)
    assert pair["co_selection_covariance"] == pytest.approx(2 / 9)
    assert result["portfolio_overlap"]["squad_shared_players"]["mean"] == pytest.approx(10)
    assert "field_sample_0001" not in str(result)
    assert result["decision_weight"] == 0
    assert result["production_eligible"] is False


def test_summary_rejects_non_normalized_weights():
    artifact = sample_artifact()
    artifact["portfolios"][0]["field_weight"] = 0.5
    with pytest.raises(CovarFieldPortfolioSummaryError, match="normalized to one"):
        summarize_field_portfolio_sample(artifact)


def test_summary_rejects_invalid_manager_portfolio_shape():
    artifact = sample_artifact()
    artifact["portfolios"][0]["starting_player_ids"].pop()
    with pytest.raises(CovarFieldPortfolioSummaryError, match="11 starters"):
        summarize_field_portfolio_sample(artifact)


def test_summary_rejects_bench_captain():
    artifact = sample_artifact()
    artifact["portfolios"][0]["captain_id"] = artifact["portfolios"][0]["bench_order"][0]
    with pytest.raises(CovarFieldPortfolioSummaryError, match="starting players"):
        summarize_field_portfolio_sample(artifact)
