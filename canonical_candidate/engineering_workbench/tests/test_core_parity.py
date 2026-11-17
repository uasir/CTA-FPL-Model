from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

WORKBENCH = Path(__file__).resolve().parents[1]
CANDIDATE = WORKBENCH.parent
FIXTURE = WORKBENCH / "tests" / "fixtures" / "3895320"
CONTRACT = WORKBENCH / "config" / "cta_core_parity_contract.json"
JS_RUNNER = WORKBENCH / "src" / "js" / "run_pilot_parity.mjs"

sys.path.insert(0, str(WORKBENCH / "src"))
sys.path.insert(0, str(CANDIDATE / "src"))

from cta_audit.audit import audit, load_registry, load_rows  # noqa: E402
import cta_engine  # noqa: E402


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


class CoreParityTests(unittest.TestCase):
    def test_contract_keeps_possession_player_and_grid_grains_separate(self):
        sequence = load_registry(CONTRACT, "sequences")
        player = load_registry(CONTRACT, "players")
        grid = load_registry(CONTRACT, "xt_grid")
        self.assertEqual(sequence["key_columns"], ["match_id", "period", "possession_id", "team"])
        self.assertEqual(player["key_columns"], ["statsbomb_player_id"])
        self.assertEqual(grid["key_columns"], ["x_cell", "y_cell"])
        self.assertIn("minutes and all per-90 columns", " ".join(
            item["feature"] for item in json.loads(CONTRACT.read_text())["parity_tables"]["players"]["unsupported_features"]
        ))

    def test_null_remains_distinct_from_zero_for_sparse_counter_features(self):
        registry = load_registry(CONTRACT, "players")
        row = {"statsbomb_player_id": "123"}
        row.update({name: None for name in registry["features"]})
        same_null = dict(row)
        passing = audit([row], [same_null], registry)
        self.assertEqual(passing["summary"]["status"], "PASS")

        zero_value = dict(same_null)
        zero_value["shots"] = 0
        failing = audit([row], [zero_value], registry)
        self.assertEqual(failing["summary"]["status"], "FAIL")
        self.assertEqual(failing["features"]["shots"]["null_mismatches"], 1)

    def test_real_pilot_fixture_matches_python_and_javascript_at_each_grain(self):
        fixture_manifest = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
        event_source = CANDIDATE / "data" / "events" / "3895320.json"
        frame_source = CANDIDATE / "data" / "three-sixty" / "3895320.json"
        self.assertEqual(
            git_blob_sha1(event_source),
            fixture_manifest["source_git_blob_sha1"]["events"],
        )
        self.assertEqual(
            git_blob_sha1(frame_source),
            fixture_manifest["source_git_blob_sha1"]["three_sixty"],
        )

        with tempfile.TemporaryDirectory(prefix="cta-core-parity-fixture-") as temp:
            root = Path(temp)
            python_out = root / "python"
            js_out = root / "javascript"
            args = Namespace(
                events_dir=str(FIXTURE / "events"),
                three_sixty_dir=str(FIXTURE / "three-sixty"),
                direction_map=str(CANDIDATE / "data" / "direction_map.csv"),
                player_map=str(CANDIDATE / "data" / "player_id_map.csv"),
                minutes=str(CANDIDATE / "data" / "player_minutes.csv"),
                output_dir=str(python_out),
            )
            with contextlib.redirect_stdout(io.StringIO()):
                cta_engine.run(args)

            subprocess.run(
                [
                    "node",
                    str(JS_RUNNER),
                    "--events",
                    str(FIXTURE / "events" / "3895320.json"),
                    "--three-sixty",
                    str(FIXTURE / "three-sixty" / "3895320.json"),
                    "--direction-map",
                    str(CANDIDATE / "data" / "direction_map.csv"),
                    "--out",
                    str(js_out),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            pairs = [
                ("sequences", python_out / "sequences.csv", js_out / "sequences.json"),
                ("players", python_out / "player_features.csv", js_out / "players.json"),
                ("xt_grid", python_out / "xt_grid.csv", js_out / "xt_grid.json"),
            ]
            for table, python_path, javascript_path in pairs:
                with self.subTest(table=table):
                    result = audit(
                        load_rows(python_path),
                        load_rows(javascript_path),
                        load_registry(CONTRACT, table),
                    )
                    self.assertEqual(
                        result["summary"]["status"],
                        "PASS",
                        json.dumps(result["summary"], indent=2),
                    )
                    self.assertEqual(result["summary"]["missing_in_javascript"], 0)
                    self.assertEqual(result["summary"]["extra_in_javascript"], 0)
                    self.assertEqual(
                        result["summary"]["python_rows"],
                        result["summary"]["javascript_rows"],
                    )


if __name__ == "__main__":
    unittest.main()
