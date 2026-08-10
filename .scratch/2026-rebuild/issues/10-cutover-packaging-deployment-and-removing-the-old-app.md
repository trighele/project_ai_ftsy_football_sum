# 10 — Cutover: packaging, deployment, and removing the old app

**What to build:** The new app becomes the only app. The Gradio entrypoint and the Postgres access module are deleted, along with the audio staging directory. Gradio and psycopg2 come out of the dependency declaration; the Hugging Face and Postgres environment variables come out of the deployment configuration. Nothing left in the repo references Whisper, ffmpeg, or a player database.

This ticket contains no user-facing behaviour — it is a mechanical sweep, and it should move quickly. Its risk is omission: a leftover reference to a deleted environment variable makes the next deploy fail in a way that is annoying to diagnose. Work through every consumer.

The image moves to a Python 3.14 slim base built with `uv sync --frozen`. ffmpeg, the C build toolchain, and the compiler are removed from it — nothing needs them once audio processing is gone. The pinned requirements file is deleted; it exists only to feed the old image build and will drift the moment it has no consumer.

The served port moves off Gradio's 7860 to a conventional application port, and must be changed consistently — Compose port mapping, the Kubernetes Service and Deployment, and the systemd port-forward reference all have to agree, or the deploy comes up unreachable.

A PersistentVolumeClaim is added and mounted at the data path ticket 03 made configurable, so saved runs and the cached player reference survive a pod restart. Docker Compose mounts a named volume at the same path so local and deployed behaviour do not diverge.

The deploy workflow's Secret and ConfigMap variable lists are updated to drop the removed variables. **Do not run a deploy** — that stays with the operator.

**Blocked by:** 07 and 09.

**Status:** ready-for-agent

- [ ] The Gradio entrypoint module, the Postgres access module, and the audio staging directory are deleted.
- [ ] Gradio and psycopg2 are removed from the dependency declaration; the lockfile is regenerated.
- [ ] The pinned requirements file is deleted and nothing references it.
- [ ] The image builds from a Python 3.14 slim base using `uv sync --frozen`.
- [ ] ffmpeg, the build toolchain, and the compiler are removed from the image.
- [ ] The served port is changed consistently across the application, Compose, the Kubernetes Service, the Deployment, and the port-forward reference.
- [ ] A PersistentVolumeClaim manifest exists and is mounted at the configured data path in the Deployment.
- [ ] Docker Compose mounts a named volume at the same data path.
- [ ] The Hugging Face and Postgres variables are removed from the workflow's Secret and ConfigMap lists.
- [ ] A repository-wide search finds no remaining reference to the Hugging Face endpoint, the Postgres connection variables, ffmpeg, or the staging path.
- [ ] The image builds and the container serves the app end to end under Docker Compose.
- [ ] No deploy is executed.
