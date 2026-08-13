# 01 — Publish the image to GHCR under the new name and tag rules

**What to build:** Pushing to `main` publishes a container image the Unraid box can pull, and running the workflow by hand publishes a build that cannot reach the live app.

A push to `main` builds the image on GitHub's hosted runners and publishes it as `ghcr.io/<owner>/ffsum` under two tags: `latest`, which is what the box follows, and a commit-sha tag, which is what you pin to when a deploy goes wrong. A manual `workflow_dispatch` run publishes the same image under a dated development tag carrying the commit sha — `dev-<YYYYMMDD>-<sha>` — and under nothing else. `latest` moves on a merge to `main` and at no other time, so the live application can never be running code that is not on the main branch.

The tag rules are expressed declaratively, gated on the triggering event, rather than computed in a shell conditional. This is a deliberate choice: the safety property is the whole point of the ticket, and it should be confirmable by reading the workflow rather than by trusting a script. Builds reuse a dependency cache between runs, so a change to application code does not re-download every wheel on a cold hosted runner.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] The workflow runs on GitHub's hosted runners and needs nothing from the maintainer's hardware
- [ ] A push to `main` publishes `ghcr.io/<owner>/ffsum:latest`
- [ ] A push to `main` also publishes a distinct commit-sha tag for the same build
- [ ] A `workflow_dispatch` run publishes `dev-<YYYYMMDD>-<sha>` and no other tag
- [ ] A `workflow_dispatch` run leaves `latest` pointing where it was
- [ ] Two `workflow_dispatch` runs on the same day produce two distinct tags
- [ ] Which tags are written on which trigger is readable from the workflow file without tracing shell logic
- [ ] A build whose dependencies are unchanged reuses the cached dependency layer
- [ ] The workflow needs no registry credential beyond the token GitHub Actions already provides
- [ ] `uv run pytest` still passes; no application code changed

## Notes

The `workflow_dispatch` half is verifiable from a feature branch right now. The `latest` half only proves itself on a merge to `main` — do not mark that criterion met on the strength of a dry read of the file.

The old Kubernetes workflow is left in place by this ticket. It is `workflow_dispatch`-only and cannot fire on its own, so the two coexist harmlessly until ticket 04 removes it.

## Comments
