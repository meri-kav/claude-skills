# Gates per repo: what `run_gates.py` does not cover

The script handles enumeration, exit codes, per-commit comment ratio, baseline scans one at a
time, and the type check last. What stays a judgment call is below.

## pacific-server

- **Tests:** after the gates, run the test files of the touched modules. When an ORM model or
  migration changed, also `pytest alembic/`. Setting `DATABASE_URL` un-skips tests from other
  areas; a narrow run failing where a full run passes is that.
- **Checks that are not required but still count:** Integration Tests, Tests (platform),
  Tests (coverage), lint, check-connector-safeguards, check-release-tooling.
- **Known flakes** (`pr.py wait` reruns the GitHub Actions ones once):
  - The connector-policy shard dies on its 900s deadline.
  - A CANCELLED check-connector-safeguards is the self-hosted runner's 10-minute checkout.
  - "mocked coverage was not published after 600s" means a unit shard died. Fix that shard
    and both go green.
  - A red on every shard at `build-base` is a CI bug from main.
- **Stacked PRs** get a reduced check set, and the gate base is the PR's base.
- **Red on main:**
  - `check-tenant-setting-coverage` since 2026-09-18.
  - `check-acl-freshness-declared` fails locally with "RETRIEVAL_CONFIG_FILE_NAME is unset" (seen
    2026-09-24). It looks like missing local setup, but that is not proven.

  Recheck either one on a main worktree before calling it already there.

## pacific-site

- Build test fixtures from the generated enums, never the string literal.
- Design and UI consistency run in CI but are not required.
