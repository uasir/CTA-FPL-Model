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
