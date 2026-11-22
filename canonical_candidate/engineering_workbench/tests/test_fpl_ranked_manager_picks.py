import unittest
from datetime import datetime,timezone
from capture_fpl_ranked_manager_picks import choose_pages,select_managers,normalize_picks,capture,official_player_ids


class RankedManagerSampleTests(unittest.TestCase):
    def test_official_player_universe_uses_bootstrap_elements(self):
        self.assertEqual(official_player_ids({"elements":[{"id":4},{"id":9}]}),[4,9])

    def test_official_player_universe_rejects_missing_or_duplicate_ids(self):
        with self.assertRaisesRegex(ValueError,"non-empty elements"):
            official_player_ids({"events":[]})
        with self.assertRaisesRegex(ValueError,"duplicate"):
            official_player_ids({"elements":[{"id":4},{"id":4}]})

    def test_rank_page_sampling_covers_every_page_deterministically(self):
        a=choose_pages(10000,400,7)
        b=choose_pages(10000,400,7)
        self.assertEqual(a,b)
        self.assertEqual(len(a),200)
        self.assertEqual(a,list(range(1,201)))

    def test_select_managers_samples_two_from_every_page_with_equal_weights(self):
        payloads={
            1:{"standings":{"results":[{"entry":101+i,"rank":1+i} for i in range(50)]}},
            2:{"standings":{"results":[{"entry":201+i,"rank":51+i} for i in range(50)]}},
        }
        managers=select_managers(payloads,4,100,5)
        self.assertEqual(len(managers),4)
        self.assertEqual({x["sample_weight"] for x in managers},{25.0})
        self.assertEqual({x["page_standings"] for x in managers},{1,2})
        self.assertEqual(sum(x["page_standings"]==1 for x in managers),2)
        self.assertEqual(sum(x["page_standings"]==2 for x in managers),2)
        self.assertTrue(all(1<=x["rank_before_deadline"]<=100 for x in managers))

    def test_select_managers_rejects_incomplete_rank_page(self):
        payloads={
            1:{"standings":{"results":[{"entry":101+i,"rank":1+i} for i in range(49)]}},
            2:{"standings":{"results":[{"entry":201+i,"rank":51+i} for i in range(50)]}},
        }
        with self.assertRaisesRegex(ValueError,"incomplete"):
            select_managers(payloads,4,100,5)

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
        rows,report=capture(
            bootstrap,
            force=False,
            now_fn=lambda: datetime(2026,11,21,10,50,tzinfo=timezone.utc),
        )
        self.assertEqual(rows,[])
        self.assertEqual(report["status"],"SKIPPED_OUTSIDE_DEADLINE_WINDOW")


if __name__=="__main__":
    unittest.main()
