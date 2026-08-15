# 06 — Commit the Unraid template XML

**What to build:** Rebuilding the deployment is a re-import, not a reconstruction from memory.

The runtime definition lives in Unraid's Docker template UI, which means that without this ticket the only copy of how this application runs is a web form on one machine. Unraid writes each user template to disk as XML. Exporting that file and committing it turns "recreate it from the field list in the docs" into "import it", and gives the deployment a version history the same way everything else here has one.

**Blocked by:** 02 — Get it running on Unraid. The template file does not exist until the container has been created.

**Status:** ready-for-agent

Needs one thing from the maintainer that an agent cannot fetch: the exported XML from the box, pasted in. Everything after that is a commit.

- [ ] The exported Unraid template XML is committed
- [ ] Its contents match the container that is actually running — image, port, path, and variables
- [ ] It contains no secret value; `ANTHROPIC_API_KEY` appears as a name, never a value
- [ ] The guidance file points at it as the restorable copy of the deployment
- [ ] `uv run pytest` still passes; no application code changed

## Notes

Check the exported file before committing it. Unraid templates can carry the values of environment variables, not only their names, and this one is configured with an API key.

This file is a snapshot, not a live definition. Changing the container in the Unraid UI does not update it, so it goes stale unless re-exported after a change — worth saying wherever the guidance file points at it.

## Comments
