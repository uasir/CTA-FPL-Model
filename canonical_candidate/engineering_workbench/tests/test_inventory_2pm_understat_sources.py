from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from inventory_2pm_understat_sources import (
    build_inventory,
    latest_player_paths,
    team_paths,
)


class UnderstatInventoryTests(unittest.TestCase):
    def test_latest_player_path_matches_pinned_loader_selection(self):
        paths = [
            "data/2021-22/understat/player_one_10.csv",
            "data/2023-24/understat/player_one_10.csv",
            "data/2022-23/understat/player_two_20.csv",
        ]
        self.assertEqual(
            latest_player_paths(paths, {10, 20, 30}),
            {
                10: "data/2023-24/understat/player_one_10.csv",
                20: "data/2022-23/understat/player_two_20.csv",
            },
        )

    def test_team_path_excludes_aggregate_player_file(self):
        paths = [
            "data/2024-25/understat/understat_Arsenal.csv",
            "data/2024-25/understat/understat_player.csv",
            "data/2023-24/understat/understat_Arsenal.csv",
        ]
        self.assertEqual(
            team_paths(paths, "2024-25"),
            ["data/2024-25/understat/understat_Arsenal.csv"],
        )

    def test_inventory_distinguishes_pinned_and_live_fallback_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dastan = root / "dastan"
            raw = root / "raw"
            (dastan / "data" / "mappings").mkdir(parents=True)
            (raw / "vaastav" / "understat" / "players").mkdir(parents=True)
            (raw / "understat" / "players").mkdir(parents=True)
            (raw / "vaastav" / "understat" / "teams" / "2024-25").mkdir(parents=True)
            (raw / "vaastav").mkdir(exist_ok=True)
            (dastan / "data" / "source_pins.json").write_text(json.dumps({
                "vaastav": {"repository": "vaastav/Fantasy-Premier-League", "commit": "pin"}
            }))
            (dastan / "data" / "mappings" / "fpl_understat_training_snapshot.csv").write_text(
                "understat_id\n10\n20\n"
            )
            (raw / "vaastav" / "tree.json").write_text(json.dumps({
                "tree": [
                    {"type": "blob", "path": "data/2023-24/understat/player_10.csv"},
                    {"type": "blob", "path": "data/2024-25/understat/understat_Arsenal.csv"},
                ]
            }))
            pinned = raw / "vaastav" / "understat" / "players" / "10.csv"
            pinned.write_text("date,xG\n2024-01-01,0.2\n")
            fallback = raw / "understat" / "players" / "20.json"
            fallback.write_text('[{"date":"2024-01-01","xG":0.1}]')
            team = raw / "vaastav" / "understat" / "teams" / "2024-25" / "understat_Arsenal.csv"
            team.write_text("date,xG\n2024-01-01,1.2\n")
            (raw / "downloads.json").write_text(json.dumps({
                "created_at": "2026-11-27T00:00:00Z",
                "files": {}
            }))
            report = build_inventory(raw, dastan, ["2024-25"])
            self.assertEqual(
                {row["understat_id"]: row["source_kind"] for row in report["players"]},
                {10: "pinned_player_csv", 20: "live_player_fallback"},
            )
            self.assertEqual(report["teams"][0]["source_kind"], "pinned_team_csv")
            self.assertFalse(report["historical_publication_vintage_claim"])
            self.assertEqual(report["admission_decision"], "NO_FEATURES_ADMITTED")


if __name__ == "__main__":
    unittest.main()
