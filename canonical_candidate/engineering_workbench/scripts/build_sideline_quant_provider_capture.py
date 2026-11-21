#!/usr/bin/env python3
"""Build the common M3 capture envelope from a Sideline Quant artifact."""
from __future__ import annotations
import argparse, base64, hashlib, json
from pathlib import Path
from typing import Any, Mapping
from capture_fpl_cat_snapshot import FPL_BOOTSTRAP_URL

class ProviderCaptureBuildError(ValueError):
    pass

def _decode(value: Any, label: str):
    if not isinstance(value, str) or not value:
        raise ProviderCaptureBuildError(f"{label} archive is missing")
    try:
        raw = base64.b64decode(value, validate=True)
        obj = json.loads(raw)
    except Exception as exc:
        raise ProviderCaptureBuildError(f"{label} archive is not base64 JSON") from exc
    if not isinstance(obj, dict):
        raise ProviderCaptureBuildError(f"{label} archive must be a JSON object")
    return raw, obj

def build_sideline_quant_provider_capture(raw_capture: Mapping[str, Any], parsed: Mapping[str, Any]) -> dict[str, Any]:
    if raw_capture.get("provider", {}).get("name") != "Sideline Quant":
        raise ProviderCaptureBuildError("raw capture is not from Sideline Quant")
    snapshot = parsed.get("player_gameweek_snapshot")
    if not isinstance(snapshot, Mapping):
        raise ProviderCaptureBuildError("parsed artifact lacks player-Gameweek decision snapshot")
    provider = snapshot.get("provider", {})
    if (provider.get("name") != "Sideline Quant" or provider.get("product") != "gameweek_projections"
            or provider.get("variant") != "provider_native_xp"):
        raise ProviderCaptureBuildError("normalized provider product/variant is not registered")
    if snapshot.get("grain") != "player_gameweek" or snapshot.get("decision_eligible") is not True:
        raise ProviderCaptureBuildError("player-Gameweek snapshot is not decision eligible")
    raw_timing = raw_capture.get("timing", {})
    normalized_timing = snapshot.get("timing", {})
    if (snapshot.get("season") != raw_capture.get("season")
            or snapshot.get("target_gameweek") != raw_capture.get("target_gameweek")):
        raise ProviderCaptureBuildError("raw and normalized season/Gameweek differ")
    for field in ("generated_at_utc", "captured_at_utc", "deadline_utc"):
        if normalized_timing.get(field) != raw_timing.get(field):
            raise ProviderCaptureBuildError(f"raw and normalized {field} differ")
    archives = raw_capture.get("raw_archives", {})
    provider_raw, provider_payload = _decode(archives.get("provider_response_base64"), "Sideline Quant provider")
    bootstrap_raw, bootstrap = _decode(archives.get("official_fpl_bootstrap_base64"), "official FPL bootstrap")
    source, meta_source = raw_capture.get("source", {}), raw_capture.get("official_metadata_provenance", {})
    provider_hash, bootstrap_hash = hashlib.sha256(provider_raw).hexdigest(), hashlib.sha256(bootstrap_raw).hexdigest()
    if source.get("raw_sha256") != provider_hash or snapshot.get("source", {}).get("raw_sha256") != provider_hash:
        raise ProviderCaptureBuildError("provider raw hash mismatch")
    if meta_source.get("raw_sha256") != bootstrap_hash or meta_source.get("source_url") != FPL_BOOTSTRAP_URL:
        raise ProviderCaptureBuildError("official bootstrap hash or URL mismatch")
    if provider_payload.get("gameweek") != snapshot.get("target_gameweek"):
        raise ProviderCaptureBuildError("raw provider Gameweek differs from normalized snapshot")
    elements, types = bootstrap.get("elements"), bootstrap.get("element_types")
    if not isinstance(elements, list) or not isinstance(types, list):
        raise ProviderCaptureBuildError("official bootstrap lacks elements or element_types")
    allowed_positions = {"GKP", "DEF", "MID", "FWD"}
    type_names = {x.get("id"):x.get("singular_name_short") for x in types if isinstance(x,dict)}
    metadata = {}
    for x in elements:
        if isinstance(x,dict):
            pid=x.get("id"); p=type_names.get(x.get("element_type"))
            if p not in allowed_positions:
                p = None
            if isinstance(pid,int) and p and isinstance(x.get("team"),int) and isinstance(x.get("now_cost"),int):
                metadata[pid]={"fpl_element_id":pid,"price":x["now_cost"]/10,"position":p,"team_id":x["team"]}
    records=snapshot.get("records")
    if not isinstance(records,list) or not records:
        raise ProviderCaptureBuildError("normalized player-Gameweek records are empty")
    ids=[r.get("fpl_element_id") for r in records if isinstance(r,Mapping)]
    if len(ids)!=len(records) or any(isinstance(i,bool) or not isinstance(i,int) or i<1 for i in ids) or len(set(ids))!=len(ids):
        raise ProviderCaptureBuildError("normalized player IDs are invalid or duplicated")
    missing=sorted(set(ids)-set(metadata))
    if missing:
        raise ProviderCaptureBuildError("official bootstrap is missing player IDs: "+", ".join(map(str,missing)))
    return {
        "provider_snapshot":dict(snapshot),
        "player_metadata":[metadata[i] for i in ids],
        "raw_archives":{
            "provider_response_base64":archives["provider_response_base64"],
            "fpl_bootstrap_response_base64":archives["official_fpl_bootstrap_base64"],
        },
        "player_metadata_provenance":{
            "source_url":FPL_BOOTSTRAP_URL,"raw_snapshot_id":meta_source["raw_snapshot_id"],
            "raw_sha256":bootstrap_hash,"captured_at_utc":meta_source["captured_at_utc"],
            "row_count":len(elements),
        },
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-capture",type=Path,required=True)
    p.add_argument("--normalized-capture",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    raw=json.loads(a.raw_capture.read_text(encoding="utf-8"))
    parsed=json.loads(a.normalized_capture.read_text(encoding="utf-8"))
    result=build_sideline_quant_provider_capture(raw,parsed)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"provider":result["provider_snapshot"]["provider"]["name"],
      "snapshot_id":result["provider_snapshot"]["snapshot_id"],
      "target_gameweek":result["provider_snapshot"]["target_gameweek"],
      "forecast_rows":len(result["provider_snapshot"]["records"])},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
