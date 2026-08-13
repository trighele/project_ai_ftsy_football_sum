# 01 — Publish the image to GHCR under the new name and tag rules

**What to build:** Pushing to `main` publishes a container image the Unraid box can pull, and running the workflow by hand publishes a build that cannot reach the live app.

A push to `main` builds the image on GitHub's hosted runners and publishes it as `ghcr.io/<owner>/ffsum` under two tags: `latest`, which is what the box follows, and a commit-sha tag, which is what you pin to when a deploy goes wrong. A manual `workflow_dispatch` run publishes the same image under a dated development tag carrying the commit sha — `dev-<YYYYMMDD>-<sha>` — and under nothing else. `latest` moves on a merge to `main` and at no other time, so the live application can never be running code that is not on the main branch.

The tag rules are expressed declaratively, gated on the triggering event, rather than computed in a shell conditional. This is a deliberate choice: the safety property is the whole point of the ticket, and it should be confirmable by reading the workflow rather than by trusting a script. Builds reuse a dependency cache between runs, so a change to application code does not re-download every wheel on a cold hosted runner.

**Blocked by:** None — can start immediately.

**Status:** ready-for-human

- [x] The workflow runs on GitHub's hosted runners and needs nothing from the maintainer's hardware
- [ ] A push to `main` publishes `ghcr.io/<owner>/ffsum:latest` — written, unproven until a merge (see Notes)
- [ ] A push to `main` also publishes a distinct commit-sha tag for the same build — written, unproven until a merge
- [x] A `workflow_dispatch` run publishes `dev-<YYYYMMDD>-<sha>` and no other tag
- [x] A `workflow_dispatch` run leaves `latest` pointing where it was
- [x] Two `workflow_dispatch` runs on the same day produce two distinct tags — for two distinct commits; see Comments
- [x] Which tags are written on which trigger is readable from the workflow file without tracing shell logic
- [x] A build whose dependencies are unchanged reuses the cached dependency layer
- [x] The workflow needs no registry credential beyond the token GitHub Actions already provides
- [x] `uv run pytest` still passes; no application code changed

## Notes

The `workflow_dispatch` half is verifiable from a feature branch right now. The `latest` half only proves itself on a merge to `main` — do not mark that criterion met on the strength of a dry read of the file.

The old Kubernetes workflow is left in place by this ticket. It is `workflow_dispatch`-only and cannot fire on its own, so the two coexist harmlessly until ticket 04 removes it.

## Comments

**Implemented** — `.github/workflows/deploy-v2.yml` rewritten; `.claude/CLAUDE.md`'s CI paragraph updated to describe the new tag rules. `uv run pytest`: 212 passed. No application code touched.

The tag rules are one `docker/metadata-action` block, each entry gated on `github.event_name`, with `flavor: latest=false` so the only `latest` in the file is the push-gated one. Verified against the action's README: `enable` is a common attribute valid on every tag type and defaults to `true`; `type=raw` expands the handlebars globals, so `dev-{{date 'YYYYMMDD'}}-{{sha}}` resolves to e.g. `dev-20260813-a1b2c3d`; `{{sha}}` is the 7-char short sha.

**One gap in the spec's dev-tag format, for the author rather than a silent patch.** `dev-<YYYYMMDD>-<sha>` discriminates two same-day dispatches only when the *commit* differs. Re-dispatching an unchanged branch — a retry after a transient registry or build failure — produces the identical tag and the second push moves it, which is the exact failure "Why the dev tag carries the sha as well as the date" was written to prevent. The format as specified is implemented faithfully; closing the gap needs `{{sha}}` plus `github.run_id` or a timestamp. Low stakes: nothing follows dev tags.

**Deliberately not added:** a `concurrency:` group. Two merges to `main` in quick succession race, and the slower build wins `latest`. Not in this ticket's scope, and the spec's rollback answer is a manual re-point at a `sha-` tag, so it is survivable — noting it rather than expanding scope.

**Also present but not requested:** `labels: ${{ steps.meta.outputs.labels }}` on the build step. Kept because the OCI labels link the GHCR package back to this repo, which helps when the package is made public in ticket 02.
