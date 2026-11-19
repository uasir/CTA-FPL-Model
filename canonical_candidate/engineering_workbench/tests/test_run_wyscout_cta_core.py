from run_wyscout_cta_core import run


def test_wyscout_events_execute_through_canonical_cta_core(tmp_path):
    events = [
        {
            "id": "1", "_match_id": "match-1", "_event_index": 0,
            "type": {"name": "Pass"}, "player": {"id": "wyscout:1", "name": "A"},
            "team": {"name": "Home"}, "possession_team": {"name": "Home"},
            "possession": 1, "period": 1, "minute": 1, "second": 0,
            "location": [12.0, 40.0],
            "pass": {"end_location": [90.0, 40.0]},
        },
        {
            "id": "2", "_match_id": "match-1", "_event_index": 1,
            "type": {"name": "Shot"}, "player": {"id": "wyscout:2", "name": "B"},
            "team": {"name": "Home"}, "possession_team": {"name": "Home"},
            "possession": 1, "period": 1, "minute": 1, "second": 5,
            "location": [108.0, 40.0], "shot": {"outcome": {"name": "Goal"}},
        },
    ]
    source = tmp_path / "events.json"
    source.write_text(__import__("json").dumps(events))
    report = run(source, tmp_path / "out")
    assert report["status"] == "PASS_CORE_ENGINE_EXECUTED_RESEARCH_ONLY"
    assert report["events_loaded"] == 2
    assert report["unique_matches"] == 1
    assert report["inferred_possession_segments"] == 1
    assert report["sequence_feature_rows"] == 1
    assert report["provider_player_feature_rows"] == 2
    assert report["predictive_validation"] == "NOT_EVALUATED"
    assert (tmp_path / "out" / "wyscout_cta_core_execution_report.json").exists()
