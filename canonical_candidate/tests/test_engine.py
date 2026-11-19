import unittest
from src.cta_engine import flatten_matches, build_features, fit_xt, audit_360, write_csv, complete_statsbomb_directions

class CTATests(unittest.TestCase):
    def setUp(self):
        self.raw = [
            {"id":"1","type":{"name":"Pass"},"team":{"name":"A"},"possession_team":{"name":"A"},
             "possession":1,"period":1,"minute":1,"second":0,"player":{"id":1,"name":"P"},
             "location":[70,30],"pass":{"end_location":[110,40],"recipient":{"id":2,"name":"Q"}}},
            {"id":"2","type":{"name":"Ball Receipt*"},"team":{"name":"A"},"possession_team":{"name":"A"},
             "possession":1,"period":1,"minute":1,"second":2,"player":{"id":2,"name":"Q"},"location":[110,40],
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
        self.assertEqual(players["1"]["passes"], 1)
        self.assertEqual(players["2"]["pressured_receipts"], 1)
    def test_same_name_different_statsbomb_ids_remain_distinct(self):
        raw = [
            {"id":"a","type":{"name":"Pass"},"team":{"name":"A"},"possession_team":{"name":"A"},
             "possession":1,"period":1,"minute":1,"second":0,"player":{"id":11,"name":"Same"},
             "location":[70,30],"pass":{"end_location":[80,40],"recipient":{"id":22,"name":"Same"}}},
            {"id":"b","type":{"name":"Ball Receipt*"},"team":{"name":"A"},"possession_team":{"name":"A"},
             "possession":1,"period":1,"minute":1,"second":2,"player":{"id":22,"name":"Same"},"location":[80,40]},
        ]
        ev = flatten_matches([("m1", raw)])
        _, players = build_features(ev, {("m1",1,"A"):True}, None)
        self.assertEqual(set(players), {"11","22"})
        self.assertEqual(players["11"]["passes"], 1)
        self.assertEqual(players["22"]["passes_received"], 1)
        self.assertEqual(players["22"]["statsbomb_player_name"], "Same")

    def test_player_name_without_statsbomb_id_is_rejected(self):
        bad = [dict(self.raw[0], player={"name":"P"})]
        ev = flatten_matches([("m1", bad)])
        with self.assertRaisesRegex(ValueError, "no ID"):
            build_features(ev, {("m1",1,"A"):True}, None)

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
        self.assertEqual(audit["xt_fit_match_ids"], "ALL_INPUT_MATCHES")
        self.assertEqual(audit["xt_fit_match_count"], 1)
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
        self.assertEqual(result["unique_match_event_keys"], 2)

    def test_360_audit_rejects_cross_match_uuid_collision(self):
        ev = flatten_matches([("match-B", self.raw)])
        import tempfile, json, pathlib
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "match-A.json").write_text(json.dumps([
                {"event_uuid":"1","freeze_frame":[]},
                {"event_uuid":"2","freeze_frame":[]}
            ]))
            result = audit_360(ev, d)
        self.assertEqual(result["matched_frame_uuids"], 0)
        self.assertEqual(result["unmatched_frame_uuids"], 2)
        self.assertEqual(result["frame_to_event_join_rate"], 0.0)
        self.assertEqual(result["event_coverage_with_frame"], 0.0)

if __name__ == "__main__":
    unittest.main()


    def test_xt_can_be_fitted_on_training_matches_only(self):
        training_shot = {
            "id": "train-shot", "type": {"name": "Shot"},
            "team": {"name": "A"}, "possession_team": {"name": "A"},
            "period": 1, "location": [110, 40],
            "shot": {"outcome": {"name": "Goal"}},
        }
        heldout_shot = {
            "id": "heldout-shot", "type": {"name": "Shot"},
            "team": {"name": "B"}, "possession_team": {"name": "B"},
            "period": 1, "location": [110, 40],
            "shot": {"outcome": {"name": "Off T"}},
        }
        ev = flatten_matches([("train", [training_shot]), ("heldout", [heldout_shot])])
        directions = complete_statsbomb_directions(ev, {})
        values, audit = fit_xt(ev, directions, fit_match_ids=["train"])
        self.assertIsNotNone(values)
        self.assertEqual(audit["xt_shots"], 1)
        self.assertEqual(audit["xt_goals"], 1)
        self.assertEqual(audit["xt_fit_match_ids"], ["train"])
        self.assertEqual(audit["xt_fit_match_count"], 1)

    def test_xt_training_match_subset_rejects_unknown_ids(self):
        ev = flatten_matches([("train", self.raw)])
        with self.assertRaisesRegex(ValueError, "absent from input"):
            fit_xt(ev, complete_statsbomb_directions(ev, {}), fit_match_ids=["missing"])
