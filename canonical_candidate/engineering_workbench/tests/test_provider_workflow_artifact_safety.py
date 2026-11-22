from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = {
    "fplcat": ROOT / ".github/workflows/capture-fplcat-benchmark.yml",
    "sidelinequant": ROOT / ".github/workflows/capture-sidelinequant-benchmark.yml",
    "fplrogue": ROOT / ".github/workflows/capture-fplrogue-benchmark.yml",
}


def test_public_provider_workflows_preserve_raw_artifacts_only_for_redistributable_feeds():
    fplcat = WORKFLOWS["fplcat"].read_text(encoding="utf-8")
    sideline = WORKFLOWS["sidelinequant"].read_text(encoding="utf-8")
    fplrogue = WORKFLOWS["fplrogue"].read_text(encoding="utf-8")

    # FPL Cat public use requires attribution; Sideline Quant provider data is CC BY 4.0.
    # Preserve immutable raw snapshots for those two eligible feeds, with run-scoped retention.
    assert "Upload immutable raw snapshot, M3-M4 replay and metadata summary" in fplcat
    assert "artifacts/fplcat/" in fplcat
    assert "artifacts/provider-summary/" in fplcat
    assert "retention-days: 90" in fplcat
    assert "Upload immutable raw snapshot, normalized feed and metadata summary" in sideline
    assert "artifacts/sidelinequant/" in sideline
    assert "artifacts/provider-summary/" in sideline
    assert "retention-days: 90" in sideline

    # FPLRogue remains metadata-only until source terms and redistribution permissions are cleared.
    assert "Upload metadata-only capture summary" in fplrogue
    upload_block = fplrogue.split("uses: actions/upload-artifact@v4", 1)[1]
    assert "artifacts/provider-summary/" in upload_block
    assert "artifacts/fplrogue/" not in upload_block


def test_wildcard_has_no_public_capture_workflow():
    assert not (ROOT / ".github/workflows/capture-fplwildcard-benchmark.yml").exists()



def test_personal_m3_workflow_accepts_public_manager_inputs_and_preserves_evidence_checks():
    path = ROOT / ".github/workflows/capture-predeadline-decision-evidence.yml"
    workflow = path.read_text(encoding="utf-8")
    checkout = workflow.index("Check out M3 implementation")
    sideline_download = workflow.index("Retrieve optional Sideline Quant raw and normalized snapshot")
    sideline_build = workflow.index("Build common provider capture envelope from Sideline Quant")
    capture = workflow.index("Capture and seal pre-deadline decision evidence")
    upload = workflow.index("Upload pre-deadline decision evidence and recommendation")
    assert checkout < sideline_download < sideline_build < capture < upload
    assert "manager_team_id:" in workflow
    assert 'default: "421025"' in workflow
    assert 'default: "2026-27"' in workflow
    assert "manager_state_json:" in workflow
    assert "season:" in workflow
    assert "MANAGER_TEAM_ID: ${{ inputs.manager_team_id }}" in workflow
    assert "MANAGER_STATE_JSON: ${{ inputs.manager_state_json }}" in workflow
    assert "SEASON: ${{ inputs.season }}" in workflow
    assert "secrets.M3_" not in workflow
    assert "Refuse personal decision capture in a public repository" not in workflow
    assert "name: predeadline-decision-evidence-manager-${{ inputs.manager_team_id }}-gw${{ inputs.gameweek }}-run${{ github.run_id }}" in workflow
    assert "sidelinequant_capture_run_id:" in workflow
    assert "sidelinequant-gw${{ inputs.gameweek }}-${{ inputs.sidelinequant_capture_run_id }}" in workflow
    assert "build_sideline_quant_provider_capture.py" in workflow
    assert "--provider-capture-override sidelinequant-provider-capture-override.json" in workflow
    assert "provisional-field-eo-${{ inputs.field_eo_capture_run_id }}" in workflow
    assert "run-id: ${{ inputs.field_eo_capture_run_id }}" in workflow
    assert "canonical_candidate/engineering_workbench/field-capture" in workflow
    replay_step = workflow.split("Independently re-execute the frozen decision", 1)[1]
    assert "--field-eo-csv field-capture/predeadline_field_eo.csv" in replay_step
    assert "--field-eo-report field-capture/predeadline_field_report.json" in replay_step

def test_predeadline_field_eo_workflow_upload_path_matches_capture_output():
    workflow_path = ROOT / ".github/workflows/capture-predeadline-field-eo.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    capture_script = (ROOT / "canonical_candidate/engineering_workbench/scripts/capture_predeadline_field_eo.py").read_text(encoding="utf-8")
    assert "--out-dir ../../run_artifacts/predeadline_field_eo" in workflow
    assert 'args.out_dir / "predeadline_field_eo.csv"' in capture_script
    assert 'args.out_dir / "predeadline_field_report.json"' in capture_script
    assert "run_artifacts/predeadline_field_eo/predeadline_field_eo.csv" in workflow
    assert "run_artifacts/predeadline_field_eo/predeadline_field_report.json" in workflow
    assert "name: provisional-field-eo-${{ github.run_id }}" in workflow


def test_official_manager_reconciliation_accepts_public_manager_input_and_uses_new_artifact_name():
    path = ROOT / ".github/workflows/reconcile-official-fpl-manager.yml"
    workflow = path.read_text(encoding="utf-8")
    validate = workflow.index("Validate requested Gameweeks and optional decision-evidence scope")
    checkout = workflow.index("Check out M3 branch")
    reconcile = workflow.index("Capture and reconcile requested completed Gameweeks")
    upload = workflow.index("Upload immutable batch evidence")
    assert validate < checkout < reconcile < upload
    assert "manager_team_id:" in workflow
    assert 'default: "421025"' in workflow
    assert "MANAGER_TEAM_ID: ${{ inputs.manager_team_id }}" in workflow
    assert "secrets.M3_MANAGER_TEAM_ID" not in workflow
    assert "Refuse personal reconciliation in a public repository" not in workflow
    assert "name: predeadline-decision-evidence-manager-${{ inputs.manager_team_id }}-gw${{ inputs.gameweeks }}-run${{ inputs.decision_evidence_run_id }}" in workflow
    assert "name: official-fpl-reconciliation-batch-${{ github.run_id }}" in workflow
    assert 'TARGET_GAMEWEEKS: ${{ inputs.gameweeks }}' in workflow
    assert '--gameweeks "$TARGET_GAMEWEEKS"' in workflow
    assert '--gameweeks "${{ inputs.gameweeks }}"' not in workflow
    assert 'if [[ "${{ inputs.gameweeks }}"' not in workflow



def test_fpl_lucho_one_shot_workflow_checks_deadline_and_emits_only_safe_summary():
    workflow_path = ROOT / ".github/workflows/capture-fpl-lucho-benchmark.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    capture_script = (
        ROOT / "canonical_candidate/engineering_workbench/scripts/capture_fpl_lucho_raw.py"
    ).read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert 'default: "2026-27"' in workflow
    assert 'default: "12"' in workflow
    assert "capture_fpl_lucho_raw.py" in workflow
    assert "summarize_provider_capture.py" in workflow
    assert '--provider "FPL Lucho"' in workflow
    assert "artifacts/provider-summary/fpl-lucho.json" in workflow
    assert "Upload sanitized schema and provenance summary only" in workflow
    assert "retention-days: 90" in workflow
    upload_block = workflow.split("uses: actions/upload-artifact@v4", 1)[1]
    assert "artifacts/provider-summary/fpl-lucho.json" in upload_block
    assert "artifacts/fpl_lucho/" not in upload_block
    assert "csv_captured_at_utc" in capture_script
    assert "FPL Lucho release or capture is at or after the official deadline" in capture_script
    assert "raw_archives" in capture_script
