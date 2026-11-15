import unittest
from cta_audit.xt import train_xt

CFG={"grid_x":2,"grid_y":1,"pitch_length":100,"pitch_width":50,"max_iterations":1000,"convergence_tolerance":1e-12,
 "action_type_field":"action_type","outcome_field":"outcome","start_x_field":"x","start_y_field":"y","end_x_field":"end_x","end_y_field":"end_y",
 "shot_actions":["shot"],"move_actions":["pass","carry"],"success_values":["complete"],"goal_values":["goal"]}

class XTTests(unittest.TestCase):
 def test_transition_to_shot_zone_has_positive_value(self):
  rows=[
   {"action_type":"pass","outcome":"complete","x":10,"y":20,"end_x":75,"end_y":20},
   {"action_type":"shot","outcome":"goal","x":75,"y":20},
   {"action_type":"shot","outcome":"saved","x":75,"y":20}
  ]
  r=train_xt(rows,CFG)
  self.assertTrue(r["solver"]["converged"])
  self.assertGreater(r["grid"][0][0],0)
  self.assertAlmostEqual(r["grid"][0][1],0.5)
 def test_failed_pass_is_not_a_transition(self):
  rows=[{"action_type":"pass","outcome":"incomplete","x":10,"y":20,"end_x":75,"end_y":20}]
  r=train_xt(rows,CFG)
  self.assertEqual(r["counts"]["successful_moves"],0)
 def test_unknown_action_excluded(self):
  r=train_xt([{"action_type":"foul","outcome":"won","x":10,"y":20}],CFG)
  self.assertEqual(r["excluded"]["excluded_unknown_action"],1)

if __name__ == "__main__": unittest.main()
