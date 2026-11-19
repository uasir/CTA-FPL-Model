from verify_cross_provider_fpl_identity import build_cross_provider_crosswalk


def row(provider, player_id, fpl_id="10", name="Example Player", dob="1990-01-01",
        priority=None, team_match="True", team_mismatch="False", overlap="8", minutes="600"):
    if provider == "Wyscout":
        priority = priority or "P1_MULTI_MATCH_TEAM_CORROBORATION"
        signature = "goal_assist_signature_exact"
    else:
        priority = priority or "P1_MULTI_MATCH_TEAM_SIGNATURE"
        signature = "full_signature_exact_rows"
    return {
        "provider": provider,
        "provider_player_id": str(player_id),
        "provider_player_name": name,
        "provider_birth_date": dob,
        "candidate_fpl_element_id": str(fpl_id),
        "candidate_fpl_player_code": "12345",
        "candidate_fpl_player_name": name,
        "candidate_fpl_team_id": "1",
        "candidate_fpl_team_name": "Arsenal",
        "candidate_status": "PENDING",
        "review_priority": priority,
        "team_match_to_season_end_team": team_match,
        "team_mismatch_to_season_end_team": team_mismatch,
        "fpl_history_overlap_rows": overlap,
        "fpl_positive_minutes_rows": minutes,
        signature: "5",
    }


def test_exact_name_dob_and_dual_p1_same_fpl_id_is_verified():
    verified, review, report = build_cross_provider_crosswalk(
        [row("Wyscout", 100)], [row("11footy", 200)]
    )
    assert len(verified) == 1
    assert verified[0]["provider_player_id"] == "100"
    assert verified[0]["corroborating_provider_player_id"] == "200"
    assert verified[0]["fpl_element_id"] == "10"
    assert verified[0]["verification_status"] == "VERIFIED_CROSS_PROVIDER_IDENTITY_AND_FPL_HISTORY"
    assert report["verified_crosswalk_rows"] == 1
    assert review == []


def test_birth_date_mismatch_is_not_verified():
    verified, review, report = build_cross_provider_crosswalk(
        [row("Wyscout", 100, dob="1990-01-01")],
        [row("11footy", 200, dob="1990-01-02")],
    )
    assert verified == []
    assert report["verified_crosswalk_rows"] == 0


def test_providers_must_agree_on_fpl_element_id():
    verified, review, _ = build_cross_provider_crosswalk(
        [row("Wyscout", 100, fpl_id="10")],
        [row("11footy", 200, fpl_id="11")],
    )
    assert verified == []
    assert "PROVIDERS_DISAGREE_ON_FPL_ELEMENT_ID" in review[0]["review_reason"]


def test_ambiguous_provider_name_dob_key_is_not_verified():
    verified, review, report = build_cross_provider_crosswalk(
        [row("Wyscout", 100), row("Wyscout", 101)],
        [row("11footy", 200)],
    )
    assert verified == []
    assert report["ambiguous_name_dob_keys"] == 1
    assert review[0]["review_reason"] == "AMBIGUOUS_PROVIDER_NAME_DOB_KEY"


def test_both_providers_must_have_p1_and_team_corroboration():
    verified, review, _ = build_cross_provider_crosswalk(
        [row("Wyscout", 100, priority="P2_TEAM_AND_STAT_CROSSCHECK")],
        [row("11footy", 200)],
    )
    assert verified == []
    assert "WYS_NOT_P1" in review[0]["review_reason"]
    verified, review, _ = build_cross_provider_crosswalk(
        [row("Wyscout", 100, team_match="False")],
        [row("11footy", 200)],
    )
    assert verified == []
    assert "WYS_TEAM_NOT_CORROBORATED" in review[0]["review_reason"]


def test_duplicate_fpl_element_collisions_are_not_promoted():
    w = [row("Wyscout", 100, name="Player One"), row("Wyscout", 101, name="Player Two")]
    f = [row("11footy", 200, name="Player One"), row("11footy", 201, name="Player Two")]
    verified, review, report = build_cross_provider_crosswalk(w, f)
    assert verified == []
    assert report["one_to_one_collision_ids"] >= 1
    assert all(item["review_reason"] == "ONE_TO_ONE_ID_COLLISION" for item in review)


def test_missing_or_invalid_dob_is_not_used_as_identity_evidence():
    verified, _, report = build_cross_provider_crosswalk(
        [row("Wyscout", 100, dob="")], [row("11footy", 200, dob="")]
    )
    assert verified == []
    assert report["exact_name_dob_key_matches"] == 0
