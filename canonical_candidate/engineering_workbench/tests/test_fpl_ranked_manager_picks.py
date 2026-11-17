import unittest
from datetime import datetime,timezone
from capture_fpl_ranked_manager_picks import choose_pages,select_managers,normalize_picks,capture


class RankedManagerSampleTests(unittest.TestCase):
    def test_rank_page_sampling_is_deterministic_and_spread(self):
        a=choose_pages(10000,100,7)
        b=choose_pages(10000,100,7)
        self.assertEqual(a,b)
        self.assertEqual(len(a),100)
        self.assertGreaterEqual(min(a),1)
        self.assertLessEqual(max(a),200)

    def test_select_managers_uses_pre_deadline_ranks_and_weights(self):
        payloads={1:{"standings":{"results":[{"entry":101,"rank":1},{"entry":102,"rank":2}]}},
                  3:{"standings":{"results":[{"entry":201,"rank":101},{"entry":202,"rank":102}]}}}
        managers=select_managers(payloads,2,10000,5)
        self.assertEqual(len(managers),2)
        self.assertEqual({x["sample_weight"] for x in managers},{5000.0})
        self.assertTrue(all(x["rank_before_deadline"] in {1,2,101,102} for x in managers))

    def test_normalizes_picks_and_chip_state(self):
        managers=[{"entry_id":7,"rank_before_deadline":7,"sample_weight":100.0}]
        picks=[{"element":i,"position":i,"is_captain":i==1,"is_vice_captain":i==2} for i in range(1,16)]
        rows=normalize_picks(managers,{7:{"entry_history":{"event":11},"active_chip":"3xc","picks":picks}},11)
        self.assertEqual(len(rows),15)
        self.assertTrue(rows[0]["is_captain"])
        self.assertEqual(rows[0]["active_chip"],"3xc")
        self.assertEqual(rows[0]["sample_weight"],100.0)

    def test_rejects_wrong_event_or_missing_picks(self):
        managers=[{"entry_id":7,"rank_before_deadline":7,"sample_weight":100.0}]
        with self.assertRaises(ValueError):
            normalize_picks(managers,{7:{"entry_history":{"event":10},"picks":[]}},11)

    def test_capture_skips_when_not_near_deadline(self):
        bootstrap={"events":[{"id":11,"deadline_time":"2026-11-21T11:00:00Z"}]}
        rows,report=capture(bootstrap,force=False)
        self.assertEqual(rows,[])
        self.assertEqual(report["status"],"SKIPPED_OUTSIDE_DEADLINE_WINDOW")


if __name__=="__main__":
    unittest.main()
