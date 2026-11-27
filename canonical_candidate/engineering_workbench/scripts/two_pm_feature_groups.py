"""Validated, versioned feature-group contract for the independent 2PM model."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EXPECTED_DEFENSIVE_COLUMNS = (
    "ar_defensive_contribution_3", "ar_defensive_contribution_5",
    "ar_defensive_contribution_10", "ar_defensive_contribution_38",
    "ar_cbit_3", "ar_cbit_5", "ar_cbit_10", "ar_cbit_38",
    "ar_recoveries_3", "ar_recoveries_5", "ar_recoveries_10", "ar_recoveries_38",
    "ar_tackles_3", "ar_tackles_5", "ar_tackles_10", "ar_tackles_38",
    "ar_dc_hit_rate_3", "ar_dc_hit_rate_5", "ar_dc_hit_rate_10",
    "ar_dc_near_rate_3", "ar_dc_near_rate_5", "ar_dc_near_rate_10",
    "ar_dc_ppg_5",
    "ar_opp_dc_allowed_3", "ar_opp_dc_allowed_5", "ar_opp_dc_allowed_10",
    "ar_opp_tackles_allowed_5",
)


def validate_feature_group_manifest(
    schema: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, tuple[str, ...]]:
    """Fail closed unless groups exactly partition the pinned ordered schema."""
    schema_order = tuple(schema.get("feature_order", ()))
    if schema.get("feature_count") != 286 or len(schema_order) != 286:
        raise ValueError("Expected the pinned 286-feature schema")
    if len(set(schema_order)) != len(schema_order):
        raise ValueError("Schema feature order contains duplicate names")
    if manifest.get("status") != "CANDIDATE_NOT_FROZEN":
        raise ValueError("Feature-group manifest must remain explicitly un-frozen")
    source = manifest.get("source_schema", {})
    if (
        source.get("version") != schema.get("schema_version")
        or source.get("upstream_commit") != schema.get("upstream_commit")
        or source.get("feature_count") != len(schema_order)
    ):
        raise ValueError("Feature-group manifest is pinned to a different source schema")

    groups = manifest.get("feature_groups", {})
    common = tuple(groups.get("common_candidate", {}).get("feature_order", ()))
    defensive = tuple(groups.get("defensive_regime_dependent", {}).get("feature_order", ()))
    if len(common) != 259 or len(defensive) != 27:
        raise ValueError("Expected 259 common and 27 defensive-regime-dependent features")
    if defensive != EXPECTED_DEFENSIVE_COLUMNS:
        raise ValueError("Defensive-regime-dependent feature inventory/order changed")
    if len(set(common)) != len(common) or len(set(defensive)) != len(defensive):
        raise ValueError("Feature group contains duplicate names")
    if set(common).intersection(defensive):
        raise ValueError("Feature groups must be disjoint")
    if set(common).union(defensive) != set(schema_order):
        missing = sorted(set(schema_order) - set(common) - set(defensive))
        extra = sorted((set(common) | set(defensive)) - set(schema_order))
        raise ValueError(f"Feature groups do not partition schema; missing={missing}, extra={extra}")
    expected_common = tuple(name for name in schema_order if name not in set(defensive))
    if common != expected_common:
        raise ValueError("Common feature order does not preserve pinned schema order")

    for group_name, expected_count in (
        ("common_candidate", 259), ("defensive_regime_dependent", 27)
    ):
        if groups[group_name].get("count") != expected_count:
            raise ValueError(f"Incorrect declared count for {group_name}")

    accounting = manifest.get("reconstruction_family_accounting", {})
    player_history = tuple(accounting.get("defensive_player_history", {}).get("feature_order", ()))
    fixture_context = tuple(accounting.get("fixture_context", {}).get("feature_order", ()))
    if len(player_history) != 26 or len(set(player_history)) != 26:
        raise ValueError("Expected 26 distinct defensive/player-history reconstruction columns")
    if len(fixture_context) != 6 or len(set(fixture_context)) != 6:
        raise ValueError("Expected six distinct fixture-context reconstruction columns")
    if not set(player_history).issubset(schema_order) or not set(fixture_context).issubset(schema_order):
        raise ValueError("Reconstruction-family accounting contains columns outside schema")
    if set(player_history).intersection(fixture_context):
        raise ValueError("Player-history and fixture-context reconstruction families must be disjoint")
    if not set(EXPECTED_DEFENSIVE_COLUMNS[:23]).issubset(player_history):
        raise ValueError("Player-history accounting omits defensive rolling/rate columns")
    if not set(EXPECTED_DEFENSIVE_COLUMNS[23:]).issubset(fixture_context):
        raise ValueError("Fixture-context accounting omits opponent allowance columns")
    if not {"ar_starts_3", "ar_starts_5", "ar_starts_10"}.issubset(player_history):
        raise ValueError("Player-history accounting must include starts-rate columns")
    if not {"ar_rest_days", "ar_team_matches_14d"}.issubset(fixture_context):
        raise ValueError("Fixture-context accounting must include schedule columns")

    scoring = manifest.get("scoring_regime_contract", {})
    expected_regimes = {
        "legacy_no_defensive_contribution_points": [
            "2020-21", "2021-22", "2022-23", "2023-24", "2024-25"
        ],
        "defensive_contribution_v1": ["2025-26", "2026-27"],
    }
    if scoring.get("version") != "1.0.0" or scoring.get("regime_by_season") != expected_regimes:
        raise ValueError("Scoring-regime season boundary does not match official FPL rules")
    regimes = scoring.get("regimes", {})
    legacy = regimes.get("legacy_no_defensive_contribution_points", {})
    current = regimes.get("defensive_contribution_v1", {})
    if legacy.get("code") != 0 or legacy.get("defensive_contribution_fpl_points") is not False:
        raise ValueError("Legacy scoring-regime encoding is invalid")
    if current.get("code") != 1 or current.get("defensive_contribution_fpl_points") is not True:
        raise ValueError("Defensive-contribution scoring-regime encoding is invalid")
    expected_actions = {
        "defender": (["clearances_blocks_interceptions", "tackles"], 10),
        "midfielder_forward": (
            ["clearances_blocks_interceptions", "tackles", "recoveries"], 12
        ),
    }
    for role, (fields, threshold) in expected_actions.items():
        rule = current.get(role, {})
        if (
            rule.get("action_fields") != fields
            or rule.get("threshold") != threshold
            or rule.get("award_points") != 2
            or rule.get("maximum_award_points_per_match") != 2
        ):
            raise ValueError(f"Official defensive-contribution scoring rule changed: {role}")
    award = current.get("reported_award_field", {})
    if (
        award.get("source_field") != "defensive_contribution"
        or "not an action-count component" not in award.get("role", "")
    ):
        raise ValueError("Defensive-contribution award field semantics are ambiguous")
    availability = manifest.get("feature_source_availability", {})
    if availability.get("state_codes") != {"UNAVAILABLE": 0, "AVAILABLE": 1, "UNKNOWN": 2}:
        raise ValueError("Feature availability state codes must be 0/1/2")
    if availability.get("default_state") != "UNKNOWN":
        raise ValueError("Unspecified feature availability must remain UNKNOWN")
    availability_groups = availability.get("groups", {})
    source_availability_groups = manifest.get("source_availability_groups", {})
    known_availability_groups = set(groups) | set(source_availability_groups)
    if set(availability_groups) - known_availability_groups:
        raise ValueError("Availability policy references an unknown feature group")
    for group_name, season_policy in availability_groups.items():
        valid_states = {"UNAVAILABLE", "AVAILABLE", "UNKNOWN"}
        if any(value not in valid_states for value in season_policy.values()):
            raise ValueError(f"Invalid availability state in policy for {group_name}")
        if group_name == "defensive_regime_dependent":
            expected_legacy = {
                "2020-21": "UNAVAILABLE", "2021-22": "UNAVAILABLE",
                "2022-23": "UNAVAILABLE", "2023-24": "UNAVAILABLE",
                "2024-25": "UNAVAILABLE", "2025-26": "AVAILABLE",
            }
            legacy_policy = {
                season: state for season, state in season_policy.items()
                if season != "2026-27"
            }
            if legacy_policy != expected_legacy:
                raise ValueError("Defensive source-availability policy does not match pinned vintages")
            if season_policy.get("2026-27", "UNKNOWN") != "UNKNOWN":
                raise ValueError("2026/27 defensive source availability must remain UNKNOWN")

    sentinel_features = set(manifest.get("snapshot_missing_sentinel_features", []))
    expected_sentinels = {
        "ar_ep_next", "sig_status_risk", "sig_chance_playing", "sig_has_news",
        "value", "selected", "transfers_balance",
    }
    if sentinel_features != expected_sentinels or not sentinel_features.issubset(schema_order):
        raise ValueError("Missing-snapshot sentinel feature inventory changed")

    family_register = manifest.get("feature_family_register", {})
    if family_register.get("source_schema_version") != schema.get("schema_version"):
        raise ValueError("Feature-family register is pinned to a different schema version")
    if family_register.get("status") != "ALL_HOLD":
        raise ValueError("Feature-family register must preserve ALL_HOLD admission status")
    family_groups = family_register.get("families", {})
    family_features = [
        feature for entry in family_groups.values()
        for feature in entry.get("feature_order", [])
    ]
    if (
        len(family_features) != 286
        or len(set(family_features)) != 286
        or set(family_features) != set(schema_order)
    ):
        raise ValueError("Feature-family register must partition all 286 schema columns exactly once")
    for family_name, entry in family_groups.items():
        if entry.get("count") != len(entry.get("feature_order", [])):
            raise ValueError(f"Incorrect feature count in family {family_name}")
    treatment_groups = family_register.get("reconstruction_treatments", {})
    treatment_features = [
        feature for entry in treatment_groups.values()
        for feature in entry.get("feature_order", [])
    ]
    if (
        len(treatment_features) != 286
        or len(set(treatment_features)) != 286
        or set(treatment_features) != set(schema_order)
    ):
        raise ValueError("Reconstruction-treatment register must partition all 286 columns exactly once")
    for treatment_name, entry in treatment_groups.items():
        if entry.get("count") != len(entry.get("feature_order", [])):
            raise ValueError(f"Incorrect feature count in treatment {treatment_name}")
    if family_register.get("admission_status_counts") != {"HOLD": 286}:
        raise ValueError("Every feature must remain HOLD in the admission register")
    if manifest.get("require_source_observed_sidecars") is not True:
        raise ValueError("Production 2PM masks must require pre-fill source observation sidecars")
    vintage_policies = manifest.get("source_vintage_policies", {})
    understat_policy = vintage_policies.get("understat", {})
    understat_features = tuple(understat_policy.get("feature_order", ()))
    expected_understat = tuple(
        name for name in schema_order
        if name.startswith((
            "player_xg_", "player_xa_", "player_shots_", "player_key_passes_",
            "player_xgbuildup_", "player_xgchain_",
        ))
        or name.startswith(("team_", "opp_"))
        or name == "status_league_rank"
    )
    if (
        understat_policy.get("status") != "HOLD"
        or understat_policy.get("mask_action") != "FORCE_UNOBSERVED"
        or understat_policy.get("feature_count") != 152
        or understat_features != expected_understat
    ):
        raise ValueError("Understat source-vintage HOLD policy must cover the exact 152-feature inventory")
    availability_groups = manifest.get("source_availability_groups", {})
    player_understat = tuple(availability_groups.get("understat_player_history", {}).get("feature_order", ()))
    team_understat = tuple(availability_groups.get("understat_team_context", {}).get("feature_order", ()))
    expected_player_understat = tuple(name for name in understat_features if name.startswith("player_"))
    expected_team_understat = tuple(name for name in understat_features if not name.startswith("player_"))
    if (
        len(player_understat) != 30
        or len(team_understat) != 122
        or availability_groups.get("understat_player_history", {}).get("count") != 30
        or availability_groups.get("understat_team_context", {}).get("count") != 122
        or player_understat != expected_player_understat
        or team_understat != expected_team_understat
        or set(player_understat).intersection(team_understat)
        or set(player_understat).union(team_understat) != set(understat_features)
    ):
        raise ValueError("Understat structural-availability groups must partition all 152 Understat features")
    availability_policy = manifest.get("feature_source_availability", {})
    availability_groups_policy = availability_policy.get("groups", {})
    player_availability = availability_groups_policy.get("understat_player_history", {})
    team_availability = availability_groups_policy.get("understat_team_context", {})
    if (
        player_availability.get("2020-21") != "UNAVAILABLE"
        or team_availability.get("2020-21") != "UNKNOWN"
        or any(player_availability.get(season) != "UNKNOWN" for season in (
            "2021-22", "2022-23", "2023-24", "2024-25", "2025-26", "2026-27"
        ))
        or any(team_availability.get(season) != "UNKNOWN" for season in (
            "2021-22", "2022-23", "2023-24", "2024-25", "2025-26", "2026-27"
        ))
    ):
        raise ValueError("Understat player/team structural-availability states are incorrect");
    pins = manifest.get("source_pins", {})
    for source_name in ("dastan", "vaastav", "fplcache"):
        pin = pins.get(source_name, {})
        if not pin.get("repository") or not pin.get("commit"):
            raise ValueError(f"Missing pinned source provenance for {source_name}")
    dastan_pin = pins["dastan"]
    if (
        dastan_pin.get("commit") != schema.get("upstream_commit")
        or dastan_pin.get("repository") != schema.get("upstream_repository")
    ):
        raise ValueError("Dastan pin does not match the pinned feature schema")

    return {
        "common_candidate": common,
        "defensive_regime_dependent": defensive,
        "defensive_player_history": player_history,
        "fixture_context": fixture_context,
    }


def load_feature_group_manifest(
    workbench_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, tuple[str, ...]]]:
    """Load and validate the manifest beside the pinned schema config."""
    root = workbench_root or Path(__file__).resolve().parents[1]
    config = root / "config"
    schema = json.loads((config / "2pm_dastan_286_schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((config / "2pm_feature_group_manifest.json").read_text(encoding="utf-8"))
    groups = validate_feature_group_manifest(schema, manifest)
    return schema, manifest, groups
