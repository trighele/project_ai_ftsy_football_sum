# 05 — Record the decision and repair the ADR trail

**What to build:** A future reader who asks "why does this app have persistent state and no orchestrator?" finds an answer, and following any ADR reference in the guidance file lands somewhere real.

An architectural decision record is written for the choice made here: publish to a registry, run on Unraid, let Watchtower deploy, run no orchestrator at all. It qualifies on all three counts — meaningfully hard to reverse, surprising without context, and the result of a genuine trade-off. It should say plainly what was given up: no declarative record of the running system, no rollout status, no readiness gate, and no rollback other than re-pointing a form at an older tag. For one process and one SQLite file serving one person, that is the right trade, but it is a trade and the record exists to say so.

The ADR directory itself has to be recreated — it was deleted wholesale in commit `4672a61`, which is also why the guidance file's three existing ADR citations currently point at nothing. Those dangling references are pre-existing debt rather than something this work caused, and they get resolved here: the claims they were carrying are stated inline where they are made, and the only ADR cited is the new one.

**Blocked by:** 04 — Remove Kubernetes from the repo and the docs. Both tickets rewrite the same guidance file, and the decision cannot be recorded as final until the change describing it has landed.

**Status:** ready-for-agent

- [ ] The ADR directory exists again
- [ ] An ADR records publishing to GHCR, running on Unraid, and having no orchestrator
- [ ] The ADR states what was given up, not only what was chosen
- [ ] No reference in the guidance file points at a deleted ADR
- [ ] The claims the deleted ADRs carried are stated where they are relied on
- [ ] The new ADR is the only one cited
- [ ] `CONTEXT.md` is unmodified
- [ ] `uv run pytest` still passes; no application code changed

## Notes

The three ADRs deleted in `4672a61` are not being restored. Their content is folded into the prose that relied on them — in particular the rule that depth rank and ECR tier are separate facts and are never collapsed into a single "tier", which is load-bearing and currently leans on a citation that resolves to nothing.

## Comments
