# Publish to GHCR, deploy via Watchtower on Unraid, no orchestrator

This app runs as one process against one SQLite file for one person. It used to run on a shared Kubernetes cluster; we now publish `ghcr.io/trighele/ffsum:latest` from CI on every merge to `main`, and Watchtower — already running on the maintainer's Unraid box — notices the new digest and restarts the container on its own poll interval. There is no orchestrator, no deploy step in CI, and nothing in the pipeline that touches the box directly: a merge to `main` is the whole deploy.

## Considered Options

- **Keep the Kubernetes deployment.** Rejected: the cluster is shared infrastructure for other applications, and a namespace, Deployment, Service, and PVC is more machinery than a single container with a single bind-mounted volume needs. It also meant the runtime definition — three non-interchangeable ports, a ConfigMap, a Secret — lived in manifests this repo carried, but a human still had to `kubectl apply` them by hand.
- **A CI step that SSHes into the box and runs `docker compose pull && up`.** Rejected: it means shipping SSH credentials to GitHub Actions and opening the box to inbound automation from a third party, to solve a problem Watchtower already solves by polling outward on its own schedule.

## Consequences

- There is no declarative record of the running system. The container's image, port mapping, volume mount, and environment variables exist only in Unraid's Docker template UI, which this repo cannot see or version — `.claude/CLAUDE.md`'s Deployment section is the closest thing to a record, and it has to be kept in sync by hand.
- There is no rollout status and no readiness gate. Watchtower restarts the container on its own poll interval; nothing confirms the new image is healthy before the old one is gone, and nothing reports back here when it happens.
- There is no rollback beyond re-pointing the Unraid template's image field at an older `sha-` tag by hand and letting Watchtower, or a manual restart, pick it up. There is no automated revert.
- For one process and one SQLite file serving one person, this is the right trade — the machinery removed cost more than the guarantees it bought. It is still a trade, which is why it is recorded here rather than left implicit.
