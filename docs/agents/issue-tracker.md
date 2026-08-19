# Issue tracker

Issues and specs are local Markdown files. There is no GitHub Issues board, no
Jira, and nothing to authenticate against: the tracker is the repository.

## Layout

```
.scratch/
└── <feature>/
    └── spec.md
```

One directory per feature, named as a kebab-case slug of the feature. `spec.md`
is the issue: what problem it solves, what the solution is, and every decision
already made about it. Working notes for a feature go beside it in the same
directory and are not read by anything.

`.scratch/` is gitignored working space for some repositories; here it is
committed, because a spec is the record of a decision and outlives the branch
that implements it.

## Front matter

```yaml
---
title: A sentence naming the feature
labels: [ready-for-agent]
created: YYYY-MM-DD
---
```

`labels` carries the triage state — see [triage-labels.md](./triage-labels.md).
A spec written from a completed grilling session is `ready-for-agent`: every
open question was answered before it was written, so there is nothing left to
ask.

## Spec shape

Problem Statement, Solution, User Stories, Implementation Decisions, Testing
Decisions, Out of Scope, Further Notes. Specs describe decisions, not code:
no file paths and no snippets, because both go stale within a commit or two.
