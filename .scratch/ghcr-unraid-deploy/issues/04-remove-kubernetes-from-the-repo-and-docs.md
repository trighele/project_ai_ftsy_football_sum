# 04 — Remove Kubernetes from the repo and the docs

**What to build:** The repository describes the deployment that exists, and stops describing the one it doesn't.

The Kubernetes manifests and the workflow that applied them are deleted. Everything that referred to them is corrected in the same change, so there is no moment where the documentation describes files that are gone: the guidance file's Deployment section is rewritten around the Unraid template's actual fields, the paragraph explaining the three non-interchangeable ports is removed along with the Service that invented the middle one, and the scattered Kubernetes references in the commands block, the CI paragraph, and the environment-variable section are corrected. The README is fixed in three places — the environment-variable prose, the line naming the Compose URL, and the `deployment/` entry in its directory tree. The comments in the Dockerfile and the Compose file that point at a PersistentVolumeClaim are rewritten to point at what actually mounts the volume now.

Because the runtime definition lives only in a web form on one machine, the guidance file's Deployment section has to carry the template's fields explicitly — image, port mapping, path mapping, and every environment variable. Without that, the only record of how this app runs is a UI page.

**Blocked by:** 03 — Watchtower deploys the next push by itself. Not a technical gate: deleting these files cannot affect the running cluster. It is a judgment gate — the description of the working path stays until the replacement has demonstrably worked.

**Status:** ready-for-agent

- [ ] The Kubernetes manifests (namespace, deployment, service, PVC) are deleted
- [ ] The Kubernetes deploy workflow is deleted
- [ ] The guidance file's Deployment section describes the Unraid template and names every field it carries
- [ ] The three-ports paragraph is gone
- [ ] No remaining reference in the guidance file describes the app as deployed to Kubernetes
- [ ] The environment-variable section no longer sources values from a ConfigMap or a Secret
- [ ] The README's three stale spots are corrected
- [ ] The Dockerfile and Compose comments no longer reference a PersistentVolumeClaim
- [ ] The Compose file still builds from source and still uses its own distinct host port
- [ ] `CONTEXT.md` is unmodified
- [ ] `uv run pytest` still passes; no application code changed

## Notes

The Compose file is deliberately left as the build-from-source local file. It is the only way to run the real image locally before it ships, and its host port stays distinct from the deployed one so a local run cannot collide with the deployed app.

The `kind` cluster, its namespace, the systemd port-forward unit, and the self-hosted runner registration are all left alone — the cluster is shared with other applications. This ticket removes the repository's description of them, not the running infrastructure.

`CONTEXT.md` is a glossary of the domain. Deployment vocabulary does not belong in it and it should come out of this ticket untouched.

## Comments
