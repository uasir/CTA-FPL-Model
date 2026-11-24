from evaluate_cta_abc_wyscout import evaluate, split_chronologically


def _rows():
    rows = []
    for gw in range(1, 11):
        for player in range(1, 11):
            p3 = float(player % 5 + gw / 10)
            m3 = float(45 + player)
            points = 1.0 + 0.5 * p3 + 0.02 * m3 + 0.1 * (player % 3)
            rows.append({
                "research_eligible_for_analysis": True,
                "fpl_element_id": str(player),
                "kickoff_time_utc": f"2017-08-{gw:02d}T12:00:00+00:00",
                "target_fpl_total_points": points,
                "fpl_total_points_prior_3_avg": p3,
                "fpl_total_points_prior_5_avg": p3 - 0.1,
                "fpl_minutes_prior_3_avg": m3,
                "fpl_minutes_prior_5_avg": m3 - 2,
                "abc_progressive_passes": float(player % 4),
                "abc_duel_success_rate": float((player % 4) / 4),
                "abc_minutes_trend": float(gw % 3),
            })
    return rows


def test_chronological_split_keeps_all_players_at_a_kickoff_together():
    train, test, cutoff = split_chronologically(_rows(), 0.7)
    assert max(row["kickoff_time_utc"] for row in train) < cutoff
    assert min(row["kickoff_time_utc"] for row in test) >= cutoff
    assert {row["kickoff_time_utc"] for row in train}.isdisjoint(
        {row["kickoff_time_utc"] for row in test}
    )


def test_abc_ablation_compares_all_layers_on_same_holdout():
    report = evaluate(_rows(), {}, train_fraction=0.7, ridge_lambda=1.0, n_boot=100)
    assert report["status"] == "PASS_EXPLORATORY_CHRONOLOGICAL_ABC_COMPARISON"
    assert report["train_rows"] == 70
    assert report["test_rows"] == 30
    assert set(report["models"]) == {
        "FPL_HISTORY_ONLY", "FPL_PLUS_A", "FPL_PLUS_B", "FPL_PLUS_C",
        "FPL_PLUS_AB", "FPL_PLUS_AC", "FPL_PLUS_BC", "FPL_PLUS_ABC",
    }
    assert set(report["paired_comparisons_vs_conventional"]) == {
        "FPL_PLUS_A", "FPL_PLUS_B", "FPL_PLUS_C",
        "FPL_PLUS_AB", "FPL_PLUS_AC", "FPL_PLUS_BC", "FPL_PLUS_ABC",
    }
    assert report["point_in_time_status"] == "NOT_VERIFIED"
    assert report["promotion_status"] == "RESEARCH_ONLY_DO_NOT_PROMOTE"
    for result in report["models"].values():
        assert result["forecast"]["point_errors"]["n"] == 30
