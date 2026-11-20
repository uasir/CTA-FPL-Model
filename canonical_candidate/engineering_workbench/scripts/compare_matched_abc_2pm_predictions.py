"""Fail-closed paired ABC versus standalone 2PM evaluation on manifest test keys."""
from __future__ import annotations
import argparse, csv, json, math, random, statistics
from collections import defaultdict
from pathlib import Path
from matched_fold_keys import canonical_key, load_partition_keys, sha_keys, verify_manifest_partition_hashes


def read_predictions(path, kind):
    required = {"fold", "season", "fpl_element_id", "gameweek", "actual_points"}
    fields = (["abc_calibrated_points", "abc_raw_points", "fpl_history_calibrated_points"]
              if kind == "abc" else ["affine_calibrated_points", "predicted_points"])
    result = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = (required | set(fields)) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{kind} prediction file missing columns: {sorted(missing)}")
        for raw in reader:
            key = canonical_key(raw["season"], raw["fpl_element_id"], raw["gameweek"])
            if key in result:
                raise ValueError(f"Duplicate {kind} prediction key: {key}")
            result[key] = {"fold": int(raw["fold"]), "actual": float(raw["actual_points"]),
                           **{field: float(raw[field]) for field in fields}}
    if not result:
        raise ValueError(f"{kind} prediction file is empty")
    return result


def validate_predictions(name, rows, partitions, manifest):
    expected = {}
    for fold, parts in partitions.items():
        for key in parts["test"]:
            if key in expected:
                raise ValueError(f"Test key occurs in multiple folds: {key}")
            expected[key] = fold
    if set(rows) != set(expected):
        raise ValueError(f"{name} prediction keys differ from manifest test cohort: missing={len(set(expected)-set(rows))}, extra={len(set(rows)-set(expected))}")
    mf = {int(x["fold"]): x for x in manifest["folds"]}
    result = {}
    for fold in sorted(partitions):
        keys = sorted(k for k, assigned in expected.items() if assigned == fold)
        if any(rows[k]["fold"] != fold for k in keys):
            raise ValueError(f"{name} prediction fold labels differ from manifest fold {fold}")
        digest = sha_keys(keys)
        if digest != mf[fold]["test_key_sha256"]:
            raise ValueError(f"{name} prediction test-key hash differs from manifest for fold {fold}")
        result[fold] = {"test_player_gameweeks": len(keys), "test_key_sha256": digest}
    return result


def metrics(rows, pred):
    errors = [r["actual"] - r[pred] for r in rows]
    ae = sorted(abs(x) for x in errors)
    def q(p):
        x = (len(ae)-1)*p; lo, hi = math.floor(x), math.ceil(x)
        return ae[lo] if lo == hi else ae[lo]*(hi-x)+ae[hi]*(x-lo)
    return {"n":len(rows), "mae":statistics.mean(ae),
            "rmse":math.sqrt(statistics.mean(x*x for x in errors)),
            "mean_signed_error_actual_minus_predicted":statistics.mean(errors),
            "absolute_error_p50":q(.5), "absolute_error_p90":q(.9),
            "absolute_error_p95":q(.95),
            "large_error_rate_ge_6":sum(x>=6 for x in ae)/len(ae),
            "large_error_rate_ge_10":sum(x>=10 for x in ae)/len(ae)}


def player_cluster_bootstrap(rows, candidate, comparator, n_boot, seed):
    clusters=defaultdict(list)
    for r in rows: clusters[(r["season"],r["player_id"])].append(r)
    names=sorted(clusters)
    if len(names)<2: raise ValueError("Need at least two player clusters")
    rng=random.Random(seed); d_mae=[]; d_mse=[]; win=[]
    for _ in range(n_boot):
        sample=[rng.choice(names) for _ in names]
        ca=[]; co=[]; cs=[]; os=[]; wins=[]
        for name in sample:
            for r in clusters[name]:
                ec=r["actual"]-r[candidate]; eo=r["actual"]-r[comparator]
                ca.append(abs(ec)); co.append(abs(eo)); cs.append(ec*ec); os.append(eo*eo)
                wins.append(1. if abs(ec)<abs(eo) else 0. if abs(ec)>abs(eo) else .5)
        d_mae.append(statistics.mean(ca)-statistics.mean(co))
        d_mse.append(statistics.mean(cs)-statistics.mean(os)); win.append(statistics.mean(wins))
    def ci(x):
        x=sorted(x); return [x[int(.025*(len(x)-1))],x[int(.975*(len(x)-1))]]
    return {"method":"PAIRED_PLAYER_SEASON_CLUSTER_BOOTSTRAP","clusters":len(names),
            "replicates":n_boot,"delta_definition":"candidate minus comparator; negative favours candidate",
            "mae_delta_ci95":ci(d_mae),"mse_delta_ci95":ci(d_mse),
            "candidate_absolute_error_win_rate_ci95":ci(win)}


def ranks(values):
    order=sorted(range(len(values)),key=lambda i:values[i]); out=[0.]*len(values); i=0
    while i<len(order):
        j=i+1
        while j<len(order) and values[order[j]]==values[order[i]]: j+=1
        rank=(i+1+j)/2
        for z in range(i,j): out[order[z]]=rank
        i=j
    return out


def corr(x,y):
    mx,my=statistics.mean(x),statistics.mean(y)
    dx=[v-mx for v in x]; dy=[v-my for v in y]
    den=math.sqrt(sum(v*v for v in dx)*sum(v*v for v in dy))
    return sum(a*b for a,b in zip(dx,dy))/den if den else 0.


def deadline_metric(rows,pred,top_k=100):
    k=min(top_k,len(rows)); ar=ranks([r["actual"] for r in rows]); pr=ranks([r[pred] for r in rows])
    chosen=sorted(rows,key=lambda r:(-r[pred],r["player_id"]))[:k]
    oracle=sorted(rows,key=lambda r:(-r["actual"],r["player_id"]))[:k]
    universe=statistics.mean(r["actual"] for r in rows)
    selected=statistics.mean(r["actual"] for r in chosen)
    oracle_mean=statistics.mean(r["actual"] for r in oracle)
    return {"n":len(rows),"top_k":k,"spearman":corr(ar,pr),
            "selected_mean_points":selected,"universe_mean_points":universe,
            "oracle_top_k_mean_points":oracle_mean,"top_k_lift_over_universe":selected-universe,
            "top_k_regret_vs_oracle":oracle_mean-selected}


def ranking(rows,pred):
    groups=defaultdict(list)
    for r in rows: groups[(r["season"],r["gameweek"])].append(r)
    by={k:deadline_metric(v,pred) for k,v in groups.items()}
    return {"n_deadlines":len(by),
            "macro_spearman":statistics.mean(x["spearman"] for x in by.values()),
            "macro_selected_mean_points":statistics.mean(x["selected_mean_points"] for x in by.values()),
            "macro_top_k_lift_over_universe":statistics.mean(x["top_k_lift_over_universe"] for x in by.values()),
            "macro_top_k_regret_vs_oracle":statistics.mean(x["top_k_regret_vs_oracle"] for x in by.values()),
            "by_deadline":{f"{s}:GW{gw}":by[(s,gw)] for s,gw in sorted(by)},
            "_raw":by}


def deadline_bootstrap(a,b,n_boot,seed):
    if set(a)!=set(b): raise ValueError("Ranking deadlines differ")
    keys=sorted(a); rng=random.Random(seed); samples={m:[] for m in ("spearman","selected_mean_points","top_k_lift_over_universe")}
    for _ in range(n_boot):
        chosen=[rng.choice(keys) for _ in keys]
        for m in samples: samples[m].append(statistics.mean(a[k][m]-b[k][m] for k in chosen))
    def ci(x):
        x=sorted(x); return [x[int(.025*(len(x)-1))],x[int(.975*(len(x)-1))]]
    return {"method":"PAIRED_TEST_DEADLINE_CLUSTER_BOOTSTRAP","deadline_clusters":len(keys),
            "replicates":n_boot,
            "caveat":"One historical season only; deadline resampling is descriptive, not cross-season generalisation.",
            **{m+"_candidate_minus_comparator_ci95":ci(v) for m,v in samples.items()}}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--abc-predictions",type=Path,required=True)
    p.add_argument("--two-pm-predictions",type=Path,required=True)
    p.add_argument("--partition-keys",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--bootstrap-replicates",type=int,default=2000)
    args=p.parse_args()
    if args.bootstrap_replicates<100: p.error("--bootstrap-replicates must be at least 100")
    parts=load_partition_keys(args.partition_keys); manifest=json.loads(args.manifest.read_text())
    verify_manifest_partition_hashes(parts,manifest)
    abc=read_predictions(args.abc_predictions,"abc"); pm=read_predictions(args.two_pm_predictions,"two_pm")
    ah=validate_predictions("ABC",abc,parts,manifest); ph=validate_predictions("2PM",pm,parts,manifest)
    if set(abc)!=set(pm): raise ValueError("ABC and 2PM prediction keys are not identical")
    rows=[]
    for key in sorted(abc):
        a,t=abc[key],pm[key]
        if a["fold"]!=t["fold"]: raise ValueError(f"Fold mismatch for {key}")
        if abs(a["actual"]-t["actual"])>1e-9: raise ValueError(f"Actual points mismatch for {key}")
        rows.append({"season":key[0],"player_id":key[1],"gameweek":key[2],"actual":a["actual"],
          "abc_calibrated":a["abc_calibrated_points"],"abc_raw":a["abc_raw_points"],
          "fpl_history":a["fpl_history_calibrated_points"],
          "two_pm_affine":t["affine_calibrated_points"],"two_pm_raw":t["predicted_points"]})
    model_keys={"ABC_calibrated":"abc_calibrated","ABC_raw":"abc_raw",
      "FPL_history_reference":"fpl_history","2PM_affine_calibrated":"two_pm_affine","2PM_raw":"two_pm_raw"}
    forecast={name:metrics(rows,key) for name,key in model_keys.items()}
    pairs={
      "ABC_calibrated_vs_2PM_affine_calibrated":("abc_calibrated","two_pm_affine"),
      "ABC_calibrated_vs_FPL_history_reference":("abc_calibrated","fpl_history"),
      "2PM_affine_calibrated_vs_FPL_history_reference":("two_pm_affine","fpl_history")}
    paired={name:player_cluster_bootstrap(rows,a,b,args.bootstrap_replicates,20261120+i)
      for i,(name,(a,b)) in enumerate(pairs.items())}
    rank_reports={}; rank_raw={}
    for name,key in model_keys.items():
        rr=ranking(rows,key); rank_raw[key]=rr.pop("_raw"); rank_reports[name]=rr
    rank_pairs={name:deadline_bootstrap(rank_raw[a],rank_raw[b],args.bootstrap_replicates,20261140+i)
      for i,(name,(a,b)) in enumerate(pairs.items())}
    per_fold={}
    for fold in sorted(parts):
        subset=[r for r in rows if pm[(r["season"],r["player_id"],r["gameweek"])]["fold"]==fold]
        per_fold[str(fold)]={"n":len(subset),
          "ABC_calibrated":metrics(subset,"abc_calibrated"),
          "2PM_affine_calibrated":metrics(subset,"two_pm_affine"),
          "FPL_history_reference":metrics(subset,"fpl_history")}
    manifest_folds={int(x["fold"]):x for x in manifest["folds"]}
    report={"status":"PASS_EXACT_MATCHED_PREDICTION_KEYS_RESEARCH_ONLY",
      "comparison":"ABC_ONLY_VS_STANDALONE_CONVENTIONAL_FPL_2PM_TRANSFORMER",
      "season":manifest.get("season"),"matched_test_player_gameweeks":len(rows),
      "matched_unique_players":len({r["player_id"] for r in rows}),
      "matched_deadlines":len({(r["season"],r["gameweek"]) for r in rows}),
      "manifest_common_cohort_sha256":manifest.get("common_key_sha256"),
      "fold_test_key_hashes":{str(f):{"manifest":manifest_folds[f]["test_key_sha256"],
          "abc_prediction":ah[f]["test_key_sha256"],"two_pm_prediction":ph[f]["test_key_sha256"]}
          for f in sorted(parts)},
      "forecast_metrics":forecast,"paired_forecast_uncertainty":paired,
      "deadline_local_ranking":rank_reports,"paired_deadline_ranking_uncertainty":rank_pairs,
      "per_fold_forecast_metrics":per_fold,
      "point_in_time_status":"NOT_VERIFIED_RETROSPECTIVE_SOURCE_VINTAGES",
      "promotion_status":"RESEARCH_ONLY_DO_NOT_PROMOTE",
      "limitations":[
        "The cohort is the restricted 2017/18 verified Wyscout-FPL identity population, not a representative FPL universe.",
        "Only one historical season is available; player-cluster intervals do not establish cross-season generalisation.",
        "Deadline-cluster ranking intervals are descriptive because all deadlines belong to one season.",
        "Source vintages were not archived at the historical FPL deadlines.",
        "ABC and 2PM are compared as calibrated point forecasts; their architectures and feature availability differ.",
        "No ABC+2PM or FPL+ABC hybrid is evaluated here."]}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps(report,indent=2,allow_nan=False))


if __name__=="__main__": main()
