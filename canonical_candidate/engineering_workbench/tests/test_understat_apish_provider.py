from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from understat_apish_provider import (
    normalize_player_matches,
    normalize_team_histories,
    _valid_meta,
    _persist_response,
    _log_records,
    _record_params,
    _record_route,
    recover_remote_histories,
    _remaining_credits,
)


class TestApiShUnderstatProvider(unittest.TestCase):
    def test_player_history_normalizes_season_and_required_fields(self):
        rows = normalize_player_matches([{
            "season": "2025-26", "date": "2025-08-15 15:00:00",
            "h_team": "Arsenal", "a_team": "Chelsea", "time": "90", "xG": "0.7",
        }], 76)
        self.assertEqual(rows[0]["season"], "2025")
        self.assertEqual(rows[0]["h_team"], "Arsenal")

    def test_player_history_rejects_missing_identity_fields(self):
        with self.assertRaisesRegex(ValueError, "lacks"):
            normalize_player_matches([{"xG": 0.5}], 76)

    def test_team_histories_normalize_venue_and_require_twenty_teams(self):
        payload = {"raw": {"teams": {
            f"id-{i}": {"title": f"Team {i}", "history": [{
                "date": "2025-08-15 15:00:00", "is_home": True,
                "scored": "1", "missed": "0", "xG": "1.2", "xGA": "0.4",
                "deep": "5", "deep_allowed": "2", "ppda": "9.0",
                "ppda_allowed": "14.0", "pts": "3",
            }]} for i in range(20)
        }}}
        teams = normalize_team_histories(payload, "2025-26")
        self.assertEqual(len(teams), 20)
        self.assertEqual(teams["Team 0"]["history"][0]["h_a"], "h")

    def test_team_histories_reject_partial_team_list(self):
        with self.assertRaisesRegex(ValueError, "lacks required team metrics"):
            normalize_team_histories({"raw": {"teams": {
                "1": {"title": "Arsenal", "history": [{"date": "2025-08-15"}]}
            }}}, "2025-26")


    def test_account_log_parsing_extracts_request_route_and_params(self):
        records = _log_records([{
            "request_id": "abc-123",
            "route": "/understat/v1/player",
            "url": "https://api.api.sh/understat/v1/player?id=181",
        }])
        self.assertEqual(records[0]["request_id"], "abc-123")
        self.assertEqual(_record_route(records[0]), "/understat/v1/player")
        self.assertEqual(_record_params(records[0])["id"], "181")

    def test_account_log_params_accept_json_and_query_string(self):
        self.assertEqual(_record_params({"params": {"season": 2025}})["season"], 2025)
        self.assertEqual(_record_params({"query": "league=EPL&season=2025"})["season"], "2025")

    def test_remote_result_recovery_restores_player_and_full_league_team_histories(self):
        class FakeClient:
            def __init__(self):
                self.last_meta = {}
                self.last_payload = None

            def account_logs(self):
                return [
                    {
                        "request_id": "player-request",
                        "route": "/understat/v1/player",
                        "params": {"id": "181"},
                        "credits_used": 1,
                    },
                    {
                        "request_id": "league-request",
                        "route": "/understat/v1/league",
                        "params": {"league": "EPL", "season": "2024"},
                        "credits_used": 1,
                    },
                ]

            def result(self, request_id):
                if request_id == "player-request":
                    self.last_payload = {"raw": {"matches": [{
                        "season": "2024", "date": "2024-08-15",
                        "h_team": "Arsenal", "a_team": "Wolves",
                    }]}}
                else:
                    self.last_payload = {"raw": {"teams": {
                        f"id-{i}": {"title": f"Team {i}", "history": [{
                            "date": "2024-08-15", "h_a": "h",
                            "scored": "1", "missed": "0", "xG": "1.2", "xGA": "0.4",
                            "deep": "5", "deep_allowed": "2", "ppda": None,
                            "ppda_allowed": None, "pts": "3",
                        }]} for i in range(20)
                    }}}
                self.last_meta = {"request_id": request_id, "credits_used": 0}
                return self.last_payload

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            players = root / "players"
            teams = root / "teams"
            recovered_players, recovered_teams, blocked = recover_remote_histories(
                FakeClient(), [181], ["2024-25"], players, teams
            )
            self.assertEqual(recovered_players, [181])
            self.assertEqual(recovered_teams, ["2024-25"])
            self.assertEqual(blocked, [])
            self.assertTrue(_valid_meta(players / "181.json", kind="player", key="181"))
            self.assertTrue(_valid_meta(teams / "2024-25.json", kind="team", key="2024-25"))

    def test_account_balance_uses_response_header_when_present(self):
        self.assertEqual(_remaining_credits({"free_credits": 100}, "875"), 875)

    def test_account_balance_sums_available_credit_buckets(self):
        self.assertEqual(_remaining_credits({
            "credits": {
                "free_monthly_credits": 800,
                "plan_credits": 100,
                "payg_credits": 50,
            }
        }), 950)

    def test_account_balance_prefers_explicit_total(self):
        self.assertEqual(_remaining_credits({
            "credits_remaining": 725,
            "free_monthly_credits": 800,
        }), 725)

    def test_account_balance_fails_closed_on_unknown_schema(self):
        with self.assertRaisesRegex(RuntimeError, "No provider data requests were made"):
            _remaining_credits({"account": {"status": "active"}})

    def test_provider_cache_requires_matching_provenance_and_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "players" / "76.json"
            client = type("Client", (), {
                "last_meta": {"request_id": "test", "credits_used": 1},
                "last_payload": {"raw": {"matches": [{"date": "2025-08-15"}]}},
            })()
            _persist_response(
                path,
                [{"season": "2025", "date": "2025-08-15", "h_team": "A", "a_team": "B"}],
                kind="player", key="76", client=client,
            )
            self.assertTrue(_valid_meta(path, kind="player", key="76"))
            self.assertFalse(_valid_meta(path, kind="player", key="87"))
            self.assertTrue((path.parent.parent / "responses" / "test.json").is_file())


if __name__ == "__main__":
    unittest.main()
