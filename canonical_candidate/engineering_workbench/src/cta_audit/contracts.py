from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from typing import Any
from .audit import load_rows, is_null, parse_bool, parse_number


def validate_dataset(rows: list[dict[str, Any]], contract: dict[str, Any], dataset_name: str) -> dict[str, Any]:
    required = contract.get("required_columns", [])
    fields = contract.get("fields", {})
    key_columns = contract.get("key_columns", [])
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    columns = set().union(*(r.keys() for r in rows)) if rows else set()
    missing_columns = sorted(set(required) - columns)
    if missing_columns:
        errors.append({"code": "missing_required_columns", "columns": missing_columns})
    for i, row in enumerate(rows):
        for name, spec in fields.items():
            if name not in row:
                if spec.get("required", name in required):
                    errors.append({"code": "missing_field", "row": i, "field": name})
                continue
            value = row[name]
            if is_null(value):
                if not spec.get("nullable", True):
                    errors.append({"code": "null_not_allowed", "row": i, "field": name})
                continue
            typ = spec.get("type", "string")
            try:
                if typ == "number":
                    x = parse_number(value)
                    if "min" in spec and x < spec["min"]: raise ValueError(f"below minimum {spec['min']}")
                    if "max" in spec and x > spec["max"]: raise ValueError(f"above maximum {spec['max']}")
                elif typ == "integer":
                    x = float(value)
                    if not math.isfinite(x) or not x.is_integer(): raise ValueError("not a finite integer")
                    if "min" in spec and x < spec["min"]: raise ValueError(f"below minimum {spec['min']}")
                    if "max" in spec and x > spec["max"]: raise ValueError(f"above maximum {spec['max']}")
                elif typ == "boolean": parse_bool(value)
                elif typ == "string":
                    if not isinstance(value, str) and not isinstance(value, (int, float)): raise ValueError("not string-like")
                elif typ == "enum":
                    if str(value) not in spec.get("allowed", []): raise ValueError(f"not in allowed values {spec.get('allowed', [])}")
                else: raise ValueError(f"unsupported contract type {typ!r}")
            except (ValueError, TypeError, OverflowError) as exc:
                errors.append({"code": "invalid_value", "row": i, "field": name, "value": value, "detail": str(exc)})
    duplicate_keys: list[dict[str, Any]] = []
    seen: dict[tuple[str, ...], int] = {}
    null_key_rows = []
    for i, row in enumerate(rows):
        vals = tuple(str(row.get(k)).strip() if not is_null(row.get(k)) else "" for k in key_columns)
        if any(v == "" for v in vals):
            null_key_rows.append(i)
        elif vals in seen:
            duplicate_keys.append({"first_row": seen[vals], "duplicate_row": i, "key": vals})
        else:
            seen[vals] = i
    if null_key_rows: errors.append({"code": "null_key_values", "rows": null_key_rows[:50], "count": len(null_key_rows)})
    if duplicate_keys: errors.append({"code": "duplicate_keys", "samples": duplicate_keys[:50], "count": len(duplicate_keys)})
    return {"dataset": dataset_name, "status": "PASS" if not errors else "FAIL", "row_count": len(rows), "columns_found": sorted(columns), "missing_required_columns": missing_columns, "errors": errors, "warnings": warnings}


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate raw CTA datasets against a versioned data contract")
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--contract", required=True, type=Path)
    ap.add_argument("--dataset", default="events")
    ap.add_argument("--out", type=Path, default=Path("reports/preflight"))
    args = ap.parse_args()
    rows = load_rows(args.input)
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    result = validate_dataset(rows, contract, args.dataset)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{args.dataset}_preflight.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    lines = [f"# {args.dataset.title()} data preflight", "", f"**Status: {result['status']}**", "", f"Rows: {result['row_count']}", "", "## Errors"]
    lines += [f"- `{e['code']}`: {e}" for e in result["errors"]] or ["- None"]
    (args.out / f"{args.dataset}_preflight.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"dataset": args.dataset, "status": result["status"], "row_count": len(rows), "errors": len(result["errors"])}))
    return 0 if result["status"] == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
