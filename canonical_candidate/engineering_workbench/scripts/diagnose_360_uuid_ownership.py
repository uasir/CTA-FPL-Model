#!/usr/bin/env python3
"""Diagnose whether a 360 frame file's event UUIDs belong to another sampled match."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def scan_uuid_ownership(events_dir: Path, frame_file: Path, target_match_id: str):
    frames=load(frame_file)
    frame_ids=[str(x.get("event_uuid")) for x in frames if x.get("event_uuid")]
    frame_set=set(frame_ids)
    event_files=sorted(events_dir.glob("*.json"))
    matches=[]
    target_teams=[]
    target_event_count=0
    for path in event_files:
        events=load(path)
        ids={str(x.get("id")) for x in events if x.get("id")}
        overlap=frame_set & ids
        teams=sorted({x.get("team",{}).get("name","") for x in events if x.get("team",{}).get("name")})
        if path.stem==str(target_match_id):
            target_event_count=len(ids)
            target_teams=teams
        if overlap:
            matches.append({"match_id":path.stem,"shared_event_uuids":len(overlap),"sample_uuids":sorted(overlap)[:5],"teams":teams})
    target_overlap=next((x["shared_event_uuids"] for x in matches if x["match_id"]==str(target_match_id)),0)
    other=[x for x in matches if x["match_id"]!=str(target_match_id)]
    if other:
        status="SOURCE_MISMATCH_SUSPECTED"
    elif target_overlap:
        status="MATCHED"
    else:
        status="UNRESOLVED_NO_MATCH_IN_SAMPLE"
    return {
        "target_match_id":str(target_match_id),
        "frame_file":frame_file.name,
        "event_files_scanned":len(event_files),
        "target_event_count":target_event_count,
        "target_event_teams":target_teams,
        "frame_count":len(frame_ids),
        "unique_frame_uuids":len(frame_set),
        "same_match_shared_uuids":target_overlap,
        "other_match_hits":other,
        "status":status,
        "interpretation":"A hit in another event file suggests the 360 file may be assigned to the wrong match. No hit in this sample does not identify its true source; keep the 360 file quarantined."
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--events-dir",type=Path,required=True)
    p.add_argument("--frame-file",type=Path,required=True)
    p.add_argument("--target-match-id",default="3837706")
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    report=scan_uuid_ownership(a.events_dir,a.frame_file,a.target_match_id)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    md=["# 360 event UUID source diagnostic","",f"**Status:** {report['status']}","",
        f"- Target match: {report['target_match_id']}",f"- Event files scanned: {report['event_files_scanned']}",
        f"- Target event teams: {', '.join(report['target_event_teams'])}",
        f"- Frame UUIDs: {report['unique_frame_uuids']}",f"- Same-match UUID overlap: {report['same_match_shared_uuids']}",
        f"- Other-match hits: {len(report['other_match_hits'])}",""]
    for hit in report["other_match_hits"]:
        md.append(f"- Match {hit['match_id']}: {hit['shared_event_uuids']} shared UUIDs ({', '.join(hit['teams'])})")
    md += ["",report["interpretation"]]
    a.out.with_suffix(".md").write_text("\n".join(md)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
