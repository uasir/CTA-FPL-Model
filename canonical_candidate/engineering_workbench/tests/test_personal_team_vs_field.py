from datetime import datetime, timezone, timedelta

import pytest

from compare_fpl_personal_team_to_field import (
    compare_squad_to_field,
    normalize_personal_picks,
    validate_locked_event,
)


def picks_payload(chip=None):
    picks = []
    for position in range(1, 16):
        picks.append({
            "element": position,
            "position": position,
            "is_captain": position == 1,
            "is_vice_captain": position == 2,
        })
    return {
        "entry_history": {"event": 11},
        "active_chip": chip,
        "picks": picks,
    }


def field_rows():
    rows = []
    for player_id in range(1, 17):
        rows.append({
            "gameweek": "11",
            "fpl_element_id": str(player_id),
            "sample_managers": "400",
            "sample_weight": "10000",
            "owned_by_pct": "80" if player_id == 1 else "60",
            "starting_pct": "70",
            "captain_pct": "30" if player_id == 1 else "5",
            "effective_ownership_pct": "110" if player_id == 1 else "65",
            "scoring_exposure_pct": "100" if player_id == 1 else "55",
        })
    return rows


class TestPersonalTeamVsField:
    def test_locked_event_requires_deadline_and_grace_to_pass(self):
        deadline = datetime(2026, 11, 21, 11, 0, tzinfo=timezone.utc)
        bootstrap = {"events": [{"id": 11, "deadline_time": deadline.isoformat()}]}
        with pytest.raises(RuntimeError, match="not eligible"):
            validate_locked_event(
                bootstrap, 11,
                now=deadline + timedelta(seconds=30),
                lock_grace_seconds=60,
            )
        assert validate_locked_event(
            bootstrap, 11,
            now=deadline + timedelta(seconds=61),
            lock_grace_seconds=60,
        )["id"] == 11

    def test_normalizes_locked_squad_and_chip(self):
        picks, chip = normalize_personal_picks(picks_payload("3xc"), 11)
        assert len(picks) == 15
        assert chip == "3xc"
        assert picks[0]["is_captain"] is True

    def test_personal_exposure_is_compared_to_existing_field_eo(self):
        picks, chip = normalize_personal_picks(picks_payload(), 11)
        output, report = compare_squad_to_field(picks, chip, field_rows(), 11)
        by_id = {row["fpl_element_id"]: row for row in output}
        assert by_id["1"]["personal_effective_ownership_pct"] == 200.0
        assert by_id["1"]["field_effective_ownership_pct"] == 110.0
        assert by_id["1"]["effective_ownership_delta_pct"] == 90.0
        assert by_id["12"]["personal_effective_ownership_pct"] == 100.0
        assert by_id["12"]["personal_scoring_exposure_pct"] == 0.0
        assert by_id["16"]["personal_effective_ownership_pct"] == 0.0
        assert report["status"] == "PASS_PERSONAL_SQUAD_VS_EXISTING_FIELD_EO"
        assert report["co_var"] == "NOT_COMPUTED_HERE; the existing CoVar portfolio layer remains separate."
        assert report["largest_negative_differentials"][0]["in_personal_squad"] is False
        assert report["most_underowned_field_players_not_owned"][0]["fpl_element_id"] == "16"

    def test_triple_captain_and_bench_boost_change_personal_exposure(self):
        picks, chip = normalize_personal_picks(picks_payload("3xc"), 11)
        triple_rows, _ = compare_squad_to_field(picks, chip, field_rows(), 11)
        triple = next(row for row in triple_rows if row["fpl_element_id"] == "1")
        assert triple["personal_effective_ownership_pct"] == 300.0
        assert triple["personal_scoring_exposure_pct"] == 300.0

        picks, chip = normalize_personal_picks(picks_payload("bboost"), 11)
        boost_rows, _ = compare_squad_to_field(picks, chip, field_rows(), 11)
        bench = next(row for row in boost_rows if row["fpl_element_id"] == "12")
        assert bench["personal_effective_ownership_pct"] == 100.0
        assert bench["personal_scoring_exposure_pct"] == 100.0

    def test_rejects_wrong_gameweek_and_incomplete_field_coverage(self):
        with pytest.raises(ValueError, match="expected GW11"):
            normalize_personal_picks(
                {"entry_history": {"event": 10}, "picks": []}, 11
            )
        picks, chip = normalize_personal_picks(picks_payload(), 11)
        with pytest.raises(ValueError, match="missing owned player IDs"):
            compare_squad_to_field(picks, chip, field_rows()[1:], 11)
