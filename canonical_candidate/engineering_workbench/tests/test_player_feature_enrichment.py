import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from enrich_player_features import enrich

def player_row(sbid="123"):
    return {"statsbomb_player_id":sbid,"statsbomb_player_name":"Example Player","passes":4}
def mapping(**kw):
    row={"season":"2026-27","competition_id":"2","statsbomb_player_id":"123","statsbomb_player_name":"Example Player",
         "fpl_element_id":"10","fpl_player_code":"90010","fpl_player_name":"Example","fpl_team_name":"Arsenal",
         "verification_status":"verified"}
    row.update(kw);return row
def fpl_row(**kw):
    row={"season":"2026-27","fpl_element_id":"10","fpl_player_code":"90010","web_name":"Example",
         "team_id":"1","team_name":"Arsenal","position":"Midfielder"}
    row.update(kw);return row

class EnrichmentTests(unittest.TestCase):
    def test_verified_id_mapping_enriches_player(self):
        rows,report=enrich([player_row()],[mapping()],[fpl_row()],"2026-27","2")
        self.assertEqual(report["status"],"PASS");self.assertTrue(report["join_ready"])
        self.assertEqual(rows[0]["fpl_element_id"],"10");self.assertEqual(rows[0]["fpl_position"],"Midfielder")
    def test_empty_crosswalk_is_not_ready(self):
        rows,report=enrich([player_row()],[],[fpl_row()],"2026-27","2")
        self.assertEqual(report["status"],"EMPTY_NOT_READY");self.assertFalse(report["join_ready"])
        self.assertEqual(rows[0]["fpl_join_status"],"UNMAPPED")
    def test_wrong_season_or_competition_does_not_join(self):
        rows,report=enrich([player_row()],[mapping(season="2015-16")],[fpl_row()],"2026-27","2")
        self.assertEqual(report["status"],"NO_MATCHING_CROSSWALK");self.assertFalse(report["join_ready"])
    def test_partial_mapping_is_not_ready(self):
        rows,report=enrich([player_row("123"),player_row("456")],[mapping()],[fpl_row()],"2026-27","2")
        self.assertEqual(report["status"],"PARTIAL_NOT_READY");self.assertEqual(report["mapped_rows"],1)
    def test_mismatched_fpl_code_blocks(self):
        rows,report=enrich([player_row()],[mapping()],[fpl_row(fpl_player_code="99999")],"2026-27","2")
        self.assertEqual(report["status"],"BLOCKED");self.assertFalse(report["join_ready"])
if __name__=="__main__":unittest.main()
