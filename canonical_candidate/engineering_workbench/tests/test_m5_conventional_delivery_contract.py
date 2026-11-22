from __future__ import annotations

import copy
import hashlib
import json
import unittest

from m5_conventional_delivery_contract import (
    M5DeliveryContractError, validate_conventional_m5_output,
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def fixture(action="TRANSFER"):
    original = list(range(1, 16))
    if action == "TRANSFER":
        post_squad = list(range(1, 15)) + [20]
        outgoing, incoming = 15, 20
        incoming_player = {"fpl_element_id": 20, "position": "MID", "team_id": 20,
                           "purchase_price": 5.0, "current_price": 5.0}
        xi = [1, 2, 3, 4, 5, 6, 7, 20, 9, 10, 11]
        bench = [13, 14, 8]
    else:
        post_squad = original
        outgoing = incoming = incoming_player = None
        xi = list(range(1, 12))
        bench = [13, 14, 15]
    plan = {
        "squad_ids": sorted(post_squad), "starting_xi": xi,
        "bench_order": bench, "reserve_goalkeeper_id": 12,
        "captain_id": 10, "vice_captain_id": 11, "formation": "4-3-3",
    }
    decision_body = {
        "action": action, "transfer_out_id": outgoing, "transfer_in_id": incoming,
        "incoming_player": incoming_player, "transfer_hit_points": 0.0,
        "squad_plan": plan,
    }
    decision = {**decision_body, "decision_sha256": hashlib.sha256(canonical(decision_body)).hexdigest()}
    manager_state = {
        "squad_snapshot": [
            {"fpl_element_id": player_id, "position":
                ("GKP" if player_id in {1, 12} else
                 "DEF" if player_id in {2, 3, 4, 5, 13} else
                 "MID" if player_id in {6, 7, 8, 14} else "FWD"),
             "team_id": player_id, "purchase_price": 5.0, "current_price": 5.0}
            for player_id in original
        ],
        "bank": 0.9, "free_transfers": 1, "hold_plan": {
            "squad_ids": original, "starting_xi": list(range(1, 12)),
            "bench_order": [13, 14, 15], "reserve_goalkeeper_id": 12,
            "captain_id": 10, "vice_captain_id": 11, "formation": "4-3-3",
        },
    }
    candidate = {
        "manager_team_id": 421025, "target_gameweek": 12,
        "deadline_utc": "2026-11-21T11:00:00Z", "as_of_utc": "2026-11-20T10:00:00Z",
        "frozen_decision": copy.deepcopy(decision), "manager_state": manager_state,
    }
    return {
        "run_type": "M3_CONVENTIONAL_PERSONAL_SQUAD_RECOMMENDATION",
        "manager_team_id": 421025, "target_gameweek": 12,
        "decision_as_of_utc": "2026-11-20T10:00:00Z",
        "deadline_utc": "2026-11-21T11:00:00Z",
        "provider_identity": {"name": "FPL Cat", "product": "published xP", "variant": "public-xp"},
        "provider_snapshot_id": "fplcat-gw12-snapshot",
        "recommendation_status": "EXPLORATORY_ONLY",
        "recommendation": {"transfer_recommendation": {
            "action": action, "alternatives_suppressed": True,
        }},
        "frozen_decision": decision, "evaluation_candidate": candidate,
        "release_eligible": False,
        "release_blockers": ["M3 historical decision-evaluation gates incomplete."],
    }


class TestM5ConventionalDeliveryContract(unittest.TestCase):
    def test_accepts_frozen_transfer_plan(self):
        result = validate_conventional_m5_output(fixture("TRANSFER"))
        self.assertEqual(result["status"], "PASS_CONVENTIONAL_M5_DELIVERY_CONTRACT")
        self.assertEqual(result["action"], "TRANSFER")
        self.assertFalse(result["release_eligible"])
        self.assertEqual(result["squad_player_count"], 15)

    def test_accepts_frozen_hold_plan(self):
        result = validate_conventional_m5_output(fixture("HOLD"))
        self.assertEqual(result["action"], "HOLD")


    def test_accepts_sideline_quant_as_separate_conventional_provider(self):
        output = fixture()
        output["provider_identity"] = {
            "name": "Sideline Quant",
            "product": "gameweek_projections",
            "variant": "provider_native_xp",
        }
        result = validate_conventional_m5_output(output)
        self.assertEqual(result["provider"]["name"], "Sideline Quant")

    def test_rejects_unapproved_conventional_forecast_provider(self):
        output = fixture()
        output["provider_identity"]["name"] = "FPLRogue"
        with self.assertRaisesRegex(M5DeliveryContractError, "only the independently run FPL Cat and Sideline Quant"):
            validate_conventional_m5_output(output)

    def test_rejects_transfer_plan_that_keeps_outgoing_player(self):
        output = fixture("TRANSFER")
        output["frozen_decision"]["squad_plan"]["squad_ids"] = list(range(1, 16))
        body = {k: v for k, v in output["frozen_decision"].items() if k != "decision_sha256"}
        output["frozen_decision"]["decision_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
        output["evaluation_candidate"]["frozen_decision"] = copy.deepcopy(output["frozen_decision"])
        with self.assertRaisesRegex(M5DeliveryContractError, "does not match frozen transfer"):
            validate_conventional_m5_output(output)

    def test_rejects_tampered_frozen_decision_hash(self):
        output = fixture()
        output["frozen_decision"]["transfer_in_id"] = 999
        with self.assertRaisesRegex(M5DeliveryContractError, "SHA-256"):
            validate_conventional_m5_output(output)

    def test_rejects_mismatched_embedded_candidate(self):
        output = fixture()
        output["evaluation_candidate"]["frozen_decision"]["action"] = "HOLD"
        with self.assertRaisesRegex(M5DeliveryContractError, "detached"):
            validate_conventional_m5_output(output)

    def test_rejects_post_deadline_decision(self):
        output = fixture()
        output["decision_as_of_utc"] = output["deadline_utc"]
        output["evaluation_candidate"]["as_of_utc"] = output["deadline_utc"]
        with self.assertRaisesRegex(M5DeliveryContractError, "strictly before"):
            validate_conventional_m5_output(output)

    def test_rejects_alternatives_leaking_into_primary_output(self):
        output = fixture()
        output["recommendation"]["transfer_recommendation"]["alternatives"] = []
        with self.assertRaisesRegex(M5DeliveryContractError, "alternatives"):
            validate_conventional_m5_output(output)

    def test_rejects_invalid_xi_bench_coverage(self):
        output = fixture()
        output["frozen_decision"]["squad_plan"]["bench_order"] = [13, 14, 15]
        body = {k: v for k, v in output["frozen_decision"].items() if k != "decision_sha256"}
        output["frozen_decision"]["decision_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
        output["evaluation_candidate"]["frozen_decision"] = copy.deepcopy(output["frozen_decision"])
        with self.assertRaisesRegex(M5DeliveryContractError, "disjoint|cover"):
            validate_conventional_m5_output(output)


if __name__ == "__main__":
    unittest.main()
