from evaluate_fpl_two_part_model import evaluate, group_player_gameweeks, fit_platt, calibrated_probability


def row(season, gw, player, points, minutes, prior=4.0):
    return {
        "season":season,"gameweek":gw,"fpl_element_id":str(player),
        "prior_gameweeks_count":max(0,gw-1),
        "prior_gw_points":prior,"prior3_gw_points_avg":prior,
        "prior5_gw_points_avg":prior,"prior_gw_minutes":90 if gw>1 else None,
        "prior3_gw_minutes_avg":75,"prior5_gw_minutes_avg":70,
        "prior5_appearance_rate":0.8,"season_appearance_rate":0.75,
        "season_to_date_minutes":500,"season_to_date_points_per90":4.5,
        "was_home":1.0,"target_total_points":points,"target_minutes":minutes,
    }


def test_double_gameweek_targets_are_aggregated_before_two_part_model():
    rows=[row("2024-25",1,10,3,90),row("2024-25",1,10,5,90)]
    grouped=group_player_gameweeks(rows)
    assert len(grouped)==1
    assert grouped[0]["actual_points"]==8
    assert grouped[0]["actual_minutes"]==180
    assert grouped[0]["appeared"]==1


def test_zero_minute_player_gameweek_is_an_appearance_negative():
    grouped=group_player_gameweeks([row("2024-25",1,10,0,0)])
    assert grouped[0]["appeared"]==0
    assert grouped[0]["actual_points"]==0


def test_chronological_two_part_evaluation_uses_all_validation_rows():
    rows=[]
    for si,season in enumerate(("2023-24","2024-25","2025-26")):
        for gw in range(1,17):
            for player in range(1,15):
                minutes=0 if (gw+player)%5==0 else (90 if (gw+player)%3 else 30)
                points=0 if minutes==0 else ((gw*player)%9)+2
                rows.append(row(season,gw,player,points,minutes,prior=(gw%6)+1))
    report=evaluate(rows)
    assert report["status"]=="RESEARCH_ONLY"
    assert report["validation_gameweeks"]==9
    assert report["validation_player_gameweeks"]>0
    assert report["appearance"]["calibrated_model"]["brier"]>=0
    assert report["appearance"]["raw_clipped_model"]["brier"]>=0
    assert report["appearance"]["prior5_appearance_rate_baseline"]["brier"]>=0
    assert report["appearance"]["calibrated_model"]["log_loss"]>=0
    assert report["appearance_calibration_player_gameweeks"]>0
    assert report["points"]["two_part_expected_points_calibrated"]["mae"]>=0
    assert report["points"]["two_part_expected_points_raw"]["mae"]>=0
    assert report["points"]["direct_points_model"]["mae"]>=0
    assert "Actual minutes are labels only" in report["leakage_controls"][0]

 
def test_platt_calibrator_returns_bounded_monotonic_probabilities():
    scores=[-2.0,-1.0,-0.5,0.2,0.8,1.2,2.0,2.5,3.0,4.0,4.5,5.0]
    labels=[0,0,0,0,0,0,1,1,1,1,1,1]
    calibrator=fit_platt(scores,labels)
    probabilities=[calibrated_probability(calibrator,x) for x in scores]
    assert all(0.0 < p < 1.0 for p in probabilities)
    assert probabilities==sorted(probabilities)
