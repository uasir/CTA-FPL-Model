from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = {
    "fplcat": ROOT / ".github/workflows/capture-fplcat-benchmark.yml",
    "sidelinequant": ROOT / ".github/workflows/capture-sidelinequant-benchmark.yml",
    "fplrogue": ROOT / ".github/workflows/capture-fplrogue-benchmark.yml",
}


def test_public_provider_workflows_upload_metadata_summaries_only():
    for provider, path in WORKFLOWS.items():
        workflow = path.read_text(encoding="utf-8")
        assert "Create metadata-only public summary" in workflow, provider
        assert "Upload metadata-only capture summary" in workflow, provider
        assert "artifacts/provider-summary/" in workflow, provider
        assert "retention-days: 90" in workflow, provider
        # Raw capture paths may be used inside the ephemeral runner, but never
        # as the upload-artifact path in this public repository.
        upload_block = workflow.split("uses: actions/upload-artifact@v4", 1)[1]
        artifact_path_line = next(
            line.strip() for line in upload_block.splitlines()
            if line.strip().startswith("path:")
        )
        assert "artifacts/provider-summary/" in artifact_path_line, provider
        assert f"artifacts/{provider}/" not in artifact_path_line, provider


def test_wildcard_has_no_public_capture_workflow():
    assert not (ROOT / ".github/workflows/capture-fplwildcard-benchmark.yml").exists()



def test_personal_m3_workflow_accepts_public_manager_inputs_and_preserves_evidence_checks():
    path = ROOT / ".github/workflows/capture-predeadline-decision-evidence.yml"
    workflow = path.read_text(encoding="utf-8")
    checkout = workflow.index("Check out M3 implementation")
    capture = workflow.index("Capture and seal pre-deadline decision evidence")
    upload = workflow.index("Upload pre-deadline decision evidence and recommendation")
    assert checkout < capture < upload
    assert "manager_team_id:" in workflow
    assert "manager_state_json:" in workflow
    assert "season:" in workflow
    assert "MANAGER_TEAM_ID: ${{ inputs.manager_team_id }}" in workflow
    assert "MANAGER_STATE_JSON: ${{ inputs.manager_state_json }}" in workflow
    assert "SEASON: ${{ inputs.season }}" in workflow
    assert "secrets.M3_" not in workflow
    assert "Refuse personal decision capture in a public repository" not in workflow
    assert "name: predeadline-decision-evidence-manager-${{ inputs.manager_team_id }}-gw${{ inputs.gameweek }}-run${{ github.run_id }}" in workflow
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
    assert "MANAGER_TEAM_ID: ${{ inputs.manager_team_id }}" in workflow
    assert "secrets.M3_MANAGER_TEAM_ID" not in workflow
    assert "Refuse personal reconciliation in a public repository" not in workflow
    assert "name: predeadline-decision-evidence-manager-${{ inputs.manager_team_id }}-gw${{ inputs.gameweeks }}-run${{ inputs.decision_evidence_run_id }}" in workflow
    assert "name: official-fpl-reconciliation-batch-${{ github.run_id }}" in workflow
    assert 'TARGET_GAMEWEEKS: ${{ inputs.gameweeks }}' in workflow
    assert '--gameweeks "$TARGET_GAMEWEEKS"' in workflow
    assert '--gameweeks "${{ inputs.gameweeks }}"' not in workflow
    assert 'if [[ "${{ inputs.gameweeks }}"' not in workflow
