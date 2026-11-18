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
        self.assertEqual(by_id["12"]["owned_by_pct"],100.0)
        self.assertEqual(by_id["12"]["starting_pct"],0.0)
        self.assertEqual(by_id["12"]["effective_ownership_pct"],100.0)
        self.assertEqual(by_id["12"]["scoring_exposure_pct"],0.0)
        self.assertEqual(report["status"],"SAMPLE_ESTIMATE_NOT_GLOBAL_CENSUS")

    def test_triple_captain_adds_two_extra_exposure_units(self):
        rows=manager(1,1,"3xc")
        output,_=estimate_effective_ownership(rows)
        haaland=next(x for x in output if x["fpl_element_id"]=="1")
        self.assertEqual(haaland["owned_by_pct"],100.0)
        self.assertEqual(haaland["captain_pct"],100.0)
        self.assertEqual(haaland["triple_captain_pct"],100.0)
        self.assertEqual(haaland["effective_ownership_pct"],300.0)

    def test_bench_ownership_is_counted_without_bench_boost(self):
        rows=manager(1,1)
        output,_=estimate_effective_ownership(rows)
        bench=next(x for x in output if x["fpl_element_id"]=="15")
        self.assertEqual(bench["owned_by_pct"],100.0)
        self.assertEqual(bench["starting_pct"],0.0)
        self.assertEqual(bench["effective_ownership_pct"],100.0)
        self.assertEqual(bench["scoring_exposure_pct"],0.0)

    def test_bench_boost_changes_scoring_exposure_not_standard_ownership(self):
        rows=manager(1,1,"bboost")
        output,_=estimate_effective_ownership(rows)
        bench=next(x for x in output if x["fpl_element_id"]=="15")
        self.assertEqual(bench["owned_by_pct"],100.0)
        self.assertEqual(bench["effective_ownership_pct"],100.0)
        self.assertEqual(bench["scoring_exposure_pct"],100.0)

    def test_weighted_sample(self):
        rows=manager(1,1,weight=3)+manager(2,2,weight=1)
        output,_=estimate_effective_ownership(rows)
        haaland=next(x for x in output if x["fpl_element_id"]=="1")
        self.assertEqual(haaland["owned_by_pct"],100.0)
        self.assertEqual(haaland["captain_pct"],75.0)
        self.assertEqual(haaland["effective_ownership_pct"],175.0)

    def test_rank_stratified_sample_reports_confidence_intervals(self):
        rows=[]
        for entry,rank,captain in [
            (1,1,1),(2,25,2),(3,51,1),(4,99,2)
        ]:
            sample=manager(entry,captain,weight=25)
            for row in sample:
                row["rank_before_deadline"]=str(rank)
            rows.extend(sample)
        output,report=estimate_effective_ownership(rows)
        haaland=next(x for x in output if x["fpl_element_id"]=="1")
        self.assertEqual(haaland["effective_ownership_pct"],150.0)
        self.assertLess(haaland["effective_ownership_pct_ci95_low"],150.0)
        self.assertGreater(haaland["effective_ownership_pct_ci95_high"],150.0)
        self.assertEqual(haaland["owned_by_pct_ci95_high"],100.0)
        self.assertTrue(report["rank_stratified"])
        self.assertEqual(report["rank_strata_count"],2)
        self.assertEqual(report["sampled_managers_per_rank_stratum"],2)
        self.assertEqual(report["effective_sample_size"],4.0)
        self.assertTrue(report["confidence_interval"]["intervals_available"])

    def test_requires_fifteen_picks_and_one_captain(self):
        with self.assertRaises(ValueError):
            estimate_effective_ownership(manager(1,1)[:-1])
        bad=manager(1,1)
        bad[1]["is_captain"]="true"
        with self.assertRaises(ValueError):
            estimate_effective_ownership(bad)


if __name__=="__main__":
    unittest.main()
