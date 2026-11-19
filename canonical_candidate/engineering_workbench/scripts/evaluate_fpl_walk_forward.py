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

POINTS_BAND_FALLBACK_REPRESENTATIVES = np.asarray((-1.0, 0.0, 1.5, 4.0, 7.5, 10.0))


def points_band(points):
    value=float(points)
    if value < 0: return 0
    if value == 0: return 1
    if value < 3: return 2
    if value < 6: return 3
    if value < 10: return 4
    return 5


def fit_points_band_model(rows, ridge_lambda=2.0, iterations=220):
    """Fit a six-class points distribution with training-only preprocessing."""
    raw=np.asarray([[optional_number(row.get(name)) for name in FEATURES] for row in rows],dtype=float)
    labels=np.asarray([points_band(row["actual_points"]) for row in rows],dtype=int)
    if len(rows)<len(FEATURES)+10 or len(set(labels))<2:
        raise ValueError("Insufficient rows or class diversity for points-band model")
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
    y=np.eye(6)[labels]
    weights=np.zeros((x.shape[1],6),dtype=float)
    for _ in range(iterations):
        logits=x@weights
        logits-=logits.max(axis=1,keepdims=True)
        probs=np.exp(logits)
        probs/=probs.sum(axis=1,keepdims=True)
        gradient=(x.T@(probs-y))/len(rows)
        gradient[1:]+=ridge_lambda*weights[1:]/len(rows)
        weights-=0.12*gradient
    return {"medians":medians,"means":means.tolist(),"scales":scales.tolist(),"weights":weights.tolist()}


def points_band_logits(model,row):
    raw=np.asarray([optional_number(row.get(name)) for name in FEATURES],dtype=float)
    missing=~np.isfinite(raw)
    imputed=np.where(missing,np.asarray(model["medians"]),raw)
    design=np.concatenate((imputed,missing.astype(float)))
    x=np.concatenate(([1.0],(design-np.asarray(model["means"]))/np.asarray(model["scales"])))
    return x@np.asarray(model["weights"])


def points_band_probabilities(model,row,temperature=1.0):
    logits=points_band_logits(model,row)/max(0.25,float(temperature))
    logits-=np.max(logits)
    probs=np.exp(logits)
    return probs/probs.sum()


def fit_points_band_representatives(rows):
    """Estimate each points band's mean from training rows only."""
    values=[[] for _ in range(6)]
    for row in rows:
        values[points_band(row["actual_points"])].append(float(row["actual_points"]))
    return np.asarray([
        float(np.mean(group)) if group else float(POINTS_BAND_FALLBACK_REPRESENTATIVES[i])
        for i,group in enumerate(values)
    ],dtype=float)


def calibrate_points_temperature(model,rows):
    """Select temperature on a later chronological slice, never on validation outcomes."""
    candidates=np.arange(0.50,2.51,0.05)
    labels=np.asarray([points_band(r["actual_points"]) for r in rows],dtype=int)
    logits=np.vstack([points_band_logits(model,row) for row in rows])
    best=(float("inf"),1.0)
    for temperature in candidates:
        scaled=logits/temperature
        scaled-=scaled.max(axis=1,keepdims=True)
        exp=np.exp(scaled)
        probs=exp/exp.sum(axis=1,keepdims=True)
        score=float(-np.log(np.clip(probs[np.arange(len(labels)),labels],1e-12,1.0)).mean())
        if score<best[0]: best=(score,float(temperature))
    return best[1]


def combine_appearance_points_distribution(appearance_probability, conditional_points_probabilities):
    """Place non-appearance probability in the zero-points class."""
    p=min(1.0,max(0.0,float(appearance_probability)))
    conditional=np.asarray(conditional_points_probabilities,dtype=float)
    if conditional.shape != (6,):
        raise ValueError("Conditional points distribution must contain six classes")
    combined=p*conditional
    combined[1]+=1.0-p
    combined/=combined.sum()
    return combined


def paired_error_comparison(actual,candidate,comparator,groups=None):
    """Aggregate paired point-forecast errors without retaining player-level outputs."""
    y=np.asarray(actual,dtype=float)
    a=np.asarray(candidate,dtype=float)
    b=np.asarray(comparator,dtype=float)
    if not (len(y)==len(a)==len(b)) or len(y)==0:
        raise ValueError("Paired forecast arrays must be non-empty and aligned")
    ae=np.abs(a-y); be=np.abs(b-y)
    sq_delta=(a-y)**2-(b-y)**2
    result={
        "n":int(len(y)),
        "mean_absolute_error_delta":round(float((ae-be).mean()),6),
        "mean_squared_error_delta":round(float(sq_delta.mean()),6),
        "candidate_absolute_error_win_rate":round(float((ae<be).mean()),6),
        "absolute_error_tie_rate":round(float(np.isclose(ae,be,atol=1e-12).mean()),6),
    }
    if groups is not None:
        labels=np.asarray(groups,dtype=object)
        if len(labels)!=len(y):
            raise ValueError("Paired forecast group labels must align with outcomes")
        result["by_group"]={}
        for group in sorted(set(labels.tolist())):
            mask=labels==group
            if mask.any():
                item=paired_error_comparison(y[mask],a[mask],b[mask])
                result["by_group"][str(group)]=item
    return result



def cluster_bootstrap_paired_errors(actual,candidate,comparator,cluster_ids,n_boot=1000,seed=20261119):
    """Player-season cluster bootstrap for paired forecast-error differences."""
    y=np.asarray(actual,dtype=float)
    a=np.asarray(candidate,dtype=float)
    b=np.asarray(comparator,dtype=float)
    clusters=np.asarray(cluster_ids,dtype=object)
    if not (len(y)==len(a)==len(b)==len(clusters)) or len(y)==0:
        raise ValueError("Cluster-bootstrap inputs must be non-empty and aligned")
    _,inverse=np.unique(clusters,return_inverse=True)
    cluster_count=int(inverse.max())+1
    if cluster_count<2:
        raise ValueError("At least two player-season clusters are required")
    candidate_abs=np.abs(a-y)
    comparator_abs=np.abs(b-y)
    counts=np.bincount(inverse,minlength=cluster_count).astype(float)
    mae_sums=np.bincount(inverse,weights=candidate_abs-comparator_abs,minlength=cluster_count)
    mse_sums=np.bincount(inverse,weights=(a-y)**2-(b-y)**2,minlength=cluster_count)
    win_sums=np.bincount(inverse,weights=(candidate_abs<comparator_abs).astype(float),minlength=cluster_count)
    rng=np.random.default_rng(seed)
    samples=np.empty((n_boot,3),dtype=float)
    for index in range(n_boot):
        draw=rng.integers(0,cluster_count,size=cluster_count)
        multiplicity=np.bincount(draw,minlength=cluster_count)
        denominator=float(multiplicity@counts)
        samples[index,0]=float(multiplicity@mae_sums)/denominator
        samples[index,1]=float(multiplicity@mse_sums)/denominator
        samples[index,2]=float(multiplicity@win_sums)/denominator
    intervals=np.quantile(samples,[0.025,0.975],axis=0)
    return {
        "method":"PLAYER_SEASON_CLUSTER_BOOTSTRAP",
        "clusters":cluster_count,
        "replicates":int(n_boot),
        "mean_absolute_error_delta_ci95":[round(float(v),6) for v in intervals[:,0]],
        "mean_squared_error_delta_ci95":[round(float(v),6) for v in intervals[:,1]],
        "candidate_absolute_error_win_rate_ci95":[round(float(v),6) for v in intervals[:,2]],
    }

def appearance_probability_bucket(probability):
    value=float(probability)
    if value<0.5: return "low_<0.50"
    if value<0.8: return "medium_0.50_to_0.80"
    return "high_>=0.80"


def blend_expected_points(hurdle, two_part, hurdle_weight):
    weight=float(hurdle_weight)
    if not 0.0<=weight<=1.0:
        raise ValueError("Hurdle blend weight must be between zero and one")
    return weight*float(hurdle)+(1.0-weight)*float(two_part)


def select_blend_weight(actual, hurdle, two_part, objective="mae"):
    """Select a convex blend weight on a separate earlier calibration-selection slice."""
    y=np.asarray(actual,dtype=float)
    h=np.asarray(hurdle,dtype=float)
    t=np.asarray(two_part,dtype=float)
    if len(y)==0 or not (len(y)==len(h)==len(t)):
        raise ValueError("Blend-selection inputs must be non-empty and aligned")
    if objective not in ("mae","mse"):
        raise ValueError("Blend objective must be mae or mse")
    weights=np.arange(0.0,1.0001,0.05)
    def loss(weight):
        prediction=weight*h+(1.0-weight)*t
        error=prediction-y
        return float(np.abs(error).mean() if objective=="mae" else np.square(error).mean())
    return float(min(weights,key=lambda weight:(loss(weight),float(weight))))


def points_distribution_metrics(actual,probabilities,representatives=None):
    labels=np.asarray([points_band(v) for v in actual],dtype=int)
    probs=np.asarray(probabilities,dtype=float)
    onehot=np.eye(6)[labels]
    reps=POINTS_BAND_FALLBACK_REPRESENTATIVES if representatives is None else np.asarray(representatives,dtype=float)
    expected=probs@reps
    cumulative=np.cumsum(probs,axis=1)[:,:-1]
    observed_cumulative=np.cumsum(onehot,axis=1)[:,:-1]
    return {
        "expected_points_mae":round(mae(actual,expected.tolist()),6),
        "expected_points_rmse":round(rmse(actual,expected.tolist()),6),
        "multiclass_log_loss":round(float(-np.log(np.clip(probs[np.arange(len(labels)),labels],1e-12,1.0)).mean()),6),
        "multiclass_brier":round(float(((probs-onehot)**2).sum(axis=1).mean()),6),
        "ranked_probability_score":round(float(((cumulative-observed_cumulative)**2).sum(axis=1).mean()),6),
        "accuracy":round(float((probs.argmax(axis=1)==labels).mean()),6),
    }



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


def fit_minutes_band_representatives(rows):
    """Estimate each class's mean minutes from training rows only."""
    values=[[] for _ in range(5)]
    for row in rows:
        minutes=float(row["actual_minutes"])
        values[minutes_band(minutes)].append(minutes)
    return np.asarray([
        float(np.mean(group)) if group else float(MINUTES_BAND_REPRESENTATIVES[i])
        for i,group in enumerate(values)
    ],dtype=float)


def minutes_distribution_metrics(actual,probabilities,representatives=None):
    labels=np.asarray([minutes_band(v) for v in actual],dtype=int)
    probs=np.asarray(probabilities,dtype=float)
    onehot=np.eye(5)[labels]
    reps=MINUTES_BAND_REPRESENTATIVES if representatives is None else np.asarray(representatives,dtype=float)
    expected=probs@reps
    return {
        "mae":round(mae(actual,expected.tolist()),6),
        "rmse":round(rmse(actual,expected.tolist()),6),
        "multiclass_log_loss":round(float(-np.log(np.clip(probs[np.arange(len(labels)),labels],1e-12,1.0)).mean()),6),
        "multiclass_brier":round(float(((probs-onehot)**2).sum(axis=1).mean()),6),
        "accuracy":round(float((probs.argmax(axis=1)==labels).mean()),6),
    }


def one_hot_minutes_distribution(value, fallback=None):
    """Use last-GW one-hot when history exists; otherwise use training-only class prior."""
    if value is None:
        if fallback is None:
            raise ValueError("Missing last-GW minutes requires a training-only fallback")
        return np.asarray(fallback,dtype=float).tolist()
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
    minutes_band_representatives=fit_minutes_band_representatives(appearance_fit)
    points_band_model=fit_points_band_model(appearance_fit)
    points_band_temperature=calibrate_points_temperature(points_band_model,calibration)
    points_band_representatives=fit_points_band_representatives(appearance_fit)
    # Fit conditional points only on the earlier appearance-fit slice.
    positive_appearance_fit=[r for r in appearance_fit if r["appeared"]==1.0]
    positive_calibration=[r for r in calibration if r["appeared"]==1.0]
    conditional_points_band_model=fit_points_band_model(positive_appearance_fit)
    conditional_points_band_temperature=calibrate_points_temperature(conditional_points_band_model,positive_calibration)
    conditional_points_band_representatives=fit_points_band_representatives(positive_appearance_fit)
    calibration_scores=[predict(appearance_model,r) for r in calibration]
    calibrator=fit_platt(calibration_scores,[r["appeared"] for r in calibration])
    # Reserve a later slice of the pre-validation calibration period solely for
    # blend-weight selection. Calibrators used for that selection see only the
    # earlier slice; validation calibrators below still use the full calibration set.
    blend_calibration_keys=sorted({(r["season"],r["gameweek"]) for r in calibration})
    blend_fit_count=max(1,int(round(len(blend_calibration_keys)*0.6)))
    blend_fit_keys=set(blend_calibration_keys[:blend_fit_count])
    blend_calibration_fit=[r for r in calibration if (r["season"],r["gameweek"]) in blend_fit_keys]
    blend_selection=[r for r in calibration if (r["season"],r["gameweek"]) not in blend_fit_keys]
    if not blend_selection:
        raise ValueError(f"Insufficient calibration rows for independent blend selection in {season}")
    blend_scores=[predict(appearance_model,r) for r in blend_calibration_fit]
    blend_calibrator=fit_platt(blend_scores,[r["appeared"] for r in blend_calibration_fit])
    blend_positive_calibration=[r for r in blend_calibration_fit if r["appeared"]==1.0]
    if len(blend_positive_calibration)<10:
        raise ValueError(f"Insufficient appeared calibration rows for blend selection in {season}")
    blend_conditional_temperature=calibrate_points_temperature(conditional_points_band_model,blend_positive_calibration)
    # The selection-slice comparator must also be trained without selection labels.
    blend_conditional_model=fit_ridge_fast(positive_appearance_fit,"actual_points",FEATURES,RIDGE_LAMBDA)
    conditional_model=fit_ridge_fast(positive_train,"actual_points",FEATURES,RIDGE_LAMBDA)
    blend_selection_actual=[]; blend_selection_hurdle=[]; blend_selection_two_part=[]
    for row in blend_selection:
        if row["last5_baseline_points"] is None:
            continue
        score=predict(appearance_model,row)
        p=calibrated_probability(blend_calibrator,score)
        conditional_probs=points_band_probabilities(conditional_points_band_model,row,blend_conditional_temperature)
        distribution=combine_appearance_points_distribution(p,conditional_probs)
        hurdle_ep=float(distribution@conditional_points_band_representatives)
        raw_p=min(1.0,max(0.0,score))
        conditional_ep=max(0.0,predict(blend_conditional_model,row))
        blend_selection_hurdle.append(hurdle_ep)
        blend_selection_two_part.append(raw_p*conditional_ep)
        blend_selection_actual.append(row["actual_points"])
    blend_weight_mae=select_blend_weight(blend_selection_actual,blend_selection_hurdle,blend_selection_two_part,"mae")
    blend_weight_mse=select_blend_weight(blend_selection_actual,blend_selection_hurdle,blend_selection_two_part,"mse")
    minutes_model=fit_ridge_fast(train,"actual_minutes",FEATURES,RIDGE_LAMBDA)
    conditional_minutes_model=fit_ridge_fast(positive_train,"actual_minutes",FEATURES,RIDGE_LAMBDA)
    # A compact, training-only persistence model tests whether recent minutes alone
    # generalize better than the full feature set for this target.
    lagged_minutes_model=fit_ridge_fast(train,"actual_minutes",MINUTES_BASELINE_FEATURES,RIDGE_LAMBDA)
    conditional_lagged_minutes_model=fit_ridge_fast(positive_train,"actual_minutes",MINUTES_BASELINE_FEATURES,RIDGE_LAMBDA)
    direct_model=fit_ridge_fast(train,"actual_points",FEATURES,RIDGE_LAMBDA)

    actual_points=[]; actual_minutes=[]; actual_appearance=[]
    minutes_band_probabilities_calibrated=[]
    minutes_band_probabilities_raw=[]
    minutes_band_last_gw=[]
    minutes_band_train_prior=[]
    points_band_probabilities_calibrated=[]
    points_band_probabilities_raw=[]
    points_band_train_prior=[]
    hurdle_points_probabilities_raw=[]
    hurdle_points_probabilities_calibrated=[]
    raw_probabilities=[]; calibrated_probabilities=[]; appearance_baseline=[]
    fallback_appearance_rate=sum(r["appeared"] for r in train)/len(train)
    train_band_counts=np.bincount([minutes_band(r["actual_minutes"]) for r in appearance_fit],minlength=5)
    train_band_prior=(train_band_counts/train_band_counts.sum()).tolist()
    train_points_counts=np.bincount([points_band(r["actual_points"]) for r in appearance_fit],minlength=6)
    train_points_prior=(train_points_counts/train_points_counts.sum()).tolist()
    predicted_minutes=[]; predicted_minutes_raw=[]; predicted_minutes_calibrated=[]
    last_minutes=[]; prior3_minutes=[]; prior5_minutes=[]
    lagged_minutes=[]; conditional_lagged_minutes_raw=[]; conditional_lagged_minutes_calibrated=[]
    two_part_raw=[]; two_part_calibrated=[]; band_points_raw=[]; band_points_calibrated=[]; direct_points=[]; last5_points=[]
    hurdle_points_raw_expected=[]; hurdle_points_calibrated_expected=[]; calibrated_appearance_buckets=[]
    blend_points_025=[]; blend_points_050=[]; blend_points_075=[]
    blend_points_selected_mae=[]; blend_points_selected_mse=[]
    player_season_clusters=[]
    for row in valid:
        # All predictions are created before actual labels are read for scoring.
        band_raw=minutes_band_probabilities(minutes_band_model,row)
        band_cal=minutes_band_probabilities(minutes_band_model,row,minutes_band_temperature)
        points_raw=points_band_probabilities(points_band_model,row)
        points_cal=points_band_probabilities(points_band_model,row,points_band_temperature)
        conditional_hurdle_raw=points_band_probabilities(conditional_points_band_model,row)
        conditional_hurdle_cal=points_band_probabilities(conditional_points_band_model,row,conditional_points_band_temperature)
        score=predict(appearance_model,row)
        raw_p=min(1.0,max(0.0,score))
        calibrated_p=calibrated_probability(calibrator,score)
        hurdle_raw=combine_appearance_points_distribution(raw_p,conditional_hurdle_raw)
        hurdle_cal=combine_appearance_points_distribution(calibrated_p,conditional_hurdle_cal)
        hurdle_raw_ep=float(hurdle_raw@conditional_points_band_representatives)
        hurdle_cal_ep=float(hurdle_cal@conditional_points_band_representatives)
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
        # Keep every metric on the same scored validation cohort.
        blend_points_025.append(blend_expected_points(hurdle_cal_ep,raw_ep,0.25))
        blend_points_050.append(blend_expected_points(hurdle_cal_ep,raw_ep,0.50))
        blend_points_075.append(blend_expected_points(hurdle_cal_ep,raw_ep,0.75))
        blend_points_selected_mae.append(blend_expected_points(hurdle_cal_ep,raw_ep,blend_weight_mae))
        blend_points_selected_mse.append(blend_expected_points(hurdle_cal_ep,raw_ep,blend_weight_mse))
        minutes_band_probabilities_raw.append(band_raw.tolist())
        points_band_probabilities_raw.append(points_raw.tolist())
        points_band_probabilities_calibrated.append(points_cal.tolist())
        points_band_train_prior.append(train_points_prior)
        hurdle_points_probabilities_raw.append(hurdle_raw.tolist())
        hurdle_points_probabilities_calibrated.append(hurdle_cal.tolist())
        minutes_band_probabilities_calibrated.append(band_cal.tolist())
        minutes_band_last_gw.append(one_hot_minutes_distribution(row["last_gw_baseline_minutes"],train_band_prior))
        minutes_band_train_prior.append(train_band_prior)
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
        hurdle_points_raw_expected.append(hurdle_raw_ep)
        hurdle_points_calibrated_expected.append(hurdle_cal_ep)
        calibrated_appearance_buckets.append(appearance_probability_bucket(calibrated_p))
        # Labels are appended only after every forecast for this row is fixed.
        actual_points.append(row["actual_points"])
        actual_minutes.append(row["actual_minutes"])
        actual_appearance.append(row["appeared"])
        player_season_clusters.append(f"{row['season']}::{row['fpl_element_id']}")

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
        "blend_selection_player_gameweeks":len(blend_selection_actual),
        "blend_selected_weights":{"mae":round(blend_weight_mae,3),"mse":round(blend_weight_mse,3)},
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
        "points_bands":{
            "temperature":round(points_band_temperature,3),
            "training_mean_representatives":points_band_representatives.tolist(),
            "calibrated":points_distribution_metrics(actual_points,points_band_probabilities_calibrated,points_band_representatives),
            "raw":points_distribution_metrics(actual_points,points_band_probabilities_raw,points_band_representatives),
            "training_class_prior":points_distribution_metrics(actual_points,points_band_train_prior,points_band_representatives),
        },
        "appearance_hurdle_points_bands":{
            "conditional_temperature":round(conditional_points_band_temperature,3),
            "conditional_training_mean_representatives":conditional_points_band_representatives.tolist(),
            "raw_appearance_probability":points_distribution_metrics(actual_points,hurdle_points_probabilities_raw,conditional_points_band_representatives),
            "calibrated_appearance_probability":points_distribution_metrics(actual_points,hurdle_points_probabilities_calibrated,conditional_points_band_representatives),
        },
        "minutes_bands":{
            "temperature":round(minutes_band_temperature,3),
            "training_mean_representatives":minutes_band_representatives.tolist(),
            "calibrated":minutes_distribution_metrics(actual_minutes,minutes_band_probabilities_calibrated,minutes_band_representatives),
            "raw":minutes_distribution_metrics(actual_minutes,minutes_band_probabilities_raw,minutes_band_representatives),
            "fixed_midpoint_calibrated":minutes_distribution_metrics(actual_minutes,minutes_band_probabilities_calibrated),
            "fixed_midpoint_raw":minutes_distribution_metrics(actual_minutes,minutes_band_probabilities_raw),
            "last_gameweek_or_training_prior":minutes_distribution_metrics(actual_minutes,minutes_band_last_gw,minutes_band_representatives),
            "training_class_prior":minutes_distribution_metrics(actual_minutes,minutes_band_train_prior,minutes_band_representatives),
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
        "_bootstrap_inputs":{
            "actual":actual_points,
            "hurdle_calibrated":hurdle_points_calibrated_expected,
            "two_part_raw":two_part_raw,
            "direct_ridge":direct_points,
            "blend_half":blend_points_050,
            "blend_selected_mae":blend_points_selected_mae,
            "blend_selected_mse":blend_points_selected_mse,
            "player_season_clusters":player_season_clusters,
        },
        "paired_points_errors":{
            "calibrated_hurdle_vs_two_part_raw":paired_error_comparison(actual_points,hurdle_points_calibrated_expected,two_part_raw),
            "calibrated_hurdle_vs_two_part_calibrated":paired_error_comparison(actual_points,hurdle_points_calibrated_expected,two_part_calibrated),
            "calibrated_hurdle_vs_direct_ridge":paired_error_comparison(actual_points,hurdle_points_calibrated_expected,direct_points),
            "calibrated_hurdle_vs_last5":paired_error_comparison(actual_points,hurdle_points_calibrated_expected,last5_points),
            "raw_hurdle_vs_two_part_raw":paired_error_comparison(actual_points,hurdle_points_raw_expected,two_part_raw),
            "blend_half_vs_two_part_raw":paired_error_comparison(actual_points,blend_points_050,two_part_raw),
            "blend_selected_mae_vs_two_part_raw":paired_error_comparison(actual_points,blend_points_selected_mae,two_part_raw),
            "blend_selected_mse_vs_two_part_raw":paired_error_comparison(actual_points,blend_points_selected_mse,two_part_raw),
            "calibrated_hurdle_vs_two_part_raw_by_appearance_probability":paired_error_comparison(actual_points,hurdle_points_calibrated_expected,two_part_raw,calibrated_appearance_buckets)["by_group"],
        },
        "points":{
            "two_part_calibrated":regression_metrics(actual_points,two_part_calibrated),
            "two_part_raw":regression_metrics(actual_points,two_part_raw),
            "minutes_band_raw":regression_metrics(actual_points,band_points_raw),
            "minutes_band_calibrated":regression_metrics(actual_points,band_points_calibrated),
            "direct":regression_metrics(actual_points,direct_points),
            "last5_baseline":regression_metrics(actual_points,last5_points),
            "blend_hurdle_025":regression_metrics(actual_points,blend_points_025),
            "blend_hurdle_050":regression_metrics(actual_points,blend_points_050),
            "blend_hurdle_075":regression_metrics(actual_points,blend_points_075),
            "blend_selected_mae":regression_metrics(actual_points,blend_points_selected_mae),
            "blend_selected_mse":regression_metrics(actual_points,blend_points_selected_mse),
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

    # Keep player-level cluster keys and errors runner-local; publish only aggregate intervals.
    pooled_bootstrap_inputs=[]
    for fold_index,fold in enumerate(folds):
        inputs=fold.pop("_bootstrap_inputs")
        pooled_bootstrap_inputs.append(inputs)
        fold["paired_points_errors"]["calibrated_hurdle_vs_two_part_raw"]["cluster_bootstrap_95ci"]=cluster_bootstrap_paired_errors(
            inputs["actual"],inputs["hurdle_calibrated"],inputs["two_part_raw"],
            inputs["player_season_clusters"],seed=20261119+fold_index)
        fold["paired_points_errors"]["calibrated_hurdle_vs_direct_ridge"]["cluster_bootstrap_95ci"]=cluster_bootstrap_paired_errors(
            inputs["actual"],inputs["hurdle_calibrated"],inputs["direct_ridge"],
            inputs["player_season_clusters"],seed=20262119+fold_index)
    pooled_actual=[v for item in pooled_bootstrap_inputs for v in item["actual"]]
    pooled_hurdle=[v for item in pooled_bootstrap_inputs for v in item["hurdle_calibrated"]]
    pooled_two_part=[v for item in pooled_bootstrap_inputs for v in item["two_part_raw"]]
    pooled_ridge=[v for item in pooled_bootstrap_inputs for v in item["direct_ridge"]]
    pooled_blend_half=[v for item in pooled_bootstrap_inputs for v in item["blend_half"]]
    pooled_blend_selected_mae=[v for item in pooled_bootstrap_inputs for v in item["blend_selected_mae"]]
    pooled_blend_selected_mse=[v for item in pooled_bootstrap_inputs for v in item["blend_selected_mse"]]
    pooled_clusters=[v for item in pooled_bootstrap_inputs for v in item["player_season_clusters"]]

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
        "points_bands":{
            model:{metric:weighted_metric("points_bands",model,metric)
                   for metric in ("expected_points_mae","expected_points_rmse","multiclass_log_loss","multiclass_brier","ranked_probability_score","accuracy")}
            for model in ("calibrated","raw","training_class_prior")
        },
        "appearance_hurdle_points_bands":{
            model:{metric:weighted_metric("appearance_hurdle_points_bands",model,metric)
                   for metric in ("expected_points_mae","expected_points_rmse","multiclass_log_loss","multiclass_brier","ranked_probability_score","accuracy")}
            for model in ("raw_appearance_probability","calibrated_appearance_probability")
        },
        "minutes_bands":{
            model:{metric:weighted_metric("minutes_bands",model,metric)
                   for metric in ("mae","rmse","multiclass_log_loss","multiclass_brier","accuracy")}
            for model in ("calibrated","raw","fixed_midpoint_calibrated","fixed_midpoint_raw","last_gameweek_or_training_prior","training_class_prior")
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
            for model in ("two_part_calibrated","two_part_raw","minutes_band_raw","minutes_band_calibrated","direct","last5_baseline","blend_hurdle_025","blend_hurdle_050","blend_hurdle_075","blend_selected_mae","blend_selected_mse")
        },
        "paired_points_errors":{
            key:{
                metric:round(sum(f["validation_player_gameweeks"]*f["paired_points_errors"][key][metric] for f in folds)/sum(f["validation_player_gameweeks"] for f in folds),6)
                for metric in ("mean_absolute_error_delta","mean_squared_error_delta","candidate_absolute_error_win_rate","absolute_error_tie_rate")
            } | {"n":sum(f["paired_points_errors"][key]["n"] for f in folds)}
            for key in ("calibrated_hurdle_vs_two_part_raw","calibrated_hurdle_vs_two_part_calibrated","calibrated_hurdle_vs_direct_ridge","calibrated_hurdle_vs_last5","raw_hurdle_vs_two_part_raw","blend_half_vs_two_part_raw","blend_selected_mae_vs_two_part_raw","blend_selected_mse_vs_two_part_raw")
        },
    }
    pooled["paired_points_errors"]["calibrated_hurdle_vs_two_part_raw"]["cluster_bootstrap_95ci"]=cluster_bootstrap_paired_errors(
        pooled_actual,pooled_hurdle,pooled_two_part,pooled_clusters,seed=20263119)
    pooled["paired_points_errors"]["calibrated_hurdle_vs_direct_ridge"]["cluster_bootstrap_95ci"]=cluster_bootstrap_paired_errors(
        pooled_actual,pooled_hurdle,pooled_ridge,pooled_clusters,seed=20264119)
    pooled["paired_points_errors"]["blend_half_vs_two_part_raw"]["cluster_bootstrap_95ci"]=cluster_bootstrap_paired_errors(
        pooled_actual,pooled_blend_half,pooled_two_part,pooled_clusters,seed=20265119)
    pooled["paired_points_errors"]["blend_selected_mae_vs_two_part_raw"]["cluster_bootstrap_95ci"]=cluster_bootstrap_paired_errors(
        pooled_actual,pooled_blend_selected_mae,pooled_two_part,pooled_clusters,seed=20266119)
    pooled["paired_points_errors"]["blend_selected_mse_vs_two_part_raw"]["cluster_bootstrap_95ci"]=cluster_bootstrap_paired_errors(
        pooled_actual,pooled_blend_selected_mse,pooled_two_part,pooled_clusters,seed=20267119)
    pooled["blend_selected_weights"]={
        "mae_mean":round(float(np.mean([f["blend_selected_weights"]["mae"] for f in folds])),3),
        "mse_mean":round(float(np.mean([f["blend_selected_weights"]["mse"] for f in folds])),3),
        "mae_by_season":{f["season"]:f["blend_selected_weights"]["mae"] for f in folds},
        "mse_by_season":{f["season"]:f["blend_selected_weights"]["mse"] for f in folds},
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
            "Blend weights are selected on a later calibration-selection slice that is separate from the slice used to fit blend-specific calibrators; neither slice includes validation outcomes.",
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
