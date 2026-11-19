#!/usr/bin/env python3
"""Train and time-holdout an exploratory ridge baseline on lagged FPL rows (v0.1.2).

This model is deliberately not wired into either recommendation engine:
the historical source is structurally lagged but not fully point-in-time verified.
Fixture-level minutes predictions are constrained to 0–90 before gameweek aggregation.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict
from pathlib import Path

FEATURES=(
    "prior_gw_points",
    "prior3_gw_points_avg",
    "prior5_gw_points_avg",
    "prior3_gw_minutes_avg",
    "prior5_gw_minutes_avg",
    "prior3_gw_xg_avg",
    "prior3_gw_xa_avg",
    "season_to_date_points_per90",
    "was_home",
    "team_difficulty_snapshot",
    "opponent_difficulty_snapshot",
    "fixture_count",
)
RIDGE_LAMBDA=10.0


def number(value,default=0.0):
    try:
        result=float(value)
    except (TypeError,ValueError):
        return default
    return result if math.isfinite(result) else default


def optional_number(value):
    if value is None or str(value).strip()=="":
        return None
    try:
        result=float(value)
    except (TypeError,ValueError):
        return None
    return result if math.isfinite(result) else None


def median(values):
    ordered=sorted(values)
    middle=len(ordered)//2
    if len(ordered)%2:
        return ordered[middle]
    return (ordered[middle-1]+ordered[middle])/2.0


def bool_number(value):
    if isinstance(value,bool): return 1.0 if value else 0.0
    return 1.0 if str(value).strip().lower() in {"true","1","yes","y"} else 0.0


def solve_linear_system(matrix,vector):
    n=len(vector)
    a=[list(map(float,matrix[i]))+[float(vector[i])] for i in range(n)]
    for col in range(n):
        pivot=max(range(col,n),key=lambda row:abs(a[row][col]))
        if abs(a[pivot][col])<1e-12:
            raise ValueError("Ridge normal equation is singular")
        a[col],a[pivot]=a[pivot],a[col]
        scale=a[col][col]
        a[col]=[value/scale for value in a[col]]
        for row in range(n):
            if row==col: continue
            factor=a[row][col]
            if factor:
                a[row]=[a[row][j]-factor*a[col][j] for j in range(n+1)]
    return [a[i][-1] for i in range(n)]


def fit_ridge(rows,target_key,feature_names=FEATURES,ridge_lambda=RIDGE_LAMBDA):
    raw=[[optional_number(row.get(name)) for name in feature_names] for row in rows]
    targets=[optional_number(row.get(target_key)) for row in rows]
    if any(value is None for value in targets):
        raise ValueError(f"Missing/non-finite training target: {target_key}")
    if len(raw)<len(feature_names)+2:
        raise ValueError("Not enough training rows for exploratory ridge fit")
    imputation_values=[]
    for index,name in enumerate(feature_names):
        observed=[row[index] for row in raw if row[index] is not None]
        if not observed:
            raise ValueError(f"Feature has no observed training values and cannot be imputed: {name}")
        imputation_values.append(median(observed))
    # Fit imputation values on training rows only. Missingness indicators retain
    # the distinction between an observed zero and an unavailable provider metric.
    design_names=list(feature_names)+[f"{name}__missing" for name in feature_names]
    design=[]
    for row in raw:
        imputed=[imputation_values[j] if row[j] is None else row[j] for j in range(len(feature_names))]
        indicators=[1.0 if row[j] is None else 0.0 for j in range(len(feature_names))]
        design.append(imputed+indicators)
    means=[sum(row[j] for row in design)/len(design) for j in range(len(design_names))]
    variances=[sum((row[j]-means[j])**2 for row in design)/len(design) for j in range(len(design_names))]
    scales=[math.sqrt(value) if value>1e-12 else 1.0 for value in variances]
    matrix_size=len(design_names)+1
    gram=[[0.0]*matrix_size for _ in range(matrix_size)]
    cross=[0.0]*matrix_size
    for raw_row,target in zip(design,targets):
        vector=[1.0]+[(raw_row[j]-means[j])/scales[j] for j in range(len(design_names))]
        for i in range(matrix_size):
            cross[i]+=vector[i]*target
            for j in range(matrix_size):
                gram[i][j]+=vector[i]*vector[j]
    for i in range(1,matrix_size):
        gram[i][i]+=ridge_lambda
    coefficients=solve_linear_system(gram,cross)
    return {
        "feature_names":design_names,
        "source_feature_names":list(feature_names),
        "imputation_values":imputation_values,
        "missing_value_policy":"TRAINING_MEDIAN_PLUS_MISSINGNESS_INDICATOR",
        "means":means,
        "scales":scales,
        "coefficients":coefficients,
        "ridge_lambda":ridge_lambda,
    }


def predict(model,row):
    # Retain compatibility with explicit legacy test fixtures/models. All newly
    # fitted models carry source_feature_names and use missingness indicators.
    if "source_feature_names" not in model:
        values=[number(row.get(name)) for name in model["feature_names"]]
        vector=[1.0]+[(values[j]-model["means"][j])/model["scales"][j] for j in range(len(values))]
        return sum(vector[i]*model["coefficients"][i] for i in range(len(vector)))
    source_names=model["source_feature_names"]
    values=[optional_number(row.get(name)) for name in source_names]
    imputation=model["imputation_values"]
    imputed=[imputation[j] if values[j] is None else values[j] for j in range(len(source_names))]
    indicators=[1.0 if values[j] is None else 0.0 for j in range(len(source_names))]
    design=imputed+indicators
    vector=[1.0]+[(design[j]-model["means"][j])/model["scales"][j] for j in range(len(design))]
    return sum(vector[i]*model["coefficients"][i] for i in range(len(vector)))


def mae(actual,predicted):
    return sum(abs(a-p) for a,p in zip(actual,predicted))/len(actual) if actual else None


def rmse(actual,predicted):
    return math.sqrt(sum((a-p)**2 for a,p in zip(actual,predicted))/len(actual)) if actual else None


def aggregate_predictions(rows,points_model,minutes_model):
    groups=defaultdict(list)
    for row in rows:
        key=(str(row["fpl_element_id"]),int(row["gameweek"]))
        groups[key].append(row)
    result=[]
    for (player_id,gameweek),items in sorted(groups.items(),key=lambda item:(int(item[0][0]),item[0][1])):
        predicted_points=sum(predict(points_model,row) for row in items)
        # FPL minutes are physically bounded per fixture; constrain each fixture's
        # estimate before summing DGW forecasts.
        predicted_minutes=sum(min(90.0,max(0.0,predict(minutes_model,row))) for row in items)
        result.append({
            "fpl_element_id":player_id,
            "gameweek":gameweek,
            "fixture_count":len(items),
            "actual_points":sum(number(row.get("target_total_points")) for row in items),
            "predicted_points":predicted_points,
            "baseline_last5_points":optional_number(items[0].get("prior5_gw_points_avg")),
            "actual_minutes":sum(number(row.get("target_minutes")) for row in items),
            "predicted_minutes":predicted_minutes,
            "baseline_last_gw_minutes":optional_number(items[0].get("prior_gw_minutes")),
        })
    return result


def metrics(records,actual_key,predicted_key,baseline_key):
    scored=[row for row in records if all(
        optional_number(row.get(key)) is not None
        for key in (actual_key,predicted_key,baseline_key)
    )]
    if not scored:
        raise ValueError(f"No complete rows available for metrics: {actual_key}, {predicted_key}, {baseline_key}")
    actual=[row[actual_key] for row in scored]
    predicted=[row[predicted_key] for row in scored]
    baseline=[row[baseline_key] for row in scored]
    return {
        "rows":len(scored),
        "candidate_rows":len(records),
        "rows_excluded_for_missing_metrics":len(records)-len(scored),
        "model_mae":round(mae(actual,predicted),6),
        "model_rmse":round(rmse(actual,predicted),6),
        "baseline_mae":round(mae(actual,baseline),6),
        "baseline_rmse":round(rmse(actual,baseline),6),
        "mae_delta_model_minus_baseline":round(mae(actual,predicted)-mae(actual,baseline),6),
        "rmse_delta_model_minus_baseline":round(rmse(actual,predicted)-rmse(actual,baseline),6),
        "model_mean_error":round(sum(p-a for a,p in zip(actual,predicted))/len(actual),6),
    }


def train_and_evaluate(rows):
    if not rows:
        raise ValueError("Training input is empty")
    normalized=[]
    fixture_counts=defaultdict(int)
    for row in rows:
        key=(str(row.get("fpl_element_id","")),int(number(row.get("gameweek"),-1)))
        if not key[0] or key[1]<1:
            continue
        fixture_counts[key]+=1
    for row in rows:
        key=(str(row.get("fpl_element_id","")),int(number(row.get("gameweek"),-1)))
        if key not in fixture_counts: continue
        count=fixture_counts[key]
        if count<1: continue
        item=dict(row)
        item["fixture_count"]=float(count)
        for feature in FEATURES:
            if feature=="fixture_count": continue
            value=optional_number(row.get(feature))
            if value is not None and feature in {"prior_gw_points","prior3_gw_points_avg","prior5_gw_points_avg",
                           "prior3_gw_minutes_avg","prior5_gw_minutes_avg",
                           "prior3_gw_xg_avg","prior3_gw_xa_avg"}:
                value=value/count
            elif feature=="was_home":
                value=bool_number(row.get(feature))
            elif value is not None and feature in {"team_difficulty_snapshot","opponent_difficulty_snapshot"}:
                value=value/5.0
            item[feature]=value
        item["target_total_points"]=optional_number(row.get("target_total_points"))
        item["target_minutes"]=optional_number(row.get("target_minutes"))
        if item["target_total_points"] is None or item["target_minutes"] is None:
            raise ValueError("Missing/non-finite FPL target; refusing to encode target as zero")
        normalized.append(item)
    gameweeks=sorted({int(row["gameweek"]) for row in normalized})
    if len(gameweeks)<7:
        raise ValueError("At least seven gameweeks are required for a four-GW temporal holdout")
    validation_gws=gameweeks[-4:]
    train_gws=gameweeks[:-4]
    train_rows=[
        row for row in normalized
        if int(row["gameweek"]) in train_gws and number(row.get("prior_gameweeks_count"))>=1
    ]
    validation_rows=[row for row in normalized if int(row["gameweek"]) in validation_gws]
    if len(train_rows)<len(FEATURES)+2 or not validation_rows:
        raise ValueError("Insufficient train/validation rows for temporal ridge evaluation")
    points_model=fit_ridge(train_rows,"target_total_points")
    minutes_model=fit_ridge(train_rows,"target_minutes")
    predictions=aggregate_predictions(validation_rows,points_model,minutes_model)
    points_metrics=metrics(predictions,"actual_points","predicted_points","baseline_last5_points")
    minutes_metrics=metrics(predictions,"actual_minutes","predicted_minutes","baseline_last_gw_minutes")
    report={
        "status":"EXPLORATORY_ONLY",
        "model_version":"cta-fpl-lagged-ridge-v0.1.2",
        "minutes_prediction_constraints":{"per_fixture_min":0.0,"per_fixture_max":90.0,"applied_before_gameweek_aggregation":True},
        "model_trained":True,
        "point_in_time_status":"NOT_VERIFIED",
        "training_gameweeks":train_gws,
        "validation_gameweeks":validation_gws,
        "training_fixture_rows":len(train_rows),
        "validation_fixture_rows":len(validation_rows),
        "validation_player_gameweek_rows":len(predictions),
        "ridge_lambda":RIDGE_LAMBDA,
        "features":list(FEATURES),
        "missing_feature_policy":"Training-only median imputation with explicit missingness indicators; observed zero remains distinct from missing.",
        "points_missing_feature_counts":{name:sum(1 for row in train_rows if row.get(name) is None) for name in FEATURES},
        "points_metrics":points_metrics,
        "minutes_metrics":minutes_metrics,
        "decision":"DO_NOT_PROMOTE",
        "limitations":[
            "Historical source revisions mean point-in-time status is not verified.",
            "This is one-season exploratory data with a four-gameweek temporal holdout.",
            "The model is not connected to either recommendation engine.",
            "Ridge regularisation is fixed in advance; no hyperparameter tuning is performed on the holdout.",
            "Minutes and points predictions are per fixture and are aggregated to player-gameweek.",
            "CoVar is not estimated from this model's four-gameweek holdout.",
        ],
    }
    return {"points_model":points_model,"minutes_model":minutes_model,"validation_predictions":predictions},report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--out-dir",type=Path,required=True)
    args=parser.parse_args()
    with args.input.open(newline="",encoding="utf-8-sig") as handle:
        rows=list(csv.DictReader(handle))
    model,report=train_and_evaluate(rows)
    args.out_dir.mkdir(parents=True,exist_ok=True)
    (args.out_dir/"fpl_exploratory_ridge_model.json").write_text(json.dumps(model,indent=2),encoding="utf-8")
    (args.out_dir/"fpl_exploratory_ridge_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
