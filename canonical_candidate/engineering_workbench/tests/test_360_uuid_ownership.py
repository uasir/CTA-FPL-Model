import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from diagnose_360_uuid_ownership import scan_uuid_ownership

class UUIDOwnershipTests(unittest.TestCase):
    def test_detects_frame_uuids_owned_by_another_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); events=root/"events"; events.mkdir()
            (events/"3837706.json").write_text(json.dumps([{"id":"event-a","team":{"name":"PSG"}}]))
            (events/"9999999.json").write_text(json.dumps([{"id":"frame-x","team":{"name":"Other FC"}}]))
            frames=root/"frames.json"; frames.write_text(json.dumps([{"event_uuid":"frame-x"}]))
            r=scan_uuid_ownership(events,frames,"3837706")
            self.assertEqual(r["status"],"SOURCE_MISMATCH_SUSPECTED")
            self.assertEqual(r["other_match_hits"][0]["match_id"],"9999999")

    def test_keeps_unmatched_source_unresolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); events=root/"events"; events.mkdir()
            (events/"3837706.json").write_text(json.dumps([{"id":"event-a","team":{"name":"PSG"}}]))
            frames=root/"frames.json"; frames.write_text(json.dumps([{"event_uuid":"frame-x"}]))
            r=scan_uuid_ownership(events,frames,"3837706")
            self.assertEqual(r["status"],"UNRESOLVED_NO_MATCH_IN_SAMPLE")
            self.assertEqual(r["same_match_shared_uuids"],0)

if __name__=="__main__": unittest.main()
