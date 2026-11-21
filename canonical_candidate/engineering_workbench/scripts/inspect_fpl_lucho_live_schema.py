#!/usr/bin/env python3
"""One-shot, schema-only live FPL Lucho CSV inspection.

Raw CSV bytes are held only in process memory. No row values, player names,
raw payload, or downloadable artifact are emitted or persisted.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from urllib.request import Request, urlopen

CSV_URL = "https://fpllucho.pythonanywhere.com/export/predictions.csv"


def main() -> int:
    request = Request(
        CSV_URL,
        headers={"User-Agent": "CTA-FPL-Model/1.0 (private schema-only benchmark inspection)"},
    )
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"CSV endpoint returned HTTP {response.status}")
        raw = response.read()
        content_type = response.headers.get("Content-Type", "")

    text = raw.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    headers = next(reader)
    rows = list(reader)
    normalized = [h.strip() for h in headers]
    if not headers or any(not h for h in normalized):
        raise RuntimeError("CSV has empty headers")
    if len(set(normalized)) != len(normalized):
        raise RuntimeError("CSV has duplicate headers after whitespace normalization")
    if any(len(row) != len(headers) for row in rows):
        raise RuntimeError("CSV contains inconsistent row widths")
    if not rows:
        raise RuntimeError("CSV contains no forecast rows")

    columns = []
    for index, header in enumerate(headers):
        kinds = Counter()
        for row in rows:
            token = row[index].strip()
            if not token:
                kind = "empty"
            else:
                try:
                    float(token)
                    kind = "numeric_lexeme"
                except ValueError:
                    kind = "text"
            kinds[kind] += 1
        gw_tokens = [int(x) for x in re.findall(r"(?i)GW\s*0*(\d+)", header)]
        columns.append({
            "index": index,
            "header": header,
            "gameweek_tokens": gw_tokens,
            "lexical_type_counts": dict(sorted(kinds.items())),
        })

    print(json.dumps({
        "provider": "FPL Lucho",
        "product": "forecast_csv",
        "variant": "served_odds_anchored_xp",
        "content_type": content_type,
        "csv_bytes": len(raw),
        "csv_sha256": hashlib.sha256(raw).hexdigest(),
        "row_count": len(rows),
        "column_count": len(headers),
        "columns": columns,
        "normalization_status": "SCHEMA_ONLY_SEMANTIC_MAPPING_NOT_APPROVED",
        "raw_values_emitted": False,
        "raw_payload_persisted_or_uploaded": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
