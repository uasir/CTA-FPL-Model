import pytest

from reconcile_official_fpl_manager_batch import parse_gameweeks, reconcile_batch


def _result(gw, transfer_cost=0, autosubs=None):
    return {
        "reconciliation": {
            "status": "RECONCILED",
            "official_transfer_cost": transfer_cost,
            "automatic_substitutions": autosubs or [],
        },
        "target_gameweek": gw,
        "historical_evidence_admitted": False,
    }


def test_parse_gameweeks_preserves_order_and_rejects_bad_input():
    assert parse_gameweeks("1, 3,10") == [1, 3, 10]
    with pytest.raises(ValueError, match="duplicates"):
        parse_gameweeks("1,1")
    with pytest.raises(ValueError, match="positive"):
        parse_gameweeks("1,0")
    with pytest.raises(ValueError, match="positive integers"):
        parse_gameweeks("1,x")


def test_batch_reports_autosub_hits_and_explicit_exclusions():
    def capture(_manager, gw):
        if gw == 3:
            raise RuntimeError("chip gameweek")
        return _result(
            gw,
            transfer_cost=8 if gw == 2 else 0,
            autosubs=[{"player_out_id": 7, "player_in_id": 12}] if gw == 1 else [],
        )

    result = reconcile_batch(421025, [1, 2, 3], capture)
    assert result["reconciled_gameweeks"] == [1, 2]
    assert result["excluded_gameweeks"] == [3]
    assert result["gameweeks_with_automatic_substitutions"] == [1]
    assert result["gameweeks_with_transfer_hits"] == [2]
    assert result["historical_evidence_admitted"] is False
    assert result["results"][2]["error"] == "chip gameweek"


def test_batch_rejects_duplicate_or_empty_gameweek_lists():
    with pytest.raises(ValueError, match="unique positive"):
        reconcile_batch(421025, [1, 1], lambda *_: {})
    with pytest.raises(ValueError, match="unique positive"):
        reconcile_batch(421025, [], lambda *_: {})


def test_batch_retains_diagnostic_record_for_failed_real_gameweek():
    diagnostic = {"target_gameweek": 5, "source_archives": [{"raw_sha256": "abc"}]}
    def capture(_manager, _gw):
        exc = RuntimeError("autosub mismatch")
        exc.diagnostic_record = diagnostic
        raise exc

    result = reconcile_batch(421025, [5], capture)
    assert result["excluded_count"] == 1
    assert result["results"][0]["diagnostic_record"] == diagnostic
