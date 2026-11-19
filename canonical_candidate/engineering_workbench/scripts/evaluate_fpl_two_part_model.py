#!/usr/bin/env python3
"""Evaluate a two-part FPL appearance/minutes + conditional-points model.

All labels are player-gameweek aggregates. Features are lagged and shared by
all fixtures in a DGW. Actual minutes define labels only, never live cohorts.
"""
from __future__ import annotations
import argparse, csv, json, math
from collections import defaultdict
from pathlib import Path
from train_fpl_exploratory_ridge import fit_ridge, predict, mae, rmse

FEATURES = (
    "prior_gw_points", "prior3_gw_points_avg", "prior5_gw_points_avg",
    "prior_gw_minutes", "prior3_gw_minutes_avg", "prior5_gw_minutes_avg",
    "prior5_appearance_rate", "season_appearance_rate",
    "season_to_date_minutes", "season_to_date_points_per90", "was_home",
)
RIDGE_LAMBDA = 10.0


def num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def group_player_gameweeks(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["season"], str(row["fpl_element_id"]), int(row["gameweek"]))].append(row)
    result = []
    for (season, player, gw), fixtures in sorted(groups.items()):
        first = fixtures[0]
        record = {name: num(first.get(name)) for name in FEATURES if name != "was_home"}
        homes = [num(x.get("was_home")) for x in fixtures]
        record["was_home"] = sum(x for x in homes if x is not None) / len(homes) if any(x is not None for x in homes) else None
        minutes = [num(x.get("target_minutes")) for x in fixtures]
        points = [num(x.get("target_total_points")) for x in fixtures]
        if any(x is None for x in minutes + points):
            continue
        record.update({
            "season": season, "fpl_element_id": player, "gameweek": gw,
            "fixture_count": len(fixtures),
            "actual_minutes": sum(minutes),
            "actual_points": sum(points),
            "appeared": 1.0 if sum(minutes) > 0 else 0.0,
            "last5_baseline_points": num(first.get("prior5_gw_points_avg")),
            "last_gw_baseline_minutes": num(first.get("prior_gw_minutes")),
        })
        result.append(record)
    return result


def fit_linear_probability(rows):
    # A regularized linear-probability model is intentionally transparent;
    # clipping is applied only to its predicted probability, not to labels.
    return fit_ridge(rows, "appeared", FEATURES, RIDGE_LAMBDA)


def probability(model, row):
    return min(1.0, max(0.0, predict(model, row)))


def sigmoid(value):
    value=max(-35.0,min(35.0,value))
    return 1.0/(1.0+math.exp(-value))


def fit_platt(scores, labels):
    """Fit a two-parameter logistic calibration map on a chronological calibration slice."""
    if len(scores)!=len(labels) or len(scores)<10:
        raise ValueError("Insufficient calibration examples")
    prevalence=min(1.0-1e-6,max(1e-6,sum(labels)/len(labels)))
    intercept=math.log(prevalence/(1.0-prevalence))
    slope=1.0
    for _ in range(100):
        g0=g1=h00=h01=h11=0.0
        for score,label in zip(scores,labels):
            p=sigmoid(intercept+slope*score)
            error=p-label
            weight=max(1e-8,p*(1.0-p))
            g0+=error
            g1+=error*score
            h00+=weight
            h01+=weight*score
            h11+=weight*score*score
        h00+=1e-8
        h11+=1e-6
        determinant=h00*h11-h01*h01
        if determinant<=1e-12:
            break
        step0=(h11*g0-h01*g1)/determinant
        step1=(-h01*g0+h00*g1)/determinant
        intercept-=step0
        slope-=step1
        if max(abs(step0),abs(step1))<1e-8:
            break
    return {"intercept":intercept,"slope":slope,"method":"PLATT_LOGISTIC_CALIBRATION"}


def calibrated_probability(calibrator, score):
    return sigmoid(calibrator["intercept"]+calibrator["slope"]*score)


def binary_metrics(actual, probs):
    eps = 1e-12
    brier = sum((p-y)**2 for y,p in zip(actual,probs))/len(actual)
    logloss = -sum(y*math.log(max(eps,p))+(1-y)*math.log(max(eps,1-p)) for y,p in zip(actual,probs))/len(actual)
    bins=[]
    for lo in (0.0,0.2,0.4,0.6,0.8):
        hi=lo+0.2
        selected=[(y,p) for y,p in zip(actual,probs) if lo <= p < hi or (hi == 1.0 and p == 1.0)]
        if selected:
            bins.append({"lower":lo,"upper":hi,"count":len(selected),
                         "mean_predicted":round(sum(p for _,p in selected)/len(selected),6),
                         "observed_rate":round(sum(y for y,_ in selected)/len(selected),6)})
    return {"brier":round(brier,6),"log_loss":round(logloss,6),"calibration_bins":bins}


def regression_metrics(actual, predicted):
    return {"mae":round(mae(actual,predicted),6),"rmse":round(rmse(actual,predicted),6),
            "mean_error":round(sum(p-a for a,p in zip(actual,predicted))/len(actual),6)}


def evaluate(rows, holdout_fraction=0.2):
    groups=[r for r in group_player_gameweeks(rows) if r["gameweek"]>1]
    chronology=sorted({(r["season"],r["gameweek"]) for r in groups})
    if len(chronology)<20: raise ValueError("Insufficient chronological gameweeks")
    n=max(1,math.ceil(len(chronology)*holdout_fraction))
    valid_keys=set(chronology[-n:])
    train=[r for r in groups if (r["season"],r["gameweek"]) not in valid_keys and r["gameweek"]>1]
    valid=[r for r in groups if (r["season"],r["gameweek"]) in valid_keys]
    if len(train)<len(FEATURES)+2 or not valid: raise ValueError("Insufficient training or validation rows")

    # Reserve the final fifth of the pre-test training period for calibration.
    train_keys=sorted({(r["season"],r["gameweek"]) for r in train})
    calibration_count=max(1,math.ceil(len(train_keys)*0.2))
    calibration_keys=set(train_keys[-calibration_count:])
    appearance_fit=[r for r in train if (r["season"],r["gameweek"]) not in calibration_keys]
    calibration_rows=[r for r in train if (r["season"],r["gameweek"]) in calibration_keys]
    appearance_model=fit_linear_probability(appearance_fit)
    calibration_scores=[predict(appearance_model,r) for r in calibration_rows]
    calibrator=fit_platt(calibration_scores,[r["appeared"] for r in calibration_rows])
    minutes_model=fit_ridge(train,"actual_minutes",FEATURES,RIDGE_LAMBDA)
    positive_train=[r for r in train if r["appeared"]==1.0]
    conditional_points_model=fit_ridge(positive_train,"actual_points",FEATURES,RIDGE_LAMBDA)
    # Direct model remains an apples-to-apples comparator on the same player-GW rows.
    direct_points_model=fit_ridge(train,"actual_points",FEATURES,RIDGE_LAMBDA)

    scored=[]
    for r in valid:
        raw_score=predict(appearance_model,r)
        p_raw=min(1.0,max(0.0,raw_score))
        p_cal=calibrated_probability(calibrator,raw_score)
        conditional=max(0.0,predict(conditional_points_model,r))
        two_part=p_cal*conditional
        two_part_raw=p_raw*conditional
        direct=predict(direct_points_model,r)
        last5=r["last5_baseline_points"]
        if last5 is None: continue
        scored.append({**r,"p_appearance":p_cal,"p_appearance_raw":p_raw,
                       "conditional_points":conditional,"two_part_points":two_part,
                       "two_part_points_raw":two_part_raw,"direct_points":direct,
                       "predicted_minutes":min(180.0,max(0.0,predict(minutes_model,r)))})
    if not scored: raise ValueError("No validation rows with complete last-five baseline")
    actual=[r["actual_points"] for r in scored]
    actual_app=[r["appeared"] for r in scored]
    probs=[r["p_appearance"] for r in scored]
    raw_probs=[r["p_appearance_raw"] for r in scored]
    appearance_baseline=[min(1.0,max(0.0,r["prior5_appearance_rate"])) for r in scored]
    two=[r["two_part_points"] for r in scored]
    two_raw=[r["two_part_points_raw"] for r in scored]
    direct=[r["direct_points"] for r in scored]
    last5=[r["last5_baseline_points"] for r in scored]
    minute_actual=[r["actual_minutes"] for r in scored]
    minute_pred=[r["predicted_minutes"] for r in scored]
    minute_base=[r["last_gw_baseline_minutes"] for r in scored]
    def point_report(pred):
        return regression_metrics(actual,pred)
    # Post-outcome positive-minute strata are diagnostics only, never prediction filters.
    appeared=[i for i,r in enumerate(scored) if r["appeared"]==1.0]
    per_season={}
    for season in sorted({r["season"] for r in scored}):
        idx=[i for i,r in enumerate(scored) if r["season"]==season]
        per_season[season]={
            "player_gameweeks":len(idx),
            "appearance":{
                "calibrated_model":binary_metrics([actual_app[i] for i in idx],[probs[i] for i in idx]),
                "raw_clipped_model":binary_metrics([actual_app[i] for i in idx],[raw_probs[i] for i in idx]),
                "prior5_appearance_rate_baseline":binary_metrics([actual_app[i] for i in idx],[appearance_baseline[i] for i in idx]),
            },
            "minutes_mae":round(mae([minute_actual[i] for i in idx],[minute_pred[i] for i in idx]),6),
            "two_part_points":regression_metrics([actual[i] for i in idx],[two[i] for i in idx]),
            "direct_points":regression_metrics([actual[i] for i in idx],[direct[i] for i in idx]),
            "last5_points":regression_metrics([actual[i] for i in idx],[last5[i] for i in idx]),
        }
    return {
        "status":"RESEARCH_ONLY",
        "point_in_time_status":"NOT_VERIFIED_RETROSPECTIVE_SOURCE_VINTAGES",
        "unit":"player_gameweek; DGW fixture labels summed before evaluation",
        "train_gameweeks":len({(r["season"],r["gameweek"]) for r in train}),
        "validation_gameweeks":len(valid_keys),
        "training_player_gameweeks":len(train),
        "appearance_model_fit_player_gameweeks":len(appearance_fit),
        "appearance_calibration_player_gameweeks":len(calibration_rows),
        "appearance_calibrator":calibrator,
        "positive_minutes_training_player_gameweeks":len(positive_train),
        "validation_player_gameweeks":len(scored),
        "appearance":{
            "calibrated_model":binary_metrics(actual_app,probs),
            "raw_clipped_model":binary_metrics(actual_app,raw_probs),
            "prior5_appearance_rate_baseline":binary_metrics(actual_app,appearance_baseline),
        },
        "minutes": {
            "model":regression_metrics(minute_actual,minute_pred),
            "last_gameweek_baseline":regression_metrics(minute_actual,[x for x in minute_base if x is not None])
                if all(x is not None for x in minute_base) else None,
        },
        "points": {
            "two_part_expected_points_calibrated":point_report(two),
            "two_part_expected_points_raw":point_report(two_raw),
            "direct_points_model":point_report(direct),
            "last5_points_baseline":point_report(last5),
            "two_part_minus_direct_mae":round(mae(actual,two)-mae(actual,direct),6),
            "two_part_minus_direct_rmse":round(rmse(actual,two)-rmse(actual,direct),6),
            "positive_minutes_post_outcome_diagnostic": {
                "rows":len(appeared),
                "two_part_mae":round(mae([actual[i] for i in appeared],[two[i] for i in appeared]),6),
                "direct_mae":round(mae([actual[i] for i in appeared],[direct[i] for i in appeared]),6),
                "warning":"Post-outcome diagnostic only. Actual minutes must never select or filter live predictions."
            } if appeared else None,
        },
        "validation_seasons":sorted({r["season"] for r in scored}),
        "per_season_validation_metrics":per_season,
        "features":list(FEATURES),
        "construction":"Appearance ridge fitted on the earlier training block; Platt map fitted on a later calibration block; conditional points trained on positive-minute rows from the full pre-test training period; expected points = calibrated appearance probability × conditional points.",
        "leakage_controls":[
            "Actual minutes are labels only and never determine the validation prediction cohort.",
            "All features are lagged; target fixture statistics are excluded.",
            "DGW actual points/minutes are summed at player-GW level.",
            "Training-only imputation and scaling are used by ridge fits.",
        ],
        "limitations":[
            "Platt calibration uses a chronologically later calibration slice; final holdout remains untouched.",
            "Calibration stability still needs walk-forward validation across multiple seasons.",
            "Expected points distribution is not yet fully estimated; this stage evaluates its mean decomposition.",
            "Retrospective source exports are not verified pre-deadline snapshots.",
            "One chronological holdout is preliminary; walk-forward folds and calibration are next.",
        ],
        "decision":"DO_NOT_PROMOTE",
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    with a.input.open(newline="",encoding="utf-8-sig") as f: rows=list(csv.DictReader(f))
    report=evaluate(rows)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__": main()
