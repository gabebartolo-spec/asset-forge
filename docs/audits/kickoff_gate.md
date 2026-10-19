# Kickoff gate: CI proven to reject planted defects

Date: 2026-10-20. Signer: lead. Main at `78201b1`; required checks `test`, `doc-caps`, `gitleaks`.

Each defect went in its own throwaway PR from `origin/main`, with only that defect, checked
locally first, and was closed unmerged after it went red.

| Planted defect | PR | Run | Failing job / step | Proof in the log |
|---|---|---|---|---|
| Failing unit test (`assert 1 == 2`) | #1 | 39259120820 | `test` / Unit tests | `AssertionError: planted failure for the Phase 0 gate` |
| Ruff error (unused `import os`) | #2 | 39259129361 | `test` / Ruff | `F401 os imported but unused`, `Found 1 error.` |
| Fake secret `FORGE_TEST_SECRET_` + 16 | #3 | 39259134246 | `gitleaks` | `RuleID: forge-test-secret`, `leaks found: 1` |

In each PR every other check passed, so each red came from its planted defect alone.

Verdict: Phase 0 gate (CI rejects a failing test, a lint error and a secret) **met**.
