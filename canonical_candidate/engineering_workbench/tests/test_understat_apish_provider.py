from pathlib import Path
import csv
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from understat_apish_provider import (
    ApiShUnderstatClient, normalize_player_matches, normalize_one_team, normalize_team_histories,
    _valid_meta, _persist_response, _log_records, _record_params, _record_route,
    recover_remote_histories, _remaining_credits, _season_team_names,
    _team_cache_filename, _write_complete_team_season, download_missing_histories,
)


def team_response(name="Arsenal"):
    return {"raw": {"title": name, "history": [{
        "date": "2025-08-15 15:00:00", "is_home": True,
        "scored": "1", "missed": "0", "xG": "1.2", "xGA": "0.4",
        "deep": "5", "deep_allowed": "2", "ppda": None,
        "ppda_allowed": None, "pts": "3",
    }]}}


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

    def test_client_uses_individual_team_endpoint_with_team_and_season_params(self):
        class FakeResponse:
            headers = {"x-request-id": "team-req", "x-credits-used": "1"}
            def raise_for_status(self):
                pass
            def json(self):
                return team_response("Arsenal")
        class FakeSession:
            def __init__(self):
                self.headers = {}
                self.calls = []
            def get(self, url, params, timeout):
                self.calls.append((url, params, timeout))
                return FakeResponse()
        session = FakeSession()
        client = ApiShUnderstatClient(api_key="test-key", session=session)
        result = client.team_history("Arsenal", "2024-25")
        self.assertEqual(result["title"], "Arsenal")
        self.assertTrue(session.calls[0][0].endswith("/understat/v1/team"))
        self.assertEqual(session.calls[0][1], {"team": "Arsenal", "season": 2024, "raw": "true"})

    def test_one_team_history_normalizes_venue_and_preserves_null_metrics(self):
        team = normalize_one_team(team_response(), "Arsenal", "2025-26")
        self.assertEqual(team["title"], "Arsenal")
        self.assertEqual(team["history"][0]["h_a"], "h")
        self.assertIsNone(team["history"][0]["ppda"])

    def test_one_team_history_rejects_wrong_team_identity(self):
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            normalize_one_team(team_response("Chelsea"), "Arsenal", "2025-26")

    def test_one_team_history_rejects_missing_metrics(self):
        with self.assertRaisesRegex(ValueError, "lacks required team metrics"):
            normalize_one_team({"raw": {"title": "Arsenal", "history": [{"date": "2025-08-15"}]}}, "Arsenal", "2025-26")

    def test_complete_team_season_requires_twenty_distinct_team_histories(self):
        teams = {f"Team {i}": {"title": f"Team {i}", "history": [{"date": "2025-08-15"}]} for i in range(20)}
        self.assertEqual(len(normalize_team_histories(teams, "2025-26")), 20)
        with self.assertRaisesRegex(ValueError, "expected 20"):
            normalize_team_histories(dict(list(teams.items())[:19]), "2025-26")

    def test_season_team_names_use_pinned_teams_csv_and_alias_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vaastav" / "2025-26"
            path.mkdir(parents=True)
            names = ["Arsenal", "Man City", "Man Utd", "Newcastle", "Nott'm Forest",
                     "Sheffield Utd", "Spurs", "West Brom", "Wolves", "Chelsea",
                     "Liverpool", "Everton", "Fulham", "Brentford", "Brighton",
                     "Burnley", "Leeds", "Sunderland", "Bournemouth", "Crystal Palace"]
            with (path / "teams.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["id", "name"])
                writer.writeheader()
                for i, name in enumerate(names, 1):
                    writer.writerow({"id": i, "name": name})
            mapped = _season_team_names(Path(directory), "2025-26")
            self.assertIn("Manchester City", mapped)
            self.assertIn("Nottingham Forest", mapped)
            self.assertEqual(len(mapped), 20)

    def test_account_log_parsing_extracts_request_route_and_params(self):
        records = _log_records([{
            "request_id": "abc-123", "route": "/understat/v1/player",
            "url": "https://api.api.sh/understat/v1/player?id=181",
        }])
        self.assertEqual(records[0]["request_id"], "abc-123")
        self.assertEqual(_record_route(records[0]), "/understat/v1/player")
        self.assertEqual(_record_params(records[0])["id"], "181")

    def test_account_log_params_accept_json_and_query_string(self):
        self.assertEqual(_record_params({"params": {"season": 2025}})["season"], 2025)
        self.assertEqual(_record_params({"query": "team=Arsenal&season=2025"})["season"], "2025")

    def test_remote_result_recovery_restores_player_and_individual_team(self):
        class FakeClient:
            def __init__(self):
                self.last_meta = {}
                self.last_payload = None
            def account_logs(self):
                return [
                    {"request_id": "player-request", "route": "/understat/v1/player",
                     "params": {"id": "181"}, "credits_used": 1},
                    {"request_id": "team-request", "route": "/understat/v1/team",
                     "params": {"team": "Arsenal", "season": "2024"}, "credits_used": 1},
                ]
            def result(self, request_id):
                self.last_payload = (
                    {"raw": {"matches": [{"season": "2024", "date": "2024-08-15",
                                          "h_team": "Arsenal", "a_team": "Wolves"}]}}
                    if request_id == "player-request" else team_response("Arsenal")
                )
                self.last_meta = {"request_id": request_id, "credits_used": 0}
                return self.last_payload

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            players, teams = root / "players", root / "teams"
            got_players, got_teams, blocked = recover_remote_histories(
                FakeClient(), [181], [("2024-25", "Arsenal")], players, teams
            )
            self.assertEqual(got_players, [181])
            self.assertEqual(got_teams, [("2024-25", "Arsenal")])
            self.assertEqual(blocked, [])
            self.assertTrue(_valid_meta(players / "181.json", kind="player", key="181"))
            team_path = teams / _team_cache_filename("2024-25", "Arsenal")
            self.assertTrue(_valid_meta(team_path, kind="team", key="2024-25|Arsenal"))

    def test_complete_team_season_aggregate_is_written_only_after_all_twenty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache" / "teams"
            output = root / "raw" / "understat" / "teams"
            names = [f"Team {i}" for i in range(20)]
            for name in names[:19]:
                path = cache / _team_cache_filename("2025-26", name)
                fake = type("Client", (), {
                    "last_meta": {"request_id": f"req-{name}", "credits_used": 1},
                    "last_payload": team_response(name),
                })()
                _persist_response(path, {"title": name, "history": normalize_one_team(team_response(name), name, "2025-26")["history"]},
                                  kind="team", key=f"2025-26|{name}", client=fake)
            self.assertFalse(_write_complete_team_season(cache, output, "2025-26", names))
            name = names[-1]
            path = cache / _team_cache_filename("2025-26", name)
            fake = type("Client", (), {
                "last_meta": {"request_id": f"req-{name}", "credits_used": 1},
                "last_payload": team_response(name),
            })()
            _persist_response(path, {"title": name, "history": normalize_one_team(team_response(name), name, "2025-26")["history"]},
                              kind="team", key=f"2025-26|{name}", client=fake)
            self.assertTrue(_write_complete_team_season(cache, output, "2025-26", names))
            self.assertEqual(len(__import__("json").loads((output / "2025-26.json").read_text())), 20)

    def test_downloader_restores_nineteen_team_checkpoints_and_requests_only_the_missing_team(self):
        class FakeClient:
            def __init__(self):
                self.last_meta, self.last_payload = {}, None
                self.requested = []
            def account(self):
                return {}, 1
            def account_logs(self):
                return []
            def team_history(self, team, season):
                self.requested.append((season, team))
                self.last_payload = team_response(team)
                self.last_meta = {"request_id": "last-team-request", "credits_used": 1}
                return normalize_one_team(self.last_payload, team, season)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw"
            teams_dir = raw / "vaastav" / "2025-26"
            teams_dir.mkdir(parents=True)
            names = [f"Team {i}" for i in range(20)]
            with (teams_dir / "teams.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["id", "name"])
                writer.writeheader()
                for i, name in enumerate(names, 1):
                    writer.writerow({"id": i, "name": name})
            cache = root / "shared" / "teams"
            for name in names[:-1]:
                path = cache / _team_cache_filename("2025-26", name)
                normalized = normalize_one_team(team_response(name), name, "2025-26")
                fake = type("PersistClient", (), {
                    "last_meta": {"request_id": f"cached-{name}", "credits_used": 1},
                    "last_payload": team_response(name),
                })()
                _persist_response(path, normalized, kind="team",
                                  key=f"2025-26|{name}", client=fake)
            fake_client = FakeClient()
            with patch("understat_apish_provider.ApiShUnderstatClient", return_value=fake_client):
                report = download_missing_histories(
                    raw, [], ["2025-26"], cache_root=root / "shared", probe_only=False
                )
            self.assertEqual(fake_client.requested, [("2025-26", names[-1])])
            self.assertEqual(report["fetched_team_seasons"], ["2025-26"])
            self.assertEqual(report["unresolved_team_seasons"], [])
            self.assertEqual(report["unresolved_team_member_count"], 0)
            aggregate = raw / "understat" / "teams" / "2025-26.json"
            self.assertEqual(len(__import__("json").loads(aggregate.read_text())), 20)

    def test_account_balance_uses_response_header_when_present(self):
        self.assertEqual(_remaining_credits({"free_credits": 100}, "875"), 875)

    def test_account_balance_sums_available_credit_buckets(self):
        self.assertEqual(_remaining_credits({"credits": {
            "free_monthly_credits": 800, "plan_credits": 100, "payg_credits": 50,
        }}), 950)

    def test_account_balance_prefers_explicit_total(self):
        self.assertEqual(_remaining_credits({"credits_remaining": 725, "free_monthly_credits": 800}), 725)

    def test_account_balance_fails_closed_on_unknown_schema(self):
        with self.assertRaisesRegex(RuntimeError, "No provider data requests were made"):
            _remaining_credits({"account": {"status": "active"}})

    def test_provider_cache_rejects_corrupt_exact_raw_response(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache" / "players" / "76.json"
            client = type("Client", (), {
                "last_meta": {"request_id": "raw-check", "credits_used": 1},
                "last_payload": {"raw": {"matches": [{"date": "2025-08-15"}]}},
            })()
            _persist_response(path, [{
                "season": "2025", "date": "2025-08-15", "h_team": "A", "a_team": "B"
            }], kind="player", key="76", client=client)
            self.assertTrue(_valid_meta(path, kind="player", key="76"))
            raw_path = path.parent.parent / "responses" / "raw-check.json"
            raw_path.write_text('{"tampered": true}', encoding="utf-8")
            self.assertFalse(_valid_meta(path, kind="player", key="76"))

    def test_dastan_source_copy_validates_without_duplicate_response_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache_path = root / "cache" / "players" / "76.json"
            client = type("Client", (), {
                "last_meta": {"request_id": "source-copy", "credits_used": 1},
                "last_payload": {"raw": {"matches": [{"date": "2025-08-15"}]}},
            })()
            _persist_response(cache_path, [{
                "season": "2025", "date": "2025-08-15", "h_team": "A", "a_team": "B"
            }], kind="player", key="76", client=client)
            source_copy = root / "raw" / "understat" / "players" / "76.json"
            source_copy.parent.mkdir(parents=True)
            source_copy.write_bytes(cache_path.read_bytes())
            source_copy.with_suffix(".meta").write_bytes(cache_path.with_suffix(".meta").read_bytes())
            self.assertTrue(_valid_meta(source_copy, kind="player", key="76"))

    def test_provider_cache_requires_matching_provenance_and_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "players" / "76.json"
            client = type("Client", (), {
                "last_meta": {"request_id": "test", "credits_used": 1},
                "last_payload": {"raw": {"matches": [{"date": "2025-08-15"}]}},
            })()
            _persist_response(path, [{
                "season": "2025", "date": "2025-08-15", "h_team": "A", "a_team": "B"
            }], kind="player", key="76", client=client)
            self.assertTrue(_valid_meta(path, kind="player", key="76"))
            self.assertFalse(_valid_meta(path, kind="player", key="87"))
            self.assertTrue((path.parent.parent / "responses" / "test.json").is_file())


if __name__ == "__main__":
    unittest.main()
