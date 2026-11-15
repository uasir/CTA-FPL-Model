import unittest
from cta_audit.contracts import validate_dataset
from cta_audit.audit import audit

CONTRACT = {
 "key_columns": ["match_id", "event_id"],
 "required_columns": ["match_id", "event_id", "period"],
 "fields": {
  "match_id": {"type":"string", "required":True, "nullable":False},
  "event_id": {"type":"string", "required":True, "nullable":False},
  "period": {"type":"integer", "required":True, "nullable":False, "min":1},
  "x": {"type":"number", "required":False, "nullable":True, "min":0, "max":120}
 }
}

class ContractTests(unittest.TestCase):
 def test_valid_rows_pass(self):
  r=validate_dataset([{"match_id":"m1","event_id":"e1","period":1,"x":40.2}],CONTRACT,"events")
  self.assertEqual(r["status"],"PASS")
 def test_missing_required_column_fails(self):
  r=validate_dataset([{"match_id":"m1","event_id":"e1"}],CONTRACT,"events")
  self.assertEqual(r["status"],"FAIL")
  self.assertIn("missing_required_columns",[e["code"] for e in r["errors"]])
 def test_duplicate_keys_fail(self):
  row={"match_id":"m1","event_id":"e1","period":1}
  r=validate_dataset([row,row.copy()],CONTRACT,"events")
  self.assertIn("duplicate_keys",[e["code"] for e in r["errors"]])
 def test_null_key_fails(self):
  r=validate_dataset([{"match_id":None,"event_id":"e1","period":1}],CONTRACT,"events")
  self.assertIn("null_key_values",[e["code"] for e in r["errors"]])
 def test_range_violation_fails(self):
  r=validate_dataset([{"match_id":"m1","event_id":"e1","period":1,"x":130}],CONTRACT,"events")
  self.assertIn("invalid_value",[e["code"] for e in r["errors"]])
 def test_audit_null_key_is_not_shared(self):
  reg={"key_columns":["match_id","event_id"],"features":{"v":{"type":"numeric","nullable":True}},"tolerances":{"default_numeric":{"rtol":1e-7,"atol":1e-9}}}
  a={"match_id":None,"event_id":"e1","v":1}
  r=audit([a],[a.copy()],reg)
  self.assertEqual(r["summary"]["python_null_key_rows"],1)
  self.assertEqual(r["summary"]["status"],"FAIL")

if __name__ == "__main__": unittest.main()
