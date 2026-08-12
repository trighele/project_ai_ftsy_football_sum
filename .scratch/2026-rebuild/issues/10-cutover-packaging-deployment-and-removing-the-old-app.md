# 10 — Cutover: packaging, deployment, and removing the old app

**What to build:** The new app becomes the only app. The Gradio entrypoint and the Postgres access module are deleted, along with the audio staging directory. Gradio and psycopg2 come out of the dependency declaration; the Hugging Face and Postgres environment variables come out of the deployment configuration. Nothing left in the repo references Whisper, ffmpeg, or a player database.

This ticket contains no user-facing behaviour — it is a mechanical sweep, and it should move quickly. Its risk is omission: a leftover reference to a deleted environment variable makes the next deploy fail in a way that is annoying to diagnose. Work through every consumer.

The image moves to a Python 3.14 slim base built with `uv sync --frozen`. ffmpeg, the C build toolchain, and the compiler are removed from it — nothing needs them once audio processing is gone. The pinned requirements file is deleted; it exists only to feed the old image build and will drift the moment it has no consumer.

The served port moves off Gradio's 7860 to a conventional application port, and must be changed consistently — Compose port mapping, the Kubernetes Service and Deployment, and the systemd port-forward reference all have to agree, or the deploy comes up unreachable.

A PersistentVolumeClaim is added and mounted at the data path ticket 03 made configurable, so saved runs and the cached player reference survive a pod restart. Docker Compose mounts a named volume at the same path so local and deployed behaviour do not diverge.

The deploy workflow's Secret and ConfigMap variable lists are updated to drop the removed variables. **Do not run a deploy** — that stays with the operator.

**Blocked by:** 07 and 09.

**Status:** ready-for-human

- [x] The Gradio entrypoint module, the Postgres access module, and the audio staging directory are deleted.
- [x] Gradio and psycopg2 are removed from the dependency declaration; the lockfile is regenerated.
- [x] The pinned requirements file is deleted and nothing references it.
- [x] The image builds from a Python 3.14 slim base using `uv sync --frozen`.
- [x] ffmpeg, the build toolchain, and the compiler are removed from the image.
- [x] The served port is changed consistently across the application, Compose, the Kubernetes Service, the Deployment, and the port-forward reference.
- [x] A PersistentVolumeClaim manifest exists and is mounted at the configured data path in the Deployment.
- [x] Docker Compose mounts a named volume at the same data path.
- [x] The Hugging Face and Postgres variables are removed from the workflow's Secret and ConfigMap lists.
- [x] A repository-wide search finds no remaining reference to the Hugging Face endpoint, the Postgres connection variables, ffmpeg, or the staging path.
- [ ] The image builds and the container serves the app end to end under Docker Compose. **Not verified here — there is no Docker daemon in this dev container.** What was verified instead: `uv build` produces a wheel carrying the templates and static files, and the app serves `/` and `/history` under exactly the environment the image sets (`HOST=0.0.0.0`, `PORT=8000`, `FFSUM_DATA_DIR` on a mounted path), writing its SQLite file there. Someone with Docker should run `docker-compose up --build` before the deploy.
- [x] No deploy is executed.

**Notes:**

- The port-forward reference did not need a value change: the systemd unit forwards the Service (3012) to the host (4012), and only the container port moved (7860 → 8000). The workflow's `env:` block now records all three ports and what each one is, so the next reader does not have to guess which is which.
- `notebooks/nfl_extract.ipynb` — the ourlads.com scraper that fed the Postgres player tables — is left in place. It references none of the removed variables and is not part of the app runtime; deleting it is a separate call.
