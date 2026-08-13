# Ship to GHCR, run on Unraid

Status: ready-for-agent

## Problem Statement

Deploying this app costs more than the app is worth.

To put a change in front of himself, the maintainer currently needs a self-hosted GitHub Actions runner, a `kind` cluster, four Kubernetes manifests, a Namespace, a Service, a PersistentVolumeClaim, a systemd port-forward unit, and three separate port numbers that are not interchangeable and are recorded in a workflow `env:` block that nothing reads. The workflow that drives all of it is `workflow_dispatch`-only, so nothing happens automatically. This is a single-user application that summarizes podcast episodes, holds one SQLite file, and runs one process in one container. None of that machinery earns its place.

The layer of it that fails is the layer nobody looks at. A port mapping spread across a Deployment, a Service, and a systemd unit has three places to be wrong and one symptom. A `Recreate` strategy exists only because a ReadWriteOnce volume cannot be held by two pods — a constraint invented entirely by the orchestrator, for a workload that was never going to have two pods.

Separately, `.github/workflows/deploy-v2.yml` already exists and already pushes an image to GHCR on a push to `main`. Nothing pulls that image. It is a build without a deploy, sitting alongside a deploy that has to be triggered by hand.

## Solution

GitHub Actions' job ends at the registry, and the box takes over from there.

A push to `main` builds the image on `ubuntu-latest` and pushes `ghcr.io/trighele/ffsum:latest`. Watchtower — already running on the maintainer's Unraid box — notices the digest has moved and restarts the container. There is no orchestrator, no deploy step in CI, and nothing in the pipeline that touches the maintainer's hardware. The container itself is defined once, in Unraid's Docker template UI, mapping host port 4301 to the container's 8000 and the host path `/mnt/user/appdata/ffsum` to `/data`.

A manual `workflow_dispatch` run builds and publishes too, but under a dated development tag that Watchtower is not watching — so a branch can be built and pulled deliberately without ever reaching the live app.

The trade being made explicitly: the maintainer gives up declarative rollout control and rollback-by-manifest, and gets a deployment that fits in his head and has one place to be wrong.

## User Stories

1. As the maintainer, I want a push to `main` to build and publish the image automatically, so that shipping a change does not require me to remember to trigger anything.
2. As the maintainer, I want the running container to update itself once a new image is published, so that publishing and deploying are one action rather than two.
3. As the maintainer, I want the deployment to involve no Kubernetes, so that the failure surface is a container and a port rather than a cluster.
4. As the maintainer, I want the image published under a short, stable name, so that the thing I type into Unraid matches what I call the app.
5. As the maintainer, I want every build from `main` tagged with its commit, so that I can pin the container to a known-good build when a deploy goes wrong.
6. As the maintainer, I want `latest` to move only on a push to `main`, so that the live app can never be running code that is not on the main branch.
7. As the maintainer, I want a manual workflow run to publish under a dated development tag, so that I can build and try a branch's image without deploying it.
8. As the maintainer, I want two manual runs on the same day to produce two distinct tags, so that the second build cannot silently overwrite the first.
9. As the maintainer, I want the tag rules to be legible in the workflow file itself, so that I can confirm the safety property by reading rather than by testing.
10. As the maintainer, I want the published package to be public, so that neither the box nor Watchtower needs a registry credential that can expire.
11. As the maintainer, I want the build to reuse a dependency cache between runs, so that a change to application code does not re-download every wheel.
12. As the maintainer, I want the build to run on GitHub's hosted runners, so that publishing a change does not depend on my box being awake.
13. As the maintainer, I want saved runs and the cached player reference to live on the Unraid array at a path I can open, so that I can back them up and inspect them without entering a container.
14. As the maintainer, I want the data path to be the one my existing appdata backup already covers, so that persistence is not a separate thing to remember.
15. As the maintainer, I want `ANTHROPIC_API_KEY` supplied as an Unraid template variable, so that no secret is ever committed to this repository.
16. As the maintainer, I want the app reachable on a single host port, so that there is one number to remember instead of three.
17. As the maintainer, I want the Kubernetes manifests and their workflow deleted, so that the repository does not describe infrastructure the app no longer uses.
18. As the maintainer, I want the shared `kind` cluster left running, so that the other applications deployed to it are unaffected by this change.
19. As the maintainer, I want the exact Unraid template settings recorded in the repository, so that the only copy of my deployment is not a web form on one machine.
20. As the maintainer, I want the exported Unraid template XML committed, so that rebuilding the container is a re-import rather than a reconstruction from memory.
21. As the maintainer, I want the local Compose file to keep building from source, so that I can still run the real image locally before it ships.
22. As the maintainer, I want the local Compose port to stay distinct from the deployed port, so that a local run cannot collide with the deployed one.
23. As the maintainer, I want the documentation to stop describing a Service, a PersistentVolumeClaim, and a three-port chain, so that a future reader is not told about infrastructure that no longer exists.
24. As the maintainer, I want the dangling ADR citations in the guidance file resolved, so that following a reference does not lead to a deleted file.
25. As the maintainer, I want the decision to run without an orchestrator recorded as an ADR, so that a future reader understands it was a choice rather than an oversight.
26. As the maintainer, I want the domain glossary left untouched, so that it stays a glossary of the domain rather than a record of infrastructure.
27. As the maintainer, I want a run interrupted by a Watchtower restart to tell me it was lost, so that the page does not sit forever on a stage that will never advance.
28. As the maintainer, I want the Summarize button re-enabled after an interrupted run, so that I can retry immediately without reloading.
29. As the maintainer, I want the test suite to remain the whole gate and to stay green, so that this change is verifiably confined to deployment.
30. As the maintainer, I want no application code changed by this work, so that a regression in summarizing is not a possible outcome of a deployment change.

## Implementation Decisions

**The build workflow.** `.github/workflows/deploy-v2.yml` is rewritten and keeps its two triggers: push to `main`, and `workflow_dispatch`. It runs on `ubuntu-latest` with `contents: read` and `packages: write`. It logs in to `ghcr.io` with `GITHUB_TOKEN` and builds with `docker/build-push-action`.

**Tag computation is declarative, not shell.** Tags come from `docker/metadata-action`, with each tag gated on `github.event_name`. A push to `main` produces `latest` and a commit-sha tag; a `workflow_dispatch` run produces `dev-<YYYYMMDD>-<sha>` and nothing else. This shape was chosen specifically so the safety property — a manual run can never move `latest` — is readable in the workflow file rather than buried in a shell conditional. See Testing Decisions.

**Why the dev tag carries the sha as well as the date.** Two dispatches on the same day would otherwise resolve to one tag, and the second push would silently move it.

**Why a manual run must never write `latest`.** Watchtower watches `latest`. If a dispatch wrote it, an unmerged branch would reach the live application within one poll interval, with no log line explaining why.

**Build cache.** `docker/setup-buildx-action` is added — it is required for the GitHub Actions cache backend — and the build uses `cache-from`/`cache-to` with `type=gha`. Without it, every push re-runs the image's dependency layer from cold on a hosted runner.

**The published image.** `ghcr.io/<owner>/ffsum`, replacing the `project-ai-ftsy-football-sum` name that existed only to namespace a cluster. The GHCR package is made public after the first push. The image contains application code and pure-Python wheels; no credential is baked into it, and `ANTHROPIC_API_KEY` arrives at runtime. Public removes a credential, a rotation, and the failure mode where Watchtower silently stops updating because a token expired.

**The runtime.** An Unraid Docker template, configured in the Unraid UI. It maps host `4301` to container `8000`, host path `/mnt/user/appdata/ffsum` to `/data`, and supplies `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, and `FFSUM_DATA_DIR` as template variables. A host path is used rather than a named Docker volume so the SQLite file is openable from the array and is covered by the existing appdata backup, instead of being hidden inside `docker.img`.

**Watchtower.** Already installed and running on the box; its polling schedule is left as-is. If it is label-scoped rather than global, the template's Extra Parameters must carry `--label com.centurylinklabs.watchtower.enable=true`. This is a maintainer action, not a repository change.

**The Dockerfile is unchanged** apart from a comment. It already sets `FFSUM_DATA_DIR=/data`, `HOST=0.0.0.0`, `PORT=8000`, and declares the volume — every fact the Unraid template depends on is already true.

**Kubernetes artefacts are deleted:** `deployment/` (namespace, deployment, service, PVC) and `.github/workflows/deployment.yml`. The `kind` cluster itself is **not** torn down — other applications run on it. The consequence is accepted and recorded rather than resolved: until the maintainer retires the namespace, the old copy keeps serving on port 4012 against its own SQLite database while the new one serves 4301. Two live copies, two databases.

**No data migration.** The existing PVC contents are abandoned. The cached player reference re-syncs within its 12-hour TTL or on demand, and saved runs are re-runnable from their source URLs.

**Compose is unchanged in behaviour.** `docker-compose.yml` stays the build-from-source local file on host port 9193 — deliberately distinct from 4301 so a local run cannot collide with the deployed one. Only its comment referencing the PersistentVolumeClaim changes.

**Documentation.** The guidance file's Deployment section is rewritten to enumerate the Unraid template fields, since the runtime definition otherwise exists only in a web form. The "three ports" paragraph is removed along with the Service that invented the middle number. The scattered Kubernetes references in the commands block, the CI paragraph, and the environment-variable section are corrected. `README.md` is corrected in three places: the environment-variable prose, the Compose URL line, and the `deployment/` entry in the directory tree.

**ADRs.** `docs/adr/` is recreated with one ADR recording the decision to publish to GHCR and run on Unraid with no orchestrator. It qualifies on all three counts: meaningfully hard to reverse, surprising without context (a containerized app with persistent state and no orchestrator), and the result of a real trade-off. The three dangling ADR-0001/0002/0003 citations in the guidance file — dangling since `docs/` was deleted — are resolved by stating those facts inline and citing only the new ADR.

**`CONTEXT.md` is not modified.** Deployment vocabulary is not domain language; that file is a glossary of the domain and nothing else.

**Once the container exists**, the maintainer exports the Unraid template XML from `/boot/config/plugins/dockerMan/templates-user/` and it is committed, so rebuilding the container is a re-import.

## Testing Decisions

**A good test here tests behaviour a user could observe.** No application code is modified by this work, so there is no new observable behaviour to cover. The existing test suite is the regression guard: `uv run pytest` must remain green, unchanged, proving the change is confined to deployment.

**No new test seam is added.** The one rule with a real blast radius — a manual run must never move `latest` — was considered for a test that parses the workflow YAML. It is deliberately not written, for two reasons. First, the tag logic is expressed declaratively through `docker/metadata-action`, so the rule is three readable lines rather than shell control flow; a test asserting it would restate the file. Second, a test that parses a `run:` script can only assert on its text, so it would pass while the shell was subtly wrong — the least useful kind of test. Choosing the declarative form *instead of* writing the test is the testing decision.

**This keeps the seam count at one.** The repository tests the application through `TestClient` at the HTTP boundary, with edge fakes registered on the container. `tests/test_youtube_source.py` is the single existing exception, and it exists only because the yt-dlp metadata lookup is invisible from outside the app. A YAML-parsing test would introduce a second exception and pull `pyyaml` into the dev group to do it — cost paid against a test that could not fail correctly.

**Watchtower's restart behaviour needs no new coverage.** A container restart mid-run already degrades correctly: `static/js/run.js` handles the `EventSource` error by reporting that contact with the run was lost and re-enabling the Summarize button. This is existing, verified behaviour that Watchtower exercises more often rather than differently.

**Nothing is asserted about the Unraid template**, which is configured by hand on a machine CI cannot reach. Its correctness is established by the app answering on port 4301 after the first deploy.

## Out of Scope

- Tearing down the `kind` cluster, its namespace, the systemd port-forward unit, or the self-hosted runner registration. The cluster is shared with other applications and stays up; the maintainer will retire this app's namespace on his own schedule.
- Migrating saved runs or the cached player reference off the existing PersistentVolumeClaim.
- Any change to application code, templates, stylesheets, or the test suite.
- Installing or reconfiguring Watchtower, including its polling interval and image cleanup.
- Restricting Watchtower to an overnight update window. Deliberately declined: re-running an interrupted episode costs one paste, and a schedule adds a thing that can be misconfigured silently.
- Adding a `HEALTHCHECK` to the image, or a health endpoint to the app.
- Any rollback automation. Rollback is a manual re-point of the Unraid template at a `sha-` tag.
- Restoring the three ADRs deleted in `4672a61`. Their claims are stated inline instead.
- Preserving the host port `4012`. The deployed app moves to `4301`; anything pointing at the old port is the maintainer's to update.

## Further Notes

**The port change is a cutover, not a rename.** Bookmarks, reverse-proxy entries, and phone shortcuts pointing at 4012 will not follow the app to 4301. This was raised during design and confirmed as intentional.

**The maintainer holds three actions CI cannot perform:** making the GHCR package public after the first push, creating the Unraid template, and confirming whether Watchtower is label-scoped. Until the first is done, Watchtower cannot pull; until the third is confirmed, it may not be watching this container at all.

**The template XML cannot be committed in the same pass** as the rest of this work — it does not exist until the container is created on the box. Until it lands, the guidance file's field list is the only record of how the app runs.

**What this gives up, stated plainly:** there is no declarative record of the running system, no rollout status to watch, no readiness gate, and no way to roll back other than editing a form. For a single-user application with one process and one SQLite file, that is the correct trade — but it is a trade, which is why it is recorded as an ADR.
