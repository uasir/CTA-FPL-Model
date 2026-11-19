#!/usr/bin/env python3
"""Expanding-season walk-forward validation for the two-part FPL predictor."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

from evaluate_fpl_two_part_model import (
    FEATURES, RIDGE_LAMBDA, binary_metrics, calibrated_probability,
    fit_linear_probability, fit_platt, group_player_gameweeks,
    regression_metrics,
)
from train_fpl_exploratory_ridge import fit_ridge, predict, mae, rmse


def score_fold(train, valid, season):
    train_keys=sorted({(r["season"],r["gameweek"]) for r in train})
    if len(train_keys)<10:
        raise ValueError(f"Not enough prior gameweeks to calibrate fold {season}")
    calibration_count=max(1,round(len(train_keys)*0.2))
    calibration_keys=set(train_keys[-calibration_count:])
    appearance_fit=[r for r in train if (r["season"],r["gameweek"]) not in calibration_keys]
    calibration=[r for r in train if (r["season"],r["gameweek"]) in calibration_keys]
    positive_train=[r for r in train if r["appeared"]==1.0]

    appearance_model=fit_linear_probability(appearance_fit)
    calibration_scores=[predict(appearance_model,r) for r in calibration]
    calibrator=fit_platt(calibration_scores,[r["appeared"] for r in calibration])
    minutes_model=fit_ridge(train,"actual_minutes",FEATURES,RIDGE_LAMBDA)
    conditional_model=fit_ridge(positive_train,"actual_points",FEATURES,RIDGE_LAMBDA)
    direct_model=fit_ridge(train,"actual_points",FEATURES,RIDGE_LAMBDA)

    actual_points=[]; actual_minutes=[]; actual_appearance=[]
    raw_probabilities=[]; calibrated_probabilities=[]; appearance_baseline=[]
    fallback_appearance_rate=sum(r["appeared"] for r in train)/len(train)
    predicted_minutes=[]; last_minutes=[]
    two_part_raw=[]; two_part_calibrated=[]; direct_points=[]; last5_points=[]
    for row in valid:
        # All predictions are created before actual labels are read for scoring.
        score=predict(appearance_model,row)
        raw_p=min(1.0,max(0.0,score))
        calibrated_p=calibrated_probability(calibrator,score)
        conditional=max(0.0,predict(conditional_model,row))
        raw_ep=raw_p*conditional
        calibrated_ep=calibrated_p*conditional
        direct_ep=predict(direct_model,row)
        minutes_ep=min(180.0,max(0.0,predict(minutes_model,row)))
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
        last_minutes.append(row["last_gw_baseline_minutes"])
        two_part_raw.append(raw_ep)
        two_part_calibrated.append(calibrated_ep)
        direct_points.append(direct_ep)
        last5_points.append(baseline_points)
        # Labels are appended only after every forecast for this row is fixed.
        actual_points.append(row["actual_points"])
        actual_minutes.append(row["actual_minutes"])
        actual_appearance.append(row["appeared"])

    if not actual_points:
        raise ValueError(f"No scored player-gameweeks in fold {season}")
    if any(x is None for x in last_minutes):
        last_minutes_metrics=None
    else:
        last_minutes_metrics=regression_metrics(actual_minutes,last_minutes)
    return {
        "season":season,
        "training_seasons":sorted({r["season"] for r in train}),
        "training_player_gameweeks":len(train),
        "appearance_fit_player_gameweeks":len(appearance_fit),
        "calibration_player_gameweeks":len(calibration),
        "validation_player_gameweeks":len(actual_points),
        "appearance":{
            "calibrated":binary_metrics(actual_appearance,calibrated_probabilities),
            "raw_clipped":binary_metrics(actual_appearance,raw_probabilities),
            "prior5_rate_baseline":binary_metrics(actual_appearance,appearance_baseline),
        },
        "minutes":{
            "model":regression_metrics(actual_minutes,predicted_minutes),
            "last_gameweek_baseline":last_minutes_metrics,
        },
        "points":{
            "two_part_calibrated":regression_metrics(actual_points,two_part_calibrated),
            "two_part_raw":regression_metrics(actual_points,two_part_raw),
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

    def pool(section, key):
        values=[fold[section][key] for fold in folds]
        return values

    # Pool fold-level metric values weighted by their validation player-GW counts.
    def weighted_metric(section,key,metric):
        weights=[fold["validation_player_gameweeks"] for fold in folds]
        values=[fold[section][key][metric] for fold in folds]
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
        "minutes":{
            "model_mae":weighted_metric("minutes","model","mae"),
            "last_gameweek_baseline_mae":weighted_metric("minutes","last_gameweek_baseline","mae")
                if all(f["minutes"]["last_gameweek_baseline"] is not None for f in folds) else None,
        },
        "points":{
            model:{
                metric:weighted_metric("points",model,metric)
                for metric in ("mae","rmse","mean_error")
            }
            for model in ("two_part_calibrated","two_part_raw","direct","last5_baseline")
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
