# Changelog

## v1.0.1 - CI and runtime artefact hygiene patch

### Fixed

- Restored GitHub Actions verification after the UI build ordering change.
- Made Python UI build verification POSIX-portable by removing `shell=True` npm subprocess calls.
- Centralised npm build execution through shell-free helpers in `mcp/test_verify.py`.
- Ensured UI build tests run `npm ci` when `node_modules` is missing instead of skipping.
- Removed generated pending-change JSON runtime artefacts from version control.
- Ignored generated pending-change runtime output under `Vault Files/State/pending-changes/`.
- Updated the mutating feedback write test so `feedback.md` is snapshotted and restored.

### Verification

Verified with:

```bash
python mcp/test_verify.py
python run.py validate
python run.py security
python run.py feedback
python run.py export --overwrite
cd ui && npm run build
```

Expected result:

- 695 verification tests pass.
- Vault validation passes.
- Security scan exits successfully.
- Feedback command exits successfully.
- Export command writes package output successfully.
- UI build completes successfully.
- GitHub Actions verify workflow passes.

### Known limitations

- Registry and Reuse Layer remains deferred.
- Optional Semantic Retrieval remains deferred.
- Autonomous note writing is not enabled.
- Pending memory changes remain human-reviewed before acceptance.
