import unittest
from estimate_fpl_effective_ownership import estimate_effective_ownership


def manager(entry, captain_id, chip=None, weight=1):
    rows=[]
    for pos in range(1,16):
        rows.append({
            "gameweek":"11","entry_id":str(entry),"fpl_element_id":str(pos),
            "position":str(pos),"is_captain":str(pos==captain_id).lower(),
            "active_chip":chip or "","sample_weight":str(weight)
        })
    return rows


class EffectiveOwnershipTests(unittest.TestCase):
    def test_regular_lineup_and_captain_exposure(self):
        rows=manager(1,1)+manager(2,2)
        output,report=estimate_effective_ownership(rows)
        by_id={x["fpl_element_id"]:x for x in output}
        self.assertEqual(by_id["1"]["owned_by_pct"],100.0)
        self.assertEqual(by_id["1"]["captain_pct"],50.0)
        self.assertEqual(by_id["1"]["effective_ownership_pct"],150.0)
        self.assertEqual(by_id["12"]["owned_by_pct"],0.0)
        self.assertEqual(report["status"],"SAMPLE_ESTIMATE_NOT_GLOBAL_CENSUS")

    def test_triple_captain_adds_two_extra_exposure_units(self):
        rows=manager(1,1,"3xc")
        output,_=estimate_effective_ownership(rows)
        haaland=next(x for x in output if x["fpl_element_id"]=="1")
        self.assertEqual(haaland["owned_by_pct"],100.0)
        self.assertEqual(haaland["captain_pct"],100.0)
        self.assertEqual(haaland["triple_captain_pct"],100.0)
        self.assertEqual(haaland["effective_ownership_pct"],300.0)

    def test_bench_boost_counts_all_fifteen_players(self):
        rows=manager(1,1,"bboost")
        output,_=estimate_effective_ownership(rows)
        by_id={x["fpl_element_id"]:x for x in output}
        self.assertEqual(by_id["15"]["owned_by_pct"],100.0)
        self.assertEqual(by_id["15"]["effective_ownership_pct"],100.0)

    def test_weighted_sample(self):
        rows=manager(1,1,weight=3)+manager(2,2,weight=1)
        output,_=estimate_effective_ownership(rows)
        haaland=next(x for x in output if x["fpl_element_id"]=="1")
        self.assertEqual(haaland["owned_by_pct"],100.0)
        self.assertEqual(haaland["captain_pct"],75.0)
        self.assertEqual(haaland["effective_ownership_pct"],175.0)

    def test_requires_fifteen_picks_and_one_captain(self):
        with self.assertRaises(ValueError):
            estimate_effective_ownership(manager(1,1)[:-1])
        bad=manager(1,1)
        bad[1]["is_captain"]="true"
        with self.assertRaises(ValueError):
            estimate_effective_ownership(bad)


if __name__=="__main__":
    unittest.main()
