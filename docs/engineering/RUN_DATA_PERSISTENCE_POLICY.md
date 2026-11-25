# Run data persistence and resume policy

This policy applies to every research, audit, training, evaluation, and inference workflow in this repository.

## Default rule

A run must not discard expensive downloaded source files or completed intermediate work merely because a later step times out or fails. Before starting an expensive operation, restore and validate reusable inputs from a prior run. Reuse them by default; download only missing, corrupt, or version-mismatched files.

## Required workflow design

1. **Inventory expensive inputs first.** Identify external repositories, API downloads, archives, model weights, feature stores, and costly intermediate outputs before launching a run.
2. **Pin cache identity.** Cache keys must include the relevant source repository/ref or commit, data schema/version, and builder version. Never reuse data across incompatible pins.
3. **Restore before downloading.** Restore caches before any download/build step. Validate manifests, file hashes where available, expected paths, and source pins.
4. **Checkpoint before expensive downstream work.** Do not rely only on an end-of-job `if: always()` cache-save step: a hard job timeout can prevent it from running. Split long workflows into stages/jobs so completed downloads are saved before feature reconstruction, training, or evaluation begins. For long downloads, checkpoint in bounded batches where practical.
5. **Save partial progress safely.** Persist successfully completed files and a manifest after each completed download batch. A failed/incomplete file must not be marked complete. The next run resumes missing items rather than restarting the whole download.
6. **Persist useful intermediates.** Save expensive validated intermediate datasets/artifacts separately from raw-source caches when they can be reused safely.
7. **Keep outputs and caches distinct.** Caches are reusable inputs, not the authoritative experiment record. Upload final reports, manifests, logs, and model outputs as run artifacts with clear provenance.
8. **Make cache misses visible.** Report cache hit/miss, restored file counts, newly downloaded files, skipped files, validation failures, and source/version identifiers in the run summary.
9. **Never weaken data integrity.** Reuse only files that pass validation. Re-download a missing, corrupt, incomplete, expired, or pin-mismatched file. Do not let caching bypass point-in-time, label-sealing, or source-vintage controls.
10. **Review existing workflows.** When modifying or launching a workflow, inspect whether expensive inputs already have persistence and resume support. Add it when absent before starting another costly run.

## Timeout recovery

When a run fails or times out, first inspect its saved caches, manifests, artifacts, and logs. The next run must restore and inspect those files before downloading anything. Do not repeat a full download simply because the previous job did not reach its final modeling step.

## GitHub Actions implementation guidance

Use `actions/cache/restore@v4` before expensive downloads and `actions/cache/save@v4` at explicit checkpoints. Prefer immutable, source-pinned cache keys with restore prefixes for compatible prior checkpoints. For work that can exceed a job timeout, put download/checkpoint and downstream build/training into separate jobs or workflows so the cache is committed before the long downstream stage starts. Cache eviction is possible, so retain critical intermediate artifacts in durable workflow artifacts or repository-managed storage when necessary.
