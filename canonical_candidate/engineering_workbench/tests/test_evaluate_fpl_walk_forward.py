from evaluate_fpl_walk_forward import evaluate_walk_forward, fit_ridge_fast
from train_fpl_exploratory_ridge import FEATURES, fit_ridge, predict


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
        assert fold["appearance"]["calibrated"]["brier"]>=0
        assert fold["points"]["direct"]["mae"]>=0

 
def test_numpy_walk_forward_ridge_matches_canonical_ridge_solver():
    rows=[]
    for gw in range(1,15):
        for player in range(1,15):
            minutes=0 if (gw+player)%5==0 else 90
            points=0 if minutes==0 else ((gw*player)%9)+2
            rows.append(row("2024-25",gw,player,points,minutes,prior=(gw%6)+1))
    canonical=fit_ridge(rows,"actual_points",FEATURES,10.0)
    accelerated=fit_ridge_fast(rows,"actual_points",FEATURES,10.0)
    for item in rows[:10]:
        assert abs(predict(canonical,item)-predict(accelerated,item))<1e-7
