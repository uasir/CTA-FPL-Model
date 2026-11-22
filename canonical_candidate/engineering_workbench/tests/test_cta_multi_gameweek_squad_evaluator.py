from __future__ import annotations

import unittest

from cta_multi_gameweek_squad_evaluator import (
    CTAMultiGameweekSquadError,
    evaluate_cta_five_gameweek_squad,
)


def fixture_inputs():
    positions = {
        **{i: "GKP" for i in (1, 2)},
        **{i: "DEF" for i in range(3, 8)},
        **{i: "MID" for i in range(8, 13)},
        **{i: "FWD" for i in range(13, 16)},
        16: "MID",
    }
    squad = [{"fpl_element_id": i, "purchase_price": 5.0} for i in range(1, 16)]
    panels = []
    for gw in range(12, 17):
        rows = []
        for pid, pos in positions.items():
            points = 2.0
            if pid == 8:
                points = 3.0
            if pid == 16:
                points = 5.0
            rows.append({
                "fpl_element_id": pid, "position": pos,
                "team_id": 1 + (pid % 10), "price": 5.0,
                "expected_points": points, "expected_minutes": 80.0,
            })
        panels.append({"gameweek": gw, "player_forecasts": rows})
    manager = {"squad_snapshot": squad, "bank": 0.0, "free_transfers": 1}
    xi = [1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15]
    return panels, manager, xi


class CTAMultiGameweekSquadEvaluatorTests(unittest.TestCase):
    def test_transfer_uses_cumulative_five_gameweek_xp_and_weekly_panels(self):
        panels, manager, xi = fixture_inputs()
        result = evaluate_cta_five_gameweek_squad(panels, manager, starting_xi_ids=xi)
        self.assertEqual(result["horizon_gameweeks"], [12, 13, 14, 15, 16])
        self.assertGreater(result["candidate_count"], 0)
        best = result["best_diagnostic"]
        self.assertIn(best["transfer_out_id"], {8, 9, 10, 11})
        self.assertEqual(best["transfer_in_id"], 16)
        self.assertAlmostEqual(best["gross_horizon_expected_points_delta"], 15.0)
        self.assertEqual(len(best["weekly_comparison"]), 5)
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["decision_weight"], 0)
        self.assertFalse(result["covar_used"])

    def test_rejects_incomplete_five_week_horizon(self):
        panels, manager, xi = fixture_inputs()
        with self.assertRaises(CTAMultiGameweekSquadError):
            evaluate_cta_five_gameweek_squad(panels[:4], manager, starting_xi_ids=xi)

    def test_rejects_missing_owned_player_in_any_week(self):
        panels, manager, xi = fixture_inputs()
        panels[2]["player_forecasts"] = [
            row for row in panels[2]["player_forecasts"]
            if row["fpl_element_id"] != 12
        ]
        with self.assertRaises(CTAMultiGameweekSquadError):
            evaluate_cta_five_gameweek_squad(panels, manager, starting_xi_ids=xi)


if __name__ == "__main__":
    unittest.main()
