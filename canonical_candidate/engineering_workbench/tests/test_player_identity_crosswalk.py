import unittest
from validate_player_identity_crosswalk import FIELDS, validate_rows
def row(**updates):
    v={f:"" for f in FIELDS}
    v.update({"season":"2026-27","competition_id":"2","competition_name":"Premier League","statsbomb_player_id":"123","statsbomb_player_name":"Example Player","fpl_element_id":"45","fpl_player_code":"6789","fpl_player_name":"Example","statsbomb_team_name":"Example FC","fpl_team_name":"Example FC","verification_status":"verified","match_method":"manual_source_verified","evidence_source":"official squad record","evidence_url":"https://example.org/player","verified_by":"reviewer","verified_at":"2026-11-17"})
    v.update(updates); return v
class CrosswalkTests(unittest.TestCase):
    def test_verified_evidenced_row_is_accepted(self):
        accepted,report=validate_rows([row()]); self.assertEqual(report["status"],"PASS"); self.assertEqual(len(accepted),1)
    def test_pending_and_ambiguous_are_excluded(self):
        accepted,report=validate_rows([row(verification_status="pending"),row(verification_status="ambiguous")])
        self.assertEqual(report["status"],"PASS"); self.assertEqual(accepted,[]); self.assertEqual(report["non_verified_rows_excluded"],2)
    def test_missing_evidence_is_blocked(self):
        accepted,report=validate_rows([row(evidence_url="")]); self.assertEqual(report["status"],"BLOCKED"); self.assertEqual(accepted,[])
    def test_fuzzy_method_is_blocked(self):
        accepted,report=validate_rows([row(match_method="fuzzy_name")]); self.assertEqual(report["status"],"BLOCKED"); self.assertEqual(accepted,[])
    def test_statsbomb_identity_cannot_map_to_two_fpl_ids(self):
        accepted,report=validate_rows([row(),row(fpl_element_id="46",fpl_player_code="6790")]); self.assertEqual(report["status"],"BLOCKED"); self.assertEqual(accepted,[])
    def test_fpl_element_cannot_map_to_two_statsbomb_ids(self):
        accepted,report=validate_rows([row(),row(statsbomb_player_id="124")]); self.assertEqual(report["status"],"BLOCKED"); self.assertEqual(accepted,[])
if __name__=="__main__": unittest.main()
