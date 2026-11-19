#!/usr/bin/env python3
"""Expanding-season walk-forward validation for the two-part FPL predictor."""
from __future__ import annotations
import argparse, csv, json, math
import numpy as np
from pathlib import Path

from evaluate_fpl_two_part_model import (
    FEATURES, RIDGE_LAMBDA, binary_metrics, calibrated_probability,
    fit_linear_probability, fit_platt, group_player_gameweeks,
    regression_metrics,
)
from train_fpl_exploratory_ridge import fit_ridge, optional_number, predict, mae, rmse

MINUTES_BASELINE_FEATURES = ("prior_gw_minutes", "prior3_gw_minutes_avg", "prior5_gw_minutes_avg")

MINUTES_BAND_EDGES = (0.0, 1.0, 30.0, 60.0, 90.0)
MINUTES_BAND_REPRESENTATIVES = np.asarray((0.0, 15.0, 45.0, 75.0, 90.0))


def minutes_band(minutes):
    value=float(minutes)
    if value <= 0: return 0
    if value < 30: return 1
    if value < 60: return 2
    if value < 90: return 3
    return 4


def fit_minutes_band_model(rows, ridge_lambda=2.0, iterations=180):
    """Train a regularized multinomial logistic model; all preprocessing is training-only."""
    raw=np.asarray([[optional_number(row.get(name)) for name in FEATURES] for row in rows],dtype=float)
    labels=np.asarray([minutes_band(row["actual_minutes"]) for row in rows],dtype=int)
    if len(rows)<len(FEATURES)+10 or len(set(labels))<2:
        raise ValueError("Insufficient rows or class diversity for minutes-band model")
    medians=[]
    for j,name in enumerate(FEATURES):
        observed=raw[np.isfinite(raw[:,j]),j]
        if len(observed)==0: raise ValueError(f"Feature has no observed training values: {name}")
        medians.append(float(np.median(observed)))
    missing=~np.isfinite(raw)
    imputed=np.where(missing,np.asarray(medians),raw)
    design=np.concatenate((imputed,missing.astype(float)),axis=1)
    means=design.mean(axis=0)
    scales=design.std(axis=0)
    scales=np.where(scales>1e-12,scales,1.0)
    x=np.column_stack((np.ones(len(rows)),(design-means)/scales))
    y=np.eye(5)[labels]
    weights=np.zeros((x.shape[1],5),dtype=float)
    # Conservative fixed-step gradient descent with backtracking-free small steps.
    for _ in range(iterations):
        logits=x@weights
        logits-=logits.max(axis=1,keepdims=True)
        probs=np.exp(logits)
        probs/=probs.sum(axis=1,keepdims=True)
        gradient=(x.T@(probs-y))/len(rows)
        gradient[1:]+=ridge_lambda*weights[1:]/len(rows)
        weights-=0.12*gradient
    return {"medians":medians,"means":means.tolist(),"scales":scales.tolist(),"weights":weights.tolist()}


def minutes_band_logits(model,row):
    raw=np.asarray([optional_number(row.get(name)) for name in FEATURES],dtype=float)
    missing=~np.isfinite(raw)
    imputed=np.where(missing,np.asarray(model["medians"]),raw)
    design=np.concatenate((imputed,missing.astype(float)))
    x=np.concatenate(([1.0],(design-np.asarray(model["means"]))/np.asarray(model["scales"])))
    return x@np.asarray(model["weights"])


def minutes_band_probabilities(model,row,temperature=1.0):
    logits=minutes_band_logits(model,row)/max(0.25,float(temperature))
    logits-=np.max(logits)
    probs=np.exp(logits)
    return probs/probs.sum()


def calibrate_minutes_temperature(model,rows):
    """Select a single temperature on a strictly earlier chronological calibration slice."""
    candidates=np.arange(0.50,2.51,0.05)
    labels=np.asarray([minutes_band(r["actual_minutes"]) for r in rows],dtype=int)
    logits=np.vstack([minutes_band_logits(model,row) for row in rows])
    best=(float("inf"),1.0)
    for temperature in candidates:
        scaled=logits/temperature
        scaled-=scaled.max(axis=1,keepdims=True)
        exp=np.exp(scaled)
        probs=exp/exp.sum(axis=1,keepdims=True)
        score=float(-np.log(np.clip(probs[np.arange(len(labels)),labels],1e-12,1.0)).mean())
        if score<best[0]: best=(score,float(temperature))
    return best[1]


def minutes_distribution_metrics(actual,probabilities):
    labels=np.asarray([minutes_band(v) for v in actual],dtype=int)
    probs=np.asarray(probabilities,dtype=float)
    onehot=np.eye(5)[labels]
    expected=probs@MINUTES_BAND_REPRESENTATIVES
    return {
        "mae":round(mae(actual,expected.tolist()),6),
        "rmse":round(rmse(actual,expected.tolist()),6),
        "multiclass_log_loss":round(float(-np.log(np.clip(probs[np.arange(len(labels)),labels],1e-12,1.0)).mean()),6),
        "multiclass_brier":round(float(((probs-onehot)**2).sum(axis=1).mean()),6),
        "accuracy":round(float((probs.argmax(axis=1)==labels).mean()),6),
    }


def one_hot_minutes_distribution(value):
    p=np.zeros(5,dtype=float)
    p[minutes_band(value)]=1.0
    return p.tolist()


def fit_ridge_fast(rows, target_key, feature_names=FEATURES, ridge_lambda=RIDGE_LAMBDA):
    """NumPy implementation equivalent to the canonical training-only ridge transform."""
    raw=np.asarray([[optional_number(row.get(name)) for name in feature_names] for row in rows],dtype=float)
    targets=np.asarray([optional_number(row.get(target_key)) for row in rows],dtype=float)
    if len(rows)<len(feature_names)+2 or not np.isfinite(targets).all():
        raise ValueError("Insufficient rows or invalid ridge targets")
    medians=[]
    for j,name in enumerate(feature_names):
        observed=raw[np.isfinite(raw[:,j]),j]
        if len(observed)==0:
            raise ValueError(f"Feature has no observed training values: {name}")
        medians.append(float(np.median(observed)))
    missing=~np.isfinite(raw)
    imputed=np.where(missing,np.asarray(medians),raw)
    design=np.concatenate((imputed,missing.astype(float)),axis=1)
    means=design.mean(axis=0)
    scales=design.std(axis=0)
    scales=np.where(scales>1e-12,scales,1.0)
    standardized=(design-means)/scales
    matrix=np.column_stack((np.ones(len(rows)),standardized))
    gram=matrix.T@matrix
    gram[1:,1:]+=ridge_lambda*np.eye(gram.shape[0]-1)
    coefficients=np.linalg.solve(gram,matrix.T@targets)
    design_names=list(feature_names)+[f"{name}__missing" for name in feature_names]
    return {
        "feature_names":design_names,
        "source_feature_names":list(feature_names),
        "imputation_values":medians,
        "missing_value_policy":"TRAINING_MEDIAN_PLUS_MISSINGNESS_INDICATOR",
        "means":means.tolist(),
        "scales":scales.tolist(),
        "coefficients":coefficients.tolist(),
        "ridge_lambda":ridge_lambda,
    }


def score_fold(train, valid, season):
    train_keys=sorted({(r["season"],r["gameweek"]) for r in train})
    if len(train_keys)<10:
        raise ValueError(f"Not enough prior gameweeks to calibrate fold {season}")
    calibration_count=max(1,round(len(train_keys)*0.2))
    calibration_keys=set(train_keys[-calibration_count:])
    appearance_fit=[r for r in train if (r["season"],r["gameweek"]) not in calibration_keys]
    calibration=[r for r in train if (r["season"],r["gameweek"]) in calibration_keys]
    positive_train=[r for r in train if r["appeared"]==1.0]
    calibration_keys_sorted=sorted(calibration_keys)
    appearance_fit_keys=sorted({(r["season"],r["gameweek"]) for r in appearance_fit})

    appearance_model=fit_linear_probability(appearance_fit)
    minutes_band_model=fit_minutes_band_model(appearance_fit)
    minutes_band_temperature=calibrate_minutes_temperature(minutes_band_model,calibration)
    calibration_scores=[predict(appearance_model,r) for r in calibration]
    calibrator=fit_platt(calibration_scores,[r["appeared"] for r in calibration])
    minutes_model=fit_ridge_fast(train,"actual_minutes",FEATURES,RIDGE_LAMBDA)
    conditional_minutes_model=fit_ridge_fast(positive_train,"actual_minutes",FEATURES,RIDGE_LAMBDA)
    # A compact, training-only persistence model tests whether recent minutes alone
    # generalize better than the full feature set for this target.
    lagged_minutes_model=fit_ridge_fast(train,"actual_minutes",MINUTES_BASELINE_FEATURES,RIDGE_LAMBDA)
    conditional_lagged_minutes_model=fit_ridge_fast(positive_train,"actual_minutes",MINUTES_BASELINE_FEATURES,RIDGE_LAMBDA)
    conditional_model=fit_ridge_fast(positive_train,"actual_points",FEATURES,RIDGE_LAMBDA)
    direct_model=fit_ridge_fast(train,"actual_points",FEATURES,RIDGE_LAMBDA)

    actual_points=[]; actual_minutes=[]; actual_appearance=[]
    minutes_band_probabilities_calibrated=[]
    minutes_band_probabilities_raw=[]
    minutes_band_last_gw=[]
    minutes_band_train_prior=[]
    raw_probabilities=[]; calibrated_probabilities=[]; appearance_baseline=[]
    fallback_appearance_rate=sum(r["appeared"] for r in train)/len(train)
    predicted_minutes=[]; predicted_minutes_raw=[]; predicted_minutes_calibrated=[]
    last_minutes=[]; prior3_minutes=[]; prior5_minutes=[]
    lagged_minutes=[]; conditional_lagged_minutes_raw=[]; conditional_lagged_minutes_calibrated=[]
    two_part_raw=[]; two_part_calibrated=[]; band_points_raw=[]; band_points_calibrated=[]; direct_points=[]; last5_points=[]
    for row in valid:
        # All predictions are created before actual labels are read for scoring.
        band_raw=minutes_band_probabilities(minutes_band_model,row)
        band_cal=minutes_band_probabilities(minutes_band_model,row,minutes_band_temperature)
        minutes_band_probabilities_raw.append(band_raw.tolist())
        minutes_band_probabilities_calibrated.append(band_cal.tolist())
        minutes_band_last_gw.append(one_hot_minutes_distribution(row["last_gw_baseline_minutes"]))
        train_band_counts=np.bincount([minutes_band(r["actual_minutes"]) for r in appearance_fit],minlength=5)
        minutes_band_train_prior.append((train_band_counts/train_band_counts.sum()).tolist())
        score=predict(appearance_model,row)
        raw_p=min(1.0,max(0.0,score))
        calibrated_p=calibrated_probability(calibrator,score)
        conditional=max(0.0,predict(conditional_model,row))
        raw_ep=raw_p*conditional
        calibrated_ep=calibrated_p*conditional
        band_ep_raw=(1.0-band_raw[0])*conditional
        band_ep_calibrated=(1.0-band_cal[0])*conditional
        direct_ep=predict(direct_model,row)
        minutes_ep=min(180.0,max(0.0,predict(minutes_model,row)))
        conditional_minutes=min(180.0,max(0.0,predict(conditional_minutes_model,row)))
        expected_minutes_raw=raw_p*conditional_minutes
        expected_minutes_calibrated=calibrated_p*conditional_minutes
        lagged_minutes_ep=min(180.0,max(0.0,predict(lagged_minutes_model,row)))
        conditional_lagged_minutes=min(180.0,max(0.0,predict(conditional_lagged_minutes_model,row)))
        expected_lagged_minutes_raw=raw_p*conditional_lagged_minutes
        expected_lagged_minutes_calibrated=calibrated_p*conditional_lagged_minutes
        baseline_points=row["last5_baseline_points"]
        if baseline_points is None:
            continue
        raw_probabilities.append(raw_p)
        calibrated_probabilities.append(calibrated_p)
        prior_rate=row["prior5_appearance_rate"]
        if prior_rate is None:
            prior_rate=row["season_appearance_rate"]
        if prior_rate is None:
            prior_rate=fallback_appearance_rate
        appearance_baseline.append(min(1.0,max(0.0,prior_rate)))
        predicted_minutes.append(minutes_ep)
        predicted_minutes_raw.append(expected_minutes_raw)
        predicted_minutes_calibrated.append(expected_minutes_calibrated)
        last_minutes.append(row["last_gw_baseline_minutes"])
        prior3_minutes.append(row.get("prior3_gw_minutes_avg"))
        prior5_minutes.append(row.get("prior5_gw_minutes_avg"))
        lagged_minutes.append(lagged_minutes_ep)
        conditional_lagged_minutes_raw.append(expected_lagged_minutes_raw)
        conditional_lagged_minutes_calibrated.append(expected_lagged_minutes_calibrated)
        two_part_raw.append(raw_ep)
        two_part_calibrated.append(calibrated_ep)
        band_points_raw.append(band_ep_raw)
        band_points_calibrated.append(band_ep_calibrated)
        direct_points.append(direct_ep)
        last5_points.append(baseline_points)
        # Labels are appended only after every forecast for this row is fixed.
        actual_points.append(row["actual_points"])
        actual_minutes.append(row["actual_minutes"])
        actual_appearance.append(row["appeared"])

    if not actual_points:
        raise ValueError(f"No scored player-gameweeks in fold {season}")
    def optional_minute_metrics(values):
        return None if any(x is None for x in values) else regression_metrics(actual_minutes,values)
    last_minutes_metrics=optional_minute_metrics(last_minutes)
    prior3_minutes_metrics=optional_minute_metrics(prior3_minutes)
    prior5_minutes_metrics=optional_minute_metrics(prior5_minutes)
    return {
        "season":season,
        "training_seasons":sorted({r["season"] for r in train}),
        "training_player_gameweeks":len(train),
        "appearance_fit_player_gameweeks":len(appearance_fit),
        "calibration_player_gameweeks":len(calibration),
        "calibration_appearance_positive":sum(r["appeared"]==1.0 for r in calibration),
        "calibration_appearance_negative":sum(r["appeared"]==0.0 for r in calibration),
        "calibration_appearance_rate":round(sum(r["appeared"] for r in calibration)/len(calibration),6),
        "appearance_fit_last_gameweek":{"season":appearance_fit_keys[-1][0],"gameweek":appearance_fit_keys[-1][1]},
        "calibration_first_gameweek":{"season":calibration_keys_sorted[0][0],"gameweek":calibration_keys_sorted[0][1]},
        "calibration_last_gameweek":{"season":calibration_keys_sorted[-1][0],"gameweek":calibration_keys_sorted[-1][1]},
        "validation_player_gameweeks":len(actual_points),
        "appearance":{
            "calibrated":binary_metrics(actual_appearance,calibrated_probabilities),
            "raw_clipped":binary_metrics(actual_appearance,raw_probabilities),
            "prior5_rate_baseline":binary_metrics(actual_appearance,appearance_baseline),
        },
        "minutes_bands":{
            "temperature":round(minutes_band_temperature,3),
            "calibrated":minutes_distribution_metrics(actual_minutes,minutes_band_probabilities_calibrated),
            "raw":minutes_distribution_metrics(actual_minutes,minutes_band_probabilities_raw),
            "last_gameweek_one_hot":minutes_distribution_metrics(actual_minutes,minutes_band_last_gw),
            "training_class_prior":minutes_distribution_metrics(actual_minutes,minutes_band_train_prior),
        },
        "minutes":{
            "unconditional_regression":regression_metrics(actual_minutes,predicted_minutes),
            "two_part_calibrated":regression_metrics(actual_minutes,predicted_minutes_calibrated),
            "two_part_raw":regression_metrics(actual_minutes,predicted_minutes_raw),
            "last_gameweek_baseline":last_minutes_metrics,
            "prior3_gameweeks_baseline":prior3_minutes_metrics,
            "prior5_gameweeks_baseline":prior5_minutes_metrics,
            "lagged_feature_ridge":regression_metrics(actual_minutes,lagged_minutes),
            "two_part_lagged_feature_ridge_raw":regression_metrics(actual_minutes,conditional_lagged_minutes_raw),
            "two_part_lagged_feature_ridge_calibrated":regression_metrics(actual_minutes,conditional_lagged_minutes_calibrated),
        },
        "points":{
            "two_part_calibrated":regression_metrics(actual_points,two_part_calibrated),
            "two_part_raw":regression_metrics(actual_points,two_part_raw),
            "minutes_band_raw":regression_metrics(actual_points,band_points_raw),
            "minutes_band_calibrated":regression_metrics(actual_points,band_points_calibrated),
            "direct":regression_metrics(actual_points,direct_points),
            "last5_baseline":regression_metrics(actual_points,last5_points),
        },
    }


def evaluate_walk_forward(rows):
    groups=[r for r in group_player_gameweeks(rows) if r["gameweek"]>1]
    seasons=sorted({r["season"] for r in groups})
    folds=[]
    for index,season in enumerate(seasons):
        if index==0:
            continue
        train=[r for r in groups if r["season"]<season]
        valid=[r for r in groups if r["season"]==season]
        if not train or not valid:
            continue
        folds.append(score_fold(train,valid,season))
    if not folds:
        raise ValueError("No walk-forward folds could be evaluated")

    # Pool fold-level metric values weighted by their validation player-GW counts.
    def weighted_metric(section,key,metric):
        weights=[fold["validation_player_gameweeks"] for fold in folds]
        values=[fold[section][key][metric] for fold in folds]
        if metric=="rmse":
            return round(math.sqrt(sum(w*v*v for w,v in zip(weights,values))/sum(weights)),6)
        return round(sum(w*v for w,v in zip(weights,values))/sum(weights),6)

    pooled={
        "validation_player_gameweeks":sum(f["validation_player_gameweeks"] for f in folds),
        "appearance":{
            model:{
                metric:weighted_metric("appearance",model,metric)
                for metric in ("brier","log_loss")
            }
            for model in ("calibrated","raw_clipped","prior5_rate_baseline")
        },
        "minutes_bands":{
            model:{metric:weighted_metric("minutes_bands",model,metric)
                   for metric in ("mae","rmse","multiclass_log_loss","multiclass_brier","accuracy")}
            for model in ("calibrated","raw","last_gameweek_one_hot","training_class_prior")
        },
        "minutes":{
            "unconditional_regression_mae":weighted_metric("minutes","unconditional_regression","mae"),
            "two_part_calibrated_mae":weighted_metric("minutes","two_part_calibrated","mae"),
            "two_part_raw_mae":weighted_metric("minutes","two_part_raw","mae"),
            "last_gameweek_baseline_mae":weighted_metric("minutes","last_gameweek_baseline","mae")
                if all(f["minutes"]["last_gameweek_baseline"] is not None for f in folds) else None,
            "prior3_gameweeks_baseline_mae":weighted_metric("minutes","prior3_gameweeks_baseline","mae")
                if all(f["minutes"]["prior3_gameweeks_baseline"] is not None for f in folds) else None,
            "prior5_gameweeks_baseline_mae":weighted_metric("minutes","prior5_gameweeks_baseline","mae")
                if all(f["minutes"]["prior5_gameweeks_baseline"] is not None for f in folds) else None,
            "lagged_feature_ridge_mae":weighted_metric("minutes","lagged_feature_ridge","mae"),
            "two_part_lagged_feature_ridge_raw_mae":weighted_metric("minutes","two_part_lagged_feature_ridge_raw","mae"),
            "two_part_lagged_feature_ridge_calibrated_mae":weighted_metric("minutes","two_part_lagged_feature_ridge_calibrated","mae"),
        },
        "points":{
            model:{
                metric:weighted_metric("points",model,metric)
                for metric in ("mae","rmse","mean_error")
            }
            for model in ("two_part_calibrated","two_part_raw","minutes_band_raw","minutes_band_calibrated","direct","last5_baseline")
        },
    }
    return {
        "status":"RESEARCH_ONLY",
        "decision":"DO_NOT_PROMOTE",
        "point_in_time_status":"NOT_VERIFIED_RETROSPECTIVE_SOURCE_VINTAGES",
        "validation_design":"Expanding season walk-forward: each season is tested only on models trained on earlier seasons; appearance calibration uses only a later chronological slice within the prior-season training history.",
        "unit":"player_gameweek; double-gameweek labels summed before evaluation",
        "fold_count":len(folds),
        "folds":folds,
        "pooled_weighted_metrics":pooled,
        "leakage_controls":[
            "No validation season contributes to model fitting or calibration for its own fold.",
            "All feature values are lagged; target fixture statistics are excluded.",
            "Actual minutes and points are labels only and are never used to select forecast rows.",
            "Calibration data are chronologically earlier than each validation season.",
        ],
        "limitations":[
            "Historical source files are retrospective exports, not verified pre-deadline snapshots.",
            "Season-level fold performance may reflect changes in FPL scoring, squads and competition structure.",
            "The model is still a research candidate and is not connected to recommendation decisions.",
        ],
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    with args.input.open(newline="",encoding="utf-8-sig") as handle:
        rows=list(csv.DictReader(handle))
    report=evaluate_walk_forward(rows)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
