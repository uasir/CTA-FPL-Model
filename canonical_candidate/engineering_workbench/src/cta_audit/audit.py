from __future__ import annotations
import argparse
import csv
import json
import math
import hashlib
import statistics
from pathlib import Path
from typing import Any


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        with path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("rows", [])
        if not isinstance(data, list):
            raise ValueError(f"JSON input must be a list or an object containing 'rows': {path}")
        return data
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def is_null(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip().lower() in {"", "null", "none", "nan"})


def norm_key(v: Any) -> str:
    return "<NULL>" if is_null(v) else str(v).strip()


def parse_bool(v: Any) -> bool:
    if isinstance(v, bool): return v
    s = str(v).strip().lower()
    if s in {"true", "1", "yes"}: return True
    if s in {"false", "0", "no"}: return False
    raise ValueError(f"Cannot normalize boolean value {v!r}")


def parse_number(v: Any) -> float:
    x = float(v)
    if not math.isfinite(x):
        raise ValueError(f"Non-finite numeric value {v!r}")
    return x


def key_for(row: dict[str, Any], cols: list[str]) -> tuple[str, ...]:
    return tuple(norm_key(row.get(c)) for c in cols)


def load_registry(path: Path, table: str | None = None) -> dict[str, Any]:
    source = json.loads(path.read_text(encoding="utf-8"))
    if "parity_tables" in source:
        if not table:
            raise ValueError("This parity contract requires --table")
        tables = source["parity_tables"]
        if table not in tables:
            raise ValueError(f"Unknown parity table {table!r}; choose one of {sorted(tables)}")
        selected = tables[table]
        reg = {
            "registry_version": source.get("contract_version"),
            "table": table,
            "key_columns": selected.get("key_columns"),
            "features": selected.get("features"),
            "tolerances": source.get("tolerances", {}),
        }
    else:
        if table:
            raise ValueError("--table is only valid with a multi-table parity contract")
        reg = source
    if not isinstance(reg.get("key_columns"), list) or not reg["key_columns"]:
        raise ValueError("Registry must define a non-empty key_columns list")
    if len(set(reg["key_columns"])) != len(reg["key_columns"]):
        raise ValueError("Registry key_columns must be unique")
    if not isinstance(reg.get("features"), dict) or not reg["features"]:
        raise ValueError("Registry must define a non-empty features object")
    allowed = {"numeric", "integer", "categorical", "identifier", "boolean"}
    for name, spec in reg["features"].items():
        if spec.get("type") not in allowed:
            raise ValueError(f"Feature {name!r} has unsupported or missing type")
        if "nullable" not in spec:
            raise ValueError(f"Feature {name!r} must explicitly declare nullable")
    return reg


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def audit(python_rows: list[dict[str, Any]], js_rows: list[dict[str, Any]], registry: dict[str, Any], sample_limit: int = 20) -> dict[str, Any]:
    keys = registry["key_columns"]
    features = registry["features"]
    pmap: dict[tuple[str, ...], dict[str, Any]] = {}
    jmap: dict[tuple[str, ...], dict[str, Any]] = {}
    pdups, jdups, pnullkeys, jnullkeys = [], [], [], []
    for rows, mapping, dups, nullkeys in ((python_rows, pmap, pdups, pnullkeys), (js_rows, jmap, jdups, jnullkeys)):
        for row in rows:
            k = key_for(row, keys)
            if any(part == "<NULL>" for part in k):
                nullkeys.append(k)
                continue
            if k in mapping: dups.append(k)
            else: mapping[k] = row
    pkeys, jkeys = set(pmap), set(jmap)
    shared = sorted(pkeys & jkeys)
    missing_in_js = sorted(pkeys - jkeys)
    extra_in_js = sorted(jkeys - pkeys)
    feature_results = {}
    mismatch_samples = []
    for name, spec in features.items():
        absent_p = sum(name not in r for r in python_rows)
        absent_j = sum(name not in r for r in js_rows)
        typ = spec["type"]
        compared = null_mismatch = nullability_violations = within = exact = 0
        errors, signed = [], []
        invalid = []
        for k in shared:
            a, b = pmap[k].get(name), jmap[k].get(name)
            if name not in pmap[k] or name not in jmap[k]:
                continue
            na, nb = is_null(a), is_null(b)
            if na or nb:
                compared += 1
                if na and nb:
                    exact += 1; within += 1
                    if not spec.get("nullable", True):
                        nullability_violations += 1
                        if len(mismatch_samples) < sample_limit:
                            mismatch_samples.append({"key": k, "feature": name, "python": a, "javascript": b, "reason": "null_in_non_nullable_feature"})
                else:
                    null_mismatch += 1
                    if len(mismatch_samples) < sample_limit:
                        mismatch_samples.append({"key": k, "feature": name, "python": a, "javascript": b, "reason": "null_mismatch"})
                continue
            compared += 1
            try:
                if typ in {"integer", "categorical", "identifier", "boolean"}:
                    if typ == "boolean": equal = parse_bool(a) == parse_bool(b)
                    elif typ == "integer": equal = int(a) == int(b)
                    else: equal = str(a) == str(b)
                    if equal: exact += 1; within += 1
                    else:
                        if len(mismatch_samples) < sample_limit:
                            mismatch_samples.append({"key": k, "feature": name, "python": a, "javascript": b, "reason": "exact_mismatch"})
                elif typ == "numeric":
                    x, y = parse_number(a), parse_number(b)
                    err = abs(x-y); errors.append(err); signed.append(y-x)
                    tol = registry.get("tolerances", {}).get(spec.get("tolerance_class", "default_numeric"), {"rtol":1e-7,"atol":1e-9})
                    # Decimal-rounded outputs can land microscopically beyond an
                    # absolute tolerance after binary-float parsing (for example,
                    # 0.434435 - 0.434434). Add comparison-only slack when the
                    # contract defines a non-zero absolute tolerance.
                    boundary_slack = 1e-12 if tol["atol"] > 0 else 0.0
                    ok = math.isclose(
                        x, y, rel_tol=tol["rtol"],
                        abs_tol=tol["atol"] + boundary_slack,
                    )
                    if ok: within += 1
                    if x == y: exact += 1
                    if not ok and len(mismatch_samples) < sample_limit:
                        mismatch_samples.append({"key": k, "feature": name, "python": x, "javascript": y, "abs_error": err, "reason": "numeric_out_of_tolerance"})
                else:
                    raise ValueError(f"Unsupported registry type {typ!r}")
            except (ValueError, TypeError, OverflowError) as e:
                invalid.append({"key": k, "python": a, "javascript": b, "error": str(e)})
        absent = absent_p > 0 or absent_j > 0
        result = {"type":typ,"python_missing_values":absent_p,"javascript_missing_values":absent_j,"compared":compared,"exact_matches":exact,"within_tolerance":within,"null_mismatches":null_mismatch,"nullability_violations":nullability_violations,"invalid_values":invalid[:sample_limit],"pass": not absent and null_mismatch == 0 and nullability_violations == 0 and not invalid and within == compared}
        if errors:
            se = sorted(errors)
            result.update({"max_absolute_error":max(errors),"mean_absolute_error":statistics.mean(errors),"rmse":math.sqrt(statistics.mean(e*e for e in errors)),"mean_signed_error":statistics.mean(signed),"p50_absolute_error":se[int(.50*(len(se)-1))],"p95_absolute_error":se[int(.95*(len(se)-1))],"p99_absolute_error":se[int(.99*(len(se)-1))]})
        feature_results[name] = result
    join_fields = [n for n,s in features.items() if n == "has_360_frame"]
    join_report = {}
    if join_fields:
        n = join_fields[0]
        for label, rows in (("python", python_rows), ("javascript", js_rows)):
            vals = [parse_bool(r[n]) for r in rows if n in r and not is_null(r[n])]
            join_report[label] = {"rows_with_360":sum(vals),"rows_without_360":len(vals)-sum(vals),"coverage":sum(vals)/len(vals) if vals else None}
    structural_pass = not pdups and not jdups and not pnullkeys and not jnullkeys and not missing_in_js and not extra_in_js
    features_pass = all(x["pass"] for x in feature_results.values())
    return {"summary":{"status":"PASS" if structural_pass and features_pass else "FAIL","python_rows":len(python_rows),"javascript_rows":len(js_rows),"shared_keys":len(shared),"missing_in_javascript":len(missing_in_js),"extra_in_javascript":len(extra_in_js),"python_duplicate_keys":len(pdups),"javascript_duplicate_keys":len(jdups),"python_null_key_rows":len(pnullkeys),"javascript_null_key_rows":len(jnullkeys),"features_passed":sum(x["pass"] for x in feature_results.values()),"features_total":len(feature_results)},"row_integrity":{"missing_in_javascript_sample":missing_in_js[:sample_limit],"extra_in_javascript_sample":extra_in_js[:sample_limit],"python_duplicate_sample":pdups[:sample_limit],"javascript_duplicate_sample":jdups[:sample_limit],"python_null_key_sample":pnullkeys[:sample_limit],"javascript_null_key_sample":jnullkeys[:sample_limit]},"join_report":join_report,"features":feature_results,"mismatch_samples":mismatch_samples}


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare Python and JavaScript CTA feature outputs")
    ap.add_argument("--python", required=True, type=Path, help="Python output CSV, JSON, or JSONL")
    ap.add_argument("--javascript", required=True, type=Path, help="JavaScript output CSV, JSON, or JSONL")
    ap.add_argument("--registry", type=Path, default=Path("config/feature_registry.json"))
    ap.add_argument("--table", help="Entity grain to select from a multi-table parity contract")
    ap.add_argument("--out", type=Path, default=Path("reports/parity"))
    args = ap.parse_args()
    reg = load_registry(args.registry, args.table)
    p, j = load_rows(args.python), load_rows(args.javascript)
    result = audit(p, j, reg)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out/"parity_report.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    lines = ["# Cross-runtime parity report", "", f"**Status: {result['summary']['status']}**", "", "## Summary", "", "| Metric | Value |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k,v in result["summary"].items()]
    lines += ["", "## Feature results", "", "| Feature | Pass | Compared | Within tolerance | Max absolute error |", "|---|---:|---:|---:|---:|"]
    for n,r in result["features"].items(): lines.append(f"| {n} | {r['pass']} | {r['compared']} | {r['within_tolerance']} | {r.get('max_absolute_error','—')} |")
    lines += ["", "## 360 coverage", "", "```json", json.dumps(result["join_report"],indent=2), "```", ""]
    (args.out/"parity_report.md").write_text("\n".join(lines), encoding="utf-8")
    manifest = {"registry_version":reg.get("registry_version"),"table":reg.get("table"),"python_input":{"path":str(args.python),"sha256":file_sha(args.python),"rows":len(p)},"javascript_input":{"path":str(args.javascript),"sha256":file_sha(args.javascript),"rows":len(j)},"result":result["summary"]}
    (args.out/"run_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    return 0 if result["summary"]["status"] == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
