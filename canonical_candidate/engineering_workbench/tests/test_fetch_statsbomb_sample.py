import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.fetch_statsbomb_sample import (
    IntegrityError,
    download_sample,
    fetch_verified,
    git_blob_sha1,
    verify_payload,
)


def blob_sha(payload: bytes) -> str:
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()


class FetchStatsBombSampleTests(unittest.TestCase):
    def test_git_blob_hash_matches_git_object_format(self):
        payload = b"hello CTA-FPL"
        self.assertEqual(git_blob_sha1(payload), blob_sha(payload))
        verify_payload(payload, blob_sha(payload), len(payload))

    def test_size_or_sha_mismatch_fails(self):
        payload = b"payload"
        with self.assertRaises(IntegrityError):
            verify_payload(payload, "0" * 40, len(payload))
        with self.assertRaises(IntegrityError):
            verify_payload(payload, blob_sha(payload), len(payload) + 1)

    def test_fetch_verified_downloads_and_skips_verified_existing_file(self):
        payload = b"immutable bytes"
        sha = blob_sha(payload)
        calls = []

        def fake_urlopen(request, timeout):
            calls.append((request.full_url, timeout))
            return io.BytesIO(payload)

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "events" / "123.json"
            status = fetch_verified(
                "https://example.test/123.json", dest, sha, len(payload),
                opener=fake_urlopen, sleep=lambda _: None,
            )
            self.assertEqual(status, "downloaded_verified")
            self.assertEqual(dest.read_bytes(), payload)
            status2 = fetch_verified(
                "https://example.test/123.json", dest, sha, len(payload),
                opener=lambda *_args, **_kwargs: self.fail("should not download"),
            )
            self.assertEqual(status2, "existing_verified")
        self.assertEqual(len(calls), 1)

    def test_download_sample_records_missing_360_without_empty_placeholder(self):
        event = b"event-json"
        frame = b"frame-json"
        manifest = {
            "source": {"repository": "hudl/open-data", "commit_sha": "a" * 40},
            "matches": [
                {
                    "match_id": 1,
                    "events_blob_sha": blob_sha(event),
                    "events_size_bytes": len(event),
                    "has_360": True,
                    "three_sixty_blob_sha": blob_sha(frame),
                    "three_sixty_size_bytes": len(frame),
                },
                {
                    "match_id": 2,
                    "events_blob_sha": blob_sha(event),
                    "events_size_bytes": len(event),
                    "has_360": False,
                    "three_sixty_blob_sha": None,
                    "three_sixty_size_bytes": None,
                },
            ],
        }
        payloads = {
            "/events/1.json": event,
            "/three-sixty/1.json": frame,
            "/events/2.json": event,
        }
        requested = []

        def fake_urlopen(request, timeout):
            requested.append(request.full_url)
            for suffix, payload in payloads.items():
                if request.full_url.endswith(suffix):
                    return io.BytesIO(payload)
            raise AssertionError(f"Unexpected URL: {request.full_url}")

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            report = download_sample(
                manifest, out, opener=fake_urlopen, sleep=lambda _: None
            )
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["events_verified"], 2)
            self.assertEqual(report["three_sixty_verified"], 1)
            self.assertEqual(report["three_sixty_unavailable"], 1)
            self.assertFalse((out / "three-sixty" / "2.json").exists())
            saved = json.loads((out / "download_report.json").read_text())
            self.assertEqual(saved["status"], "passed")
        self.assertEqual(len(requested), 3)


    def test_download_sample_excludes_present_but_invalid_360_source(self):
        event = b"event-json"
        invalid_frame = b"invalid-frame-json"
        manifest = {
            "source": {"repository": "hudl/open-data", "commit_sha": "c" * 40},
            "matches": [{
                "match_id": 3837706,
                "events_blob_sha": blob_sha(event),
                "events_size_bytes": len(event),
                "has_360": False,
                "has_360_source": True,
                "three_sixty_blob_sha": blob_sha(invalid_frame),
                "three_sixty_size_bytes": len(invalid_frame),
                "three_sixty_exclusion_reason": "Frame UUIDs do not join the event IDs.",
            }],
        }
        requested = []
        def fake_urlopen(request, timeout):
            requested.append(request.full_url)
            if request.full_url.endswith("/events/3837706.json"):
                return io.BytesIO(event)
            raise AssertionError("Excluded 360 source must not be downloaded")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            report = download_sample(manifest, out, opener=fake_urlopen, sleep=lambda _: None)
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["three_sixty_verified"], 0)
            self.assertEqual(report["three_sixty_excluded"], 1)
            self.assertEqual(report["three_sixty_unavailable"], 0)
            self.assertFalse((out / "three-sixty" / "3837706.json").exists())
            self.assertEqual(len(report["excluded_sources"]), 1)
        self.assertEqual(len(requested), 1)

    def test_invalid_manifest_rejects_duplicate_match_ids(self):
        manifest = {
            "source": {"repository": "hudl/open-data", "commit_sha": "b" * 40},
            "matches": [
                {"match_id": 7, "events_blob_sha": "c" * 40,
                 "events_size_bytes": 1, "has_360": False,
                 "three_sixty_blob_sha": None},
                {"match_id": 7, "events_blob_sha": "d" * 40,
                 "events_size_bytes": 1, "has_360": False,
                 "three_sixty_blob_sha": None},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                download_sample(manifest, Path(tmp))


if __name__ == "__main__":
    unittest.main()