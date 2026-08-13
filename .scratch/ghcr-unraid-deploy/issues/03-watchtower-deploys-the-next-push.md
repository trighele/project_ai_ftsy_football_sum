# 03 — Watchtower deploys the next push by itself

**What to build:** Merging to `main` is the whole deploy. Nothing else is done by hand.

Watchtower is already running on the box. This ticket establishes that it is actually watching *this* container — if it is label-scoped rather than global, the container needs the Watchtower enable label in its template's extra parameters, or it will be skipped forever with no error anywhere. Then it is proved end to end: merge a visible change to `main`, wait out one poll interval, and see the running app change without touching the box.

This is the point of the entire effort. Everything before it publishes an image; this is what makes publishing and deploying one action.

**Blocked by:** 02 — Get it running on Unraid. There is no container to update until one exists.

**Status:** ready-for-human

This ticket cannot be completed by an agent. It requires reading Watchtower's configuration on the box and watching a live container restart.

- [ ] Whether Watchtower is global or label-scoped is established, not assumed
- [ ] If label-scoped, the container carries the Watchtower enable label
- [ ] A change merged to `main` is visible in the running app without any manual step on the box
- [ ] The update happens within one Watchtower poll interval
- [ ] Saved runs survive the Watchtower-triggered restart
- [ ] A `workflow_dispatch` build does **not** cause the running container to change

## Notes

The last criterion is the one worth being deliberate about. It confirms the safety property built in ticket 01 from the other end: a dev-tagged build exists in the registry and the live app ignores it. If a dispatch ever moved the running container, an unmerged branch would be serving your live app within minutes and nothing would say why.

A Watchtower restart that interrupts a run is expected and already handled — the page reports that contact with the run was lost and re-enables the Summarize button. Watchtower makes this happen more often, not differently. Restricting Watchtower to an overnight window was considered and declined: re-running an episode costs one paste, and a schedule is one more thing that can be misconfigured silently.

## Comments
