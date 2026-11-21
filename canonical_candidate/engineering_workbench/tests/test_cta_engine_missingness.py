import json
import subprocess
from pathlib import Path

from cta_engine import build_features

JS_CORE = Path(__file__).resolve().parents[1] / "src" / "js" / "cta_core.mjs"

def _javascript_features(event):
    script = (
        'import { readFileSync } from "node:fs"; '
        'import { pathToFileURL } from "node:url"; '
        f'const {{ buildFeatures }} = await import(pathToFileURL({json.dumps(str(JS_CORE))})); '
        'const event = JSON.parse(readFileSync(0, "utf8")); '
        'const directions = new Map([[JSON.stringify(["match-1", 1, "Home"]), true]]); '
        'const result = buildFeatures([event], directions, null); '
        'process.stdout.write(JSON.stringify({ sequenceRows: result.sequenceRows, players: [...result.players.values()] }));'
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        input=json.dumps(event), capture_output=True, text=True, check=True,
    )
    return json.loads(completed.stdout)



def _shot_event(xg_marker=None):
    event = {
        "_match_id": "match-1",
        "_event_index": 0,
        "period": 1,
        "possession": 1,
        "team": {"name": "Home"},
        "possession_team": {"name": "Home"},
        "type": {"name": "Shot"},
        "player": {"id": "wyscout:10", "name": "Player A"},
        "minute": 1,
        "second": 5,
        "location": [105.0, 40.0],
        "shot": {"outcome": {"name": "Unknown"}},
    }
    if xg_marker is not None:
        event["shot"]["statsbomb_xg"] = xg_marker
    return event


def test_missing_provider_xg_is_not_encoded_as_zero():
    sequences, players = build_features(
        [_shot_event()], {("match-1", 1, "Home"): True}, None
    )

    assert sequences[0]["shot_count"] == 1
    assert sequences[0]["shot_xg_observed_count"] == 0
    assert sequences[0]["shot_xg_reference_only"] == ""
    assert "shot_xg_reference_only" not in players["wyscout:10"]
    assert "shot_xg_observed_count" not in players["wyscout:10"]


def test_observed_xg_is_retained_and_counted():
    sequences, players = build_features(
        [_shot_event(0.17)], {("match-1", 1, "Home"): True}, None
    )

    assert sequences[0]["shot_xg_observed_count"] == 1
    assert sequences[0]["shot_xg_reference_only"] == 0.17
    assert players["wyscout:10"]["shot_xg_reference_only"] == 0.17
    assert players["wyscout:10"]["shot_xg_observed_count"] == 1

def test_javascript_missing_provider_xg_is_not_encoded_as_zero():
    result = _javascript_features(_shot_event())
    sequence = result["sequenceRows"][0]
    player = result["players"][0]
    assert sequence["shot_xg_observed_count"] == 0
    assert sequence["shot_xg_reference_only"] == ""
    assert "shot_xg_reference_only" not in player
    assert "shot_xg_observed_count" not in player


def test_javascript_observed_xg_is_retained_and_counted():
    result = _javascript_features(_shot_event(0.17))
    sequence = result["sequenceRows"][0]
    player = result["players"][0]
    assert sequence["shot_xg_observed_count"] == 1
    assert sequence["shot_xg_reference_only"] == 0.17
    assert player["shot_xg_reference_only"] == 0.17
    assert player["shot_xg_observed_count"] == 1
