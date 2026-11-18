import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_openplay_epl_event_data import _frame_summary, _plain


def test_frame_summary_contains_row_count_and_schema_only():
    frame = pd.DataFrame({"player_id": [1, 2], "xg": [0.2, 0.4]})
    result = _frame_summary(frame)
    assert result == {"rows": 2, "columns": ["player_id", "xg"]}


def test_plain_converts_numpy_and_missing_values_for_json():
    frame = pd.Series([1, None], dtype="Int64")
    assert _plain(frame.iloc[0]) == 1
    assert _plain(frame.iloc[1]) is None
