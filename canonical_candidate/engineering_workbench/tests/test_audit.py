import unittest
from cta_audit.audit import audit

REG = {"key_columns":["match_id","event_id"],"features":{
 "possession_id":{"type":"categorical","nullable":True},
 "pressure_count":{"type":"integer","nullable":False},
 "support_distance_m":{"type":"numeric","nullable":True,"tolerance_class":"default_numeric"},
 "has_360_frame":{"type":"boolean","nullable":False}},
 "tolerances":{"default_numeric":{"rtol":1e-7,"atol":1e-9}}}
ROW = {"match_id":"m1","event_id":"e1","possession_id":"p1","pressure_count":2,"support_distance_m":4.25,"has_360_frame":True}

class AuditTests(unittest.TestCase):
 def test_identical_outputs_pass(self):
  r=audit([ROW.copy()],[ROW.copy()],REG)
  self.assertEqual(r["summary"]["status"],"PASS")
 def test_numeric_tolerance(self):
  b=ROW.copy(); b["support_distance_m"] += 1e-10
  r=audit([ROW.copy()],[b],REG)
  self.assertEqual(r["summary"]["status"],"PASS")
 def test_numeric_mismatch_fails(self):
  b=ROW.copy(); b["support_distance_m"] += .01
  r=audit([ROW.copy()],[b],REG)
  self.assertEqual(r["summary"]["status"],"FAIL")
 def test_key_mismatch_fails(self):
  b=ROW.copy(); b["event_id"]="e2"
  r=audit([ROW.copy()],[b],REG)
  self.assertEqual(r["summary"]["status"],"FAIL")
 def test_duplicate_key_fails(self):
  r=audit([ROW.copy(),ROW.copy()],[ROW.copy()],REG)
  self.assertEqual(r["summary"]["python_duplicate_keys"],1)
  self.assertEqual(r["summary"]["status"],"FAIL")
 def test_null_vs_zero_is_not_equal(self):
  a=ROW.copy(); b=ROW.copy(); a["support_distance_m"]=None; b["support_distance_m"]=0
  r=audit([a],[b],REG)
  self.assertEqual(r["features"]["support_distance_m"]["null_mismatches"],1)
  self.assertEqual(r["summary"]["status"],"FAIL")
 def test_null_in_non_nullable_feature_fails(self):
  a=ROW.copy(); b=ROW.copy(); a["pressure_count"]=None; b["pressure_count"]=None
  r=audit([a],[b],REG)
  self.assertEqual(r["features"]["pressure_count"]["nullability_violations"],1)
  self.assertEqual(r["summary"]["status"],"FAIL")
 def test_boolean_string_normalization(self):
  b=ROW.copy(); b["has_360_frame"]="true"
  r=audit([ROW.copy()],[b],REG)
  self.assertEqual(r["summary"]["status"],"PASS")

if __name__ == "__main__": unittest.main()
