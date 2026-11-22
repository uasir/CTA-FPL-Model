from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_dastan_minutes_inference import apply_minutes_curve, predict_rows


FEATURES = [f"feature_{i}" for i in range(286)]
SCHEMA = {"feature_order": FEATURES}
CALIBRATION = {
    "curve": {
        position: {
            "p60": [0.0, 0.5, 1.0],
            "e_minutes": [0.0, 45.0, 90.0],
            "p_any": [0.0, 0.6, 1.0],
        }
        for position in ("GKP", "DEF", "MID", "FWD")
    }
}


def row(code="100", fixture="900", position="MID"):
    result = {
        "season": "2026-27", "gameweek": "12", "fpl_code": code,
        "fpl_element_id": "7", "fixture_id": fixture, "position": position,
    }
    result.update({feature: "0" for feature in FEATURES})
    return result


class DastanMinutesInferenceTests(unittest.TestCase):
    def test_curve_obeys_minutes_and_probability_invariants(self):
        minutes, p_any = apply_minutes_curve(np.array([0.0, 0.5, 1.0]), CALIBRATION["curve"]["MID"])
        self.assertTrue(np.all(minutes >= 60.0 * np.array([0.0, 0.5, 1.0])))
        self.assertTrue(np.all((p_any >= 0) & (p_any <= 1)))
        self.assertTrue(np.all((minutes >= 0) & (minutes <= 90)))

    def test_predicts_position_specific_minutes_only(self):
        rows = [row()]
        predictors = {pos: (lambda matrix: np.full(len(matrix), 0.5)) for pos in ("GKP", "DEF", "MID", "FWD")}
        output = predict_rows(rows, SCHEMA, CALIBRATION, predictors)
        self.assertEqual(len(output), 1)
        self.assertAlmostEqual(output[0]["p60"], 0.5)
        self.assertAlmostEqual(output[0]["expected_minutes"], 45.0)
        self.assertFalse(output[0]["points_model_used"])

    def test_duplicate_fixture_player_key_rejected(self):
        predictors = {pos: (lambda matrix: np.full(len(matrix), 0.5)) for pos in ("GKP", "DEF", "MID", "FWD")}
        with self.assertRaisesRegex(ValueError, "duplicate player-fixture"):
            predict_rows([row(), row()], SCHEMA, CALIBRATION, predictors)

    def test_missing_or_nonfinite_feature_rejected(self):
        predictors = {pos: (lambda matrix: np.full(len(matrix), 0.5)) for pos in ("GKP", "DEF", "MID", "FWD")}
        missing = row()
        missing[FEATURES[0]] = ""
        with self.assertRaisesRegex(ValueError, "missing feature"):
            predict_rows([missing], SCHEMA, CALIBRATION, predictors)
        invalid = row()
        invalid[FEATURES[0]] = "nan"
        with self.assertRaisesRegex(ValueError, "non-finite"):
            predict_rows([invalid], SCHEMA, CALIBRATION, predictors)


if __name__ == "__main__":
    unittest.main()
