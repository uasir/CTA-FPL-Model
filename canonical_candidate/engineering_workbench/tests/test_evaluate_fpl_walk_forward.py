import math
from evaluate_fpl_walk_forward import FEATURES, evaluate_walk_forward, fit_ridge_fast, fit_minutes_band_model, fit_minutes_band_representatives, minutes_band_probabilities, minutes_band, minutes_distribution_metrics, one_hot_minutes_distribution
from train_fpl_exploratory_ridge import fit_ridge, predict


def row(season, gw, player, points, minutes, prior=4.0):
    return {
        "season":season,"gameweek":gw,"fpl_element_id":str(player),
        "prior_gw_points":prior,"prior3_gw_points_avg":prior,
        "prior5_gw_points_avg":prior,"prior_gw_minutes":90 if gw>1 else None,
        "prior3_gw_minutes_avg":75,"prior5_gw_minutes_avg":70,
        "prior5_appearance_rate":0.8,"season_appearance_rate":0.75,
        "season_to_date_minutes":500,"season_to_date_points_per90":4.5,
        "was_home":1.0,"target_total_points":points,"target_minutes":minutes,
    }


def test_expanding_season_walk_forward_never_trains_on_validation_season():
    rows=[]
    seasons=("2022-23","2023-24","2024-25","2025-26")
    for season_index,season in enumerate(seasons):
        for gw in range(1,17):
            for player in range(1,15):
                minutes=0 if (gw+player)%5==0 else (90 if (gw+player)%3 else 30)
                points=0 if minutes==0 else ((gw*player+season_index)%9)+2
                rows.append(row(season,gw,player,points,minutes,prior=(gw%6)+1))
    report=evaluate_walk_forward(rows)
    assert report["fold_count"]==3
    assert report["status"]=="RESEARCH_ONLY"
    assert report["pooled_weighted_metrics"]["validation_player_gameweeks"]>0
    for fold in report["folds"]:
        assert all(training_season < fold["season"] for training_season in fold["training_seasons"])
        assert fold["validation_player_gameweeks"]>0
        assert fold["calibration_player_gameweeks"]>0
        assert fold["calibration_appearance_positive"] + fold["calibration_appearance_negative"] == fold["calibration_player_gameweeks"]
        assert fold["calibration_appearance_positive"]>0 and fold["calibration_appearance_negative"]>0
        assert fold["appearance_fit_last_gameweek"]["season"] < fold["calibration_first_gameweek"]["season"] or (fold["appearance_fit_last_gameweek"]["season"] == fold["calibration_first_gameweek"]["season"] and fold["appearance_fit_last_gameweek"]["gameweek"] < fold["calibration_first_gameweek"]["gameweek"])
        assert fold["calibration_last_gameweek"]["season"] < fold["season"]
        assert fold["appearance_fit_player_gameweeks"] + fold["calibration_player_gameweeks"] == fold["training_player_gameweeks"]
        assert fold["appearance"]["calibrated"]["brier"]>=0
        assert fold["minutes"]["two_part_calibrated"]["mae"]>=0
        assert fold["minutes"]["two_part_raw"]["mae"]>=0
        assert fold["minutes"]["unconditional_regression"]["mae"]>=0
        assert fold["minutes"]["prior3_gameweeks_baseline"]["mae"]>=0
        assert fold["minutes"]["prior5_gameweeks_baseline"]["mae"]>=0
        assert fold["minutes"]["lagged_feature_ridge"]["mae"]>=0
        assert fold["minutes"]["two_part_lagged_feature_ridge_raw"]["mae"]>=0
        assert fold["minutes"]["two_part_lagged_feature_ridge_calibrated"]["mae"]>=0
        assert fold["points"]["direct"]["mae"]>=0
        assert fold["appearance_hurdle_points_bands"]["calibrated_appearance_probability"]["expected_points_mae"]>=0
        assert fold["appearance_hurdle_points_bands"]["raw_appearance_probability"]["multiclass_log_loss"]>=0
    folds=report["folds"]
    expected_rmse=math.sqrt(sum(f["validation_player_gameweeks"]*f["points"]["direct"]["rmse"]**2 for f in folds)/sum(f["validation_player_gameweeks"] for f in folds))
    assert abs(report["pooled_weighted_metrics"]["points"]["direct"]["rmse"]-expected_rmse)<1e-6

 
def test_numpy_walk_forward_ridge_matches_canonical_ridge_solver():
    rows=[]
    for gw in range(1,15):
        for player in range(1,15):
            minutes=0 if (gw+player)%5==0 else 90
            points=0 if minutes==0 else ((gw*player)%9)+2
            rows.append(row("2024-25",gw,player,points,minutes,prior=(gw%6)+1))
    canonical=fit_ridge(rows,"target_total_points",FEATURES,10.0)
    accelerated=fit_ridge_fast(rows,"target_total_points",FEATURES,10.0)
    for item in rows[:10]:
        assert abs(predict(canonical,item)-predict(accelerated,item))<1e-7



def test_minutes_band_model_probabilities_are_valid_and_training_only():
    rows=[]
    for gw in range(1,19):
        for player in range(1,20):
            minutes=(0 if (gw+player)%5==0 else
                     15 if (gw+player)%5==1 else
                     45 if (gw+player)%5==2 else
                     75 if (gw+player)%5==3 else 90)
            points=0 if minutes==0 else 2+(gw*player)%10
            rows.append(row("2024-25",gw,player,points,minutes,prior=(gw%6)+1))
    train=[{**item,"actual_minutes":item["target_minutes"]} for item in rows[:250]]
    model=fit_minutes_band_model(train,iterations=250)
    probs=minutes_band_probabilities(model,rows[260])
    assert len(probs)==5
    assert all(0.0<=p<=1.0 for p in probs)
    assert abs(sum(probs)-1.0)<1e-9
    assert [minutes_band(v) for v in (0,1,29,30,59,60,89,90)] == [0,1,1,2,2,3,3,4]
    fallback=[0.1,0.2,0.3,0.2,0.2]
    assert one_hot_minutes_distribution(None,fallback)==fallback
    assert one_hot_minutes_distribution(90,fallback)==[0.0,0.0,0.0,0.0,1.0]
    metrics=minutes_distribution_metrics([0,15,45,75,90],[ [1,0,0,0,0],[0,1,0,0,0],[0,0,1,0,0],[0,0,0,1,0],[0,0,0,0,1] ])
    assert metrics["mae"]==0.0
    assert metrics["multiclass_log_loss"]>=0.0


def test_walk_forward_report_includes_minutes_distribution_metrics():
    rows=[]
    seasons=("2022-23","2023-24","2024-25","2025-26")
    for season_index,season in enumerate(seasons):
        for gw in range(1,17):
            for player in range(1,15):
                minutes=(0 if (gw+player)%5==0 else
                         15 if (gw+player)%5==1 else
                         45 if (gw+player)%5==2 else
                         75 if (gw+player)%5==3 else 90)
                points=0 if minutes==0 else ((gw*player+season_index)%9)+2
                rows.append(row(season,gw,player,points,minutes,prior=(gw%6)+1))
    report=evaluate_walk_forward(rows)
    assert "minutes_bands" in report["pooled_weighted_metrics"]
    for fold in report["folds"]:
        bands=fold["minutes_bands"]
        assert bands["calibrated"]["mae"]>=0
        assert bands["calibrated"]["multiclass_log_loss"]>=0
        assert bands["raw"]["multiclass_brier"]>=0
        assert bands["last_gameweek_or_training_prior"]["accuracy"]>=0
        assert fold["points"]["minutes_band_calibrated"]["mae"]>=0



def test_minutes_band_representatives_are_training_only_class_means():
    train = [
        {"actual_minutes": 0},
        {"actual_minutes": 10},
        {"actual_minutes": 20},
        {"actual_minutes": 40},
        {"actual_minutes": 80},
        {"actual_minutes": 90},
    ]
    representatives = fit_minutes_band_representatives(train)
    assert representatives.tolist() == [0.0, 15.0, 40.0, 80.0, 90.0]
    probs = [[0.0, 1.0, 0.0, 0.0, 0.0]]
    metrics = minutes_distribution_metrics([10], probs, representatives)
    assert metrics["mae"] == 5.0


def test_points_band_model_distribution_and_training_only_representatives():
    from evaluate_fpl_walk_forward import (
        fit_points_band_model, fit_points_band_representatives,
        points_band, points_band_probabilities, points_distribution_metrics,
    )
    rows=[]
    values=(-2,0,1,2,3,4,5,6,7,8,9,10,12)
    for gw in range(1,20):
        for player in range(1,16):
            minutes=0 if (gw+player)%6==0 else 90
            points=values[(gw*player)%len(values)] if minutes else 0
            item=row("2024-25",gw,player,points,minutes,prior=(gw%6)+1)
            item["actual_points"]=points
            item["actual_minutes"]=minutes
            rows.append(item)
    train=rows[:220]
    model=fit_points_band_model(train,iterations=240)
    probs=points_band_probabilities(model,rows[230])
    assert len(probs)==6
    assert all(0.0<=p<=1.0 for p in probs)
    assert abs(sum(probs)-1.0)<1e-9
    assert [points_band(v) for v in (-2,-1,0,1,2,3,5,6,9,10,15)] == [0,0,1,2,2,3,3,4,4,5,5]
    reps=fit_points_band_representatives(train)
    assert len(reps)==6
    metrics=points_distribution_metrics([-1,0,2,4,8,12],[
        [1,0,0,0,0,0],[0,1,0,0,0,0],[0,0,1,0,0,0],
        [0,0,0,1,0,0],[0,0,0,0,1,0],[0,0,0,0,0,1]
    ],[-1,0,2,4,8,12])
    assert metrics["expected_points_mae"]==0.0
    assert metrics["ranked_probability_score"]>=0.0


def test_appearance_hurdle_distribution_places_nonappearance_mass_in_zero_class():
    from evaluate_fpl_walk_forward import combine_appearance_points_distribution
    conditional=[0.1,0.2,0.1,0.2,0.2,0.2]
    absent=combine_appearance_points_distribution(0.0,conditional)
    assert absent.tolist() == [0.0,1.0,0.0,0.0,0.0,0.0]
    present=combine_appearance_points_distribution(1.0,conditional)
    assert all(abs(a-b)<1e-12 for a,b in zip(present,conditional))
    mixed=combine_appearance_points_distribution(0.75,conditional)
    assert abs(sum(mixed)-1.0)<1e-12
    assert abs(mixed[1]-(0.25+0.75*conditional[1]))<1e-12
    assert all(p>=0.0 for p in mixed)



def test_paired_error_comparison_reports_aligned_deltas_and_probability_groups():
    from evaluate_fpl_walk_forward import paired_error_comparison
    actual=[0.0,2.0,5.0,8.0]
    candidate=[1.0,1.0,7.0,7.0]
    comparator=[2.0,3.0,4.0,10.0]
    groups=["low_<0.50","medium_0.50_to_0.80","high_>=0.80","high_>=0.80"]
    result=paired_error_comparison(actual,candidate,comparator,groups)
    assert result["n"]==4
    assert result["mean_absolute_error_delta"]==-0.5
    assert result["mean_squared_error_delta"]==-3.5
    assert result["candidate_absolute_error_win_rate"]==0.75
    assert result["absolute_error_tie_rate"]==0.0
    assert result["by_group"]["high_>=0.80"]["n"]==2
    assert result["by_group"]["low_<0.50"]["mean_absolute_error_delta"]==-1.0
