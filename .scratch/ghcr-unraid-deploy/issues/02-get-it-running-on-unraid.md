# 02 — Get it running on Unraid

**What to build:** The application runs on the Unraid box from the published image, reachable in a browser, with its saved runs surviving a restart.

The GHCR package is made public, so neither the box nor Watchtower ever needs a registry credential that can expire and silently stop updates. A Docker container is then created from Unraid's template UI, publishing the app on host port **4301** and keeping its data on the array at **`/mnt/user/appdata/ffsum`** — a host path rather than a named volume, so the SQLite file can be opened and backed up without entering a container, and so it lands in the appdata share the existing backup already covers.

Once it is up, the app answers on 4301, a summarize run completes and is saved, and the saved run is still there after the container is restarted.

**Blocked by:** 01 — Publish the image to GHCR under the new name and tag rules. There is nothing to pull until the image exists.

**Status:** ready-for-human

This ticket cannot be completed by an agent. Both the GHCR visibility setting and the Unraid Docker template are web forms on systems CI cannot reach.

- [ ] The GHCR package for `ffsum` is public
- [ ] The image pulls on the box with no `docker login`
- [ ] An Unraid Docker template exists for the app, pointed at `ghcr.io/<owner>/ffsum:latest`
- [ ] Host port 4301 maps to the container's 8000
- [ ] Host path `/mnt/user/appdata/ffsum` maps to `/data`
- [ ] `ANTHROPIC_API_KEY` is set as a template variable
- [ ] `CLAUDE_MODEL` and `FFSUM_DATA_DIR` are set as template variables
- [ ] The app answers in a browser on port 4301
- [ ] The readiness pill reads ready, rather than naming a missing `ANTHROPIC_API_KEY`
- [ ] A summarize run completes end to end and is saved
- [ ] The SQLite database file is visible on the array at the mapped path
- [ ] A saved run is still listed after the container is restarted

## Notes

No data is carried over from the Kubernetes PersistentVolumeClaim. The cached player reference re-syncs itself within its 12-hour window or on demand from **Sync now**, and saved runs are re-runnable from their source URLs.

The Kubernetes copy of the app keeps running on port 4012 against its own database throughout. Two live copies is the expected state until you retire that namespace, which is out of scope here — the cluster stays up for the other applications on it.

Port 4301 is not the port the app is on today. Anything pointing at 4012 — a bookmark, a reverse-proxy entry, a phone shortcut — needs updating by hand.

## Comments
