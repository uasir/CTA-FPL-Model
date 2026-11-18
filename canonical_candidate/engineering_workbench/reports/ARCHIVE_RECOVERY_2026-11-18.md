# CTA-FPL source archive recovery — 2026-11-18

## Recovery result

The five original recovery ZIP archives are present in the local working environment. Each was opened successfully, passed `ZipFile.testzip()` with no corrupt member, and its SHA-256 matched the durable manifest in `PROJECT_STATE_2026-11-15.md`.

| Original archive | Entries | SHA-256 | ZIP integrity |
|---|---:|---|---|
| `CTA_FPL_reconstruction_scaffold_v0_1.zip` | 20 | `b96b6e3c3ef04b4e12d5d153f4f381843f4ecc2e48f0ae54d41d4ec14c1d6dc1` | PASS |
| `CTA-FPL-Engineering-Workbench.zip` | 44 | `b7e62bec4299a63fb06d72e7bc38f54f2726ea68f366a29b4e3f64607f6e4630` | PASS |
| `CTA_FPL_Model_v1_0_2_Engineering_Build.zip` | 15 | `7c8960ef250472eb2bb57b3d82f4ebec8dec00096482307470aedecb40cf5a73` | PASS |
| `CTA_FPL_Model_v1_0_1_Engineering_Fix.zip` | 21 | `2c000b3c3f84bf1197303013d0d21e402b01d8ebfbddef3aa6558cfc50ab7553` | PASS |
| `CTA_FPL_Model_v1_0_Experimental.zip` | 11 | `2d8278b593165b2bad7d55ee50969d166070e8872288a7fc59d07976ae17d749` | PASS |

## Lineage and separation

1. `CTA_FPL_Model_v1_0_Experimental.zip` is the initial v1.0 experimental pipeline.
2. `CTA_FPL_Model_v1_0_1_Engineering_Fix.zip` contains the sparse-row CSV writer correction.
3. `CTA_FPL_Model_v1_0_2_Engineering_Build.zip` builds on v1.0.1 and adds StatsBomb possession-oriented direction defaults and rejection of false direction overrides.
4. `CTA-FPL-Engineering-Workbench.zip` is a separate companion package for Python–JavaScript parity, raw-data contracts, and exploratory xT. It is not a replacement for the model archive.
5. `CTA_FPL_reconstruction_scaffold_v0_1.zip` is an earlier minimal scaffold.

The independent workspace ZIP from 2026-11-17 and the candidate bundle from 2026-11-15 are later working snapshots, not replacements for the original archives. Both also pass ZIP integrity checks:

- `CTA_FPL_INDEPENDENT_WORKSPACE_2026-11-17.zip`: 118 entries; SHA-256 `c482a282466e36d6eaa8f42f724e0103a29390954b2342d64a855714b6abb7c4`.
- `CTA_FPL_Candidate_v1_0_2_plus_Workbench_2026-11-15.zip`: 70 entries; SHA-256 `ad4334228574ccfcc4bdfb6d3d4f7160a680837d58b92147d63b88ecda8b6305`.

## Canonical source comparison

The v1.0.2 archive's `src/cta_engine.py` SHA-256 is `63684622b00ffd52759af2b42c6483e18bf93d1fde2dc652c23002ca5544770f`.

The 2026-11-17 independent workspace contains a later `canonical_candidate/src/cta_engine.py` snapshot with SHA-256 `9c44115937c4fc1ae9f2eafeecdb36ac71cd25a39dea77b2f72eba72615ed19e`. Compared with the v1.0.2 archive, it includes:
- match-scoped `(match_id, event_uuid)` 360 linkage auditing;
- a stable player feature row builder with explicit zero counters and blank denominators for non-estimable per-90 metrics.

The GitHub `main` version at commit `d9f3f4a61525ae4b3bacd358f50a3c7cec5ce4e3` is v1.0.3 experimental and has Git blob SHA `74bd6665b8160fece18166b6f76043245792372a`. It is not byte-identical to the independent workspace file. The match-scoped 360 audit is being ported selectively with paired Python/JavaScript regression tests in PR #12; do not overwrite the repository's canonical engine with an archive copy.

## Preservation policy

- Keep all original archives unchanged.
- Treat the v1.0.2 model and Workbench as separate components.
- Treat later workspace ZIPs as evidence/snapshots, not canonical source-of-truth replacements.
- Port changes selectively, with Python and JavaScript tests and explicit schema/identity review.
- Do not treat synthetic smoke tests as real-match validation or FPL predictive validation.
