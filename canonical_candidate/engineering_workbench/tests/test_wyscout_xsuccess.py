import unittest
from evaluate_wyscout_xsuccess import build_pass_samples, evaluate


class XSuccessTests(unittest.TestCase):
    def test_unknown_outcomes_are_excluded(self):
        events = [
            {"eventName": "Pass", "matchId": 1, "positions": [{"x": 10, "y": 20}, {"x": 20, "y": 30}], "tags": [{"id": 1801}]},
            {"eventName": "Pass", "matchId": 1, "positions": [{"x": 10, "y": 20}, {"x": 20, "y": 30}], "tags": []},
        ]
        rows = build_pass_samples(events, {"1": "2017-08-01"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["completed"], 1)

    def test_actual_endpoint_is_excluded_from_pre_action_features(self):
        common = {"eventName": "Pass", "matchId": 1, "eventSec": 120,
                  "subEventName": "Simple pass", "tags": [{"id": 1801}]}
        first = dict(common, positions=[{"x": 20, "y": 30}, {"x": 35, "y": 40}])
        second = dict(common, positions=[{"x": 20, "y": 30}, {"x": 95, "y": 90}])
        rows = build_pass_samples([first, second], {"1": "2017-08-01"})
        self.assertEqual(rows[0]["features"], rows[1]["features"])
        self.assertEqual(rows[0]["subevent"], rows[1]["subevent"])

    def test_chronological_evaluation(self):
        samples = []
        for match in range(1, 9):
            for idx in range(30):
                samples.append({
                    "match_id": str(match), "match_date": f"2017-08-{match:02d}",
                    "features": [idx / 30, 0.2, 0.4, 0.5, (idx % 5) / 5, 0.1, 0.3, 0.2, 0.0, 0.0],
                    "completed": int(idx % 5 != 0),
                })
        report = evaluate(samples)
        self.assertEqual(report["train_matches"], 5)
        self.assertEqual(report["test_matches"], 3)
        self.assertFalse(report["cta_decision_weight_applied"])
        self.assertIn("brier", report["test_metrics"])


if __name__ == "__main__":
    unittest.main()
