import unittest
from evaluate_wyscout_temporal_xt import build_temporal_samples, evaluate


def event(match, idx, sec, kind, x=60, y=40, possession=1, outcome=None):
    row = {
        "_match_id": str(match), "_event_index": idx, "period": 1,
        "minute": 0, "second": sec, "possession": possession,
        "possession_team": {"name": "A"}, "type": {"name": kind},
        "location": [x, y],
    }
    if kind == "Shot":
        row["shot"] = {"outcome": {"name": outcome or "Saved"}}
    return row


class TemporalXTTests(unittest.TestCase):
    def test_labels_only_look_forward_within_same_possession(self):
        events = [
            event(1, 0, 1, "Pass"),
            event(1, 1, 4, "Shot", outcome="Goal"),
            event(1, 2, 7, "Pass", possession=2),
        ]
        samples = build_temporal_samples(events, {"1": "2017-08-01"})
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0]["labels"]["5"]["goal"], 1)
        self.assertEqual(samples[0]["labels"]["5"]["shot"], 1)

    def test_goal_outside_horizon_is_not_positive(self):
        events = [event(1, 0, 1, "Carry"), event(1, 1, 20, "Shot", outcome="Goal")]
        samples = build_temporal_samples(events, {"1": "2017-08-01"})
        self.assertEqual(samples[0]["labels"]["5"]["goal"], 0)
        self.assertEqual(samples[0]["labels"]["30"]["goal"], 1)

    def test_chronological_holdout_and_train_only_fit(self):
        samples = []
        for match in range(1, 9):
            for idx in range(20):
                labels = {"5": {"shot": int(idx % 5 == 0), "goal": int(idx % 10 == 0)},
                          "10": {"shot": int(idx % 4 == 0), "goal": int(idx % 10 == 0)},
                          "15": {"shot": int(idx % 3 == 0), "goal": int(idx % 10 == 0)},
                          "30": {"shot": int(idx % 2 == 0), "goal": int(idx % 10 == 0)}}
                samples.append({"match_id": str(match), "match_date": f"2017-08-{match:02d}",
                                "zone": (idx % 3, 0), "labels": labels})
        report = evaluate(samples)
        self.assertEqual(report["train_matches"], 5)
        self.assertEqual(report["test_matches"], 3)
        self.assertFalse(report["cta_decision_weight_applied"])


if __name__ == "__main__":
    unittest.main()
