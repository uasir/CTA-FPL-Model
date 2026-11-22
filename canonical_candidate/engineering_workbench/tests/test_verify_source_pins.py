from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from verify_source_pins import verify_source_pins


def _pins(path: Path, *, required: bool = True):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "schema_version": 1,
        "sources": [{
            "source_id": "archive",
            "repository": "example/FPL-archive",
            "commit": "a" * 40,
            "files": [{"path": "season/merged_gw.csv", "sha256": digest, "required": required}],
        }],
    }


def test_source_pin_verifier_accepts_matching_file(tmp_path):
    source = tmp_path / "season" / "merged_gw.csv"
    source.parent.mkdir()
    source.write_text("name,minutes\nPlayer,90\n", encoding="utf-8")

    report = verify_source_pins(_pins(source), tmp_path)

    assert report["verification_status"] == "PASS"
    assert report["sources"][0]["files"][0]["status"] == "VERIFIED"


def test_source_pin_verifier_fails_hash_mismatch(tmp_path):
    source = tmp_path / "season" / "merged_gw.csv"
    source.parent.mkdir()
    source.write_text("changed", encoding="utf-8")
    pins = _pins(source)
    pins["sources"][0]["files"][0]["sha256"] = "0" * 64

    report = verify_source_pins(pins, tmp_path)

    assert report["verification_status"] == "FAIL"
    assert "SHA-256 mismatch" in report["failures"][0]


def test_source_pin_verifier_fails_missing_required_file(tmp_path):
    pins = {
        "schema_version": 1,
        "sources": [{
            "source_id": "archive",
            "repository": "example/FPL-archive",
            "commit": "a" * 40,
            "files": [{"path": "missing.csv", "sha256": "b" * 64, "required": True}],
        }],
    }

    report = verify_source_pins(pins, tmp_path)

    assert report["verification_status"] == "FAIL"
    assert report["sources"][0]["files"][0]["status"] == "MISSING_REQUIRED"


@pytest.mark.parametrize("bad_path", ["../outside.csv", "/absolute.csv", "season/../../outside.csv"])
def test_source_pin_verifier_rejects_path_traversal(tmp_path, bad_path):
    pins = {
        "schema_version": 1,
        "sources": [{
            "source_id": "archive",
            "repository": "example/FPL-archive",
            "commit": "a" * 40,
            "files": [{"path": bad_path, "sha256": "b" * 64, "required": True}],
        }],
    }

    with pytest.raises(ValueError, match="unsafe source path"):
        verify_source_pins(pins, tmp_path)


def test_source_pin_verifier_rejects_short_commit_sha(tmp_path):
    pins = {
        "schema_version": 1,
        "sources": [{
            "source_id": "archive",
            "repository": "example/FPL-archive",
            "commit": "abc123",
            "files": [{"path": "a.csv", "sha256": "b" * 64, "required": True}],
        }],
    }

    with pytest.raises(ValueError, match="40-character commit SHA"):
        verify_source_pins(pins, tmp_path)
