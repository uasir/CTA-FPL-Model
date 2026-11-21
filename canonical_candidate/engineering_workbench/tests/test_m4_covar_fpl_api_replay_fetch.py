from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from m4_covar_fpl_api_replay_fetch import (
    OfficialFplFetchError,
    acquire_replay,
    fetch_official_json,
    write_private_replay,
)
from test_m4_covar_fpl_api_replay_adapter import api_payloads


class TestM4CovarFplApiReplayFetch(unittest.TestCase):
    def test_acquires_three_payloads_and_returns_anonymized_case(self):
        payloads = list(api_payloads())
        calls = []
        def fake_fetch(url):
            calls.append(url)
            return payloads[len(calls) - 1]
        sleeps = []
        result = acquire_replay(987654, 7, fetch=fake_fetch, sleep=sleeps.append)
        self.assertEqual(len(calls), 3)
        self.assertIn("/entry/987654/event/7/picks/", calls[0])
        self.assertEqual(len(sleeps), 2)
        serialized = json.dumps(result).lower()
        self.assertNotIn("987654", serialized)
        self.assertNotIn("entry_id", serialized)
        self.assertEqual(result["replays"][0]["mode"], "REGULAR_GW")

    def test_rejects_invalid_identifiers_before_fetch(self):
        with self.assertRaises(ValueError):
            acquire_replay(0, 7, fetch=lambda _: self.fail("must not fetch"), sleep=lambda _: None)
        with self.assertRaises(ValueError):
            acquire_replay(123, 0, fetch=lambda _: self.fail("must not fetch"), sleep=lambda _: None)

    def test_restricts_fetch_to_official_fpl_api(self):
        with self.assertRaisesRegex(OfficialFplFetchError, "only official"):
            fetch_official_json("https://example.com/api")

    def test_private_writer_uses_restrictive_permissions_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "replay.json"
            written = write_private_replay({"replays": []}, path)
            self.assertEqual(json.loads(written.read_text()), {"replays": []})
            self.assertEqual(written.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                write_private_replay({"replays": []}, path)


if __name__ == "__main__":
    unittest.main()
