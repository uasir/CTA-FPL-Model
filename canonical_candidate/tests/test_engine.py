import unittest
from src.cta_engine import flatten_matches, build_features, fit_xt, audit_360, write_csv, complete_statsbomb_directions

class CTATests(unittest.TestCase):
    def setUp(self):
        self.raw = [
            {"id":"1","type":{"name":"Pass"},"team":{"name":"A"},"possession_team":{"name":"A"},
             "possession":1,"period":1,"minute":1,"second":0,"player":{"name":"P"},
             "location":[70,30],"pass":{"end_location":[110,40],"recipient":{"name":"Q"}}},
            {"id":"2","type":{"name":"Ball Receipt*"},"team":{"name":"A"},"possession_team":{"name":"A"},
             "possession":1,"period":1,"minute":1,"second":2,"player":{"name":"Q"},"location":[110,40],
             "under_pressure":True},
        ]
    def test_statsbomb_direction_defaults_to_attacking_right(self):
        ev = flatten_matches([("m1", self.raw)])
        directions = complete_statsbomb_directions(ev, {})
        self.assertEqual(directions[("m1", 1, "A")], True)
    def test_statsbomb_false_direction_override_is_rejected(self):
        ev = flatten_matches([("m1", self.raw)])
        with self.assertRaises(ValueError):
            complete_statsbomb_directions(ev, {("m1", 1, "A"): False})
    def test_spatial_metrics_with_direction(self):
        ev = flatten_matches([("m1", self.raw)])
        seq, players = build_features(ev, {("m1",1,"A"):True}, None)
        self.assertEqual(seq[0]["box_entries"], 1)
        self.assertEqual(seq[0]["sequence_class"], "non_shot_candidate")
        self.assertEqual(players["P"]["passes"], 1)
        self.assertEqual(players["Q"]["pressured_receipts"], 1)
    def test_spatial_metrics_withheld_without_direction(self):
        ev = flatten_matches([("m1", self.raw)])
        seq, _ = build_features(ev, {}, None)
        self.assertEqual(seq[0]["box_entries"], "")
        self.assertEqual(seq[0]["sequence_class"], "other_possession")
    def test_xt_requires_shots_and_direction(self):
        ev = flatten_matches([("m1", self.raw)])
        values, audit = fit_xt(ev, {("m1",1,"A"):True})
        self.assertIsNone(values)
        self.assertEqual(audit["xt_status"], "not_fitted_no_directional_shots")
    def test_csv_writer_unions_sparse_player_fields(self):
        import tempfile, pathlib, csv
        rows = [
            {"player": "A", "passes": 1},
            {"player": "B", "shots": 1},
        ]
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d, "players.csv")
            write_csv(path, rows)
            with path.open(newline="", encoding="utf-8") as f:
                result = list(csv.DictReader(f))
        self.assertEqual(result[0]["passes"], "1")
        self.assertEqual(result[0]["shots"], "")
        self.assertEqual(result[1]["shots"], "1")
        self.assertEqual(result[1]["passes"], "")
    def test_360_audit_join_rate(self):
        ev = flatten_matches([("m1", self.raw)])
        import tempfile, json, pathlib
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "m1.json").write_text(json.dumps([
                {"event_uuid":"1","freeze_frame":[]},{"event_uuid":"2","freeze_frame":[]}
            ]))
            result = audit_360(ev, d)
        self.assertEqual(result["frame_to_event_join_rate"], 1.0)
        self.assertEqual(result["event_coverage_with_frame"], 1.0)

if __name__ == "__main__":
    unittest.main()
