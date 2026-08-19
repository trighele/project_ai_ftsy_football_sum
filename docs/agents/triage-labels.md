# Triage labels

Five roles, carried in a spec's `labels` front matter. A spec has exactly one
of them at a time.

- **needs-triage** — arrived, not yet read. The default for anything written
  in a hurry.
- **needs-info** — cannot proceed until a question is answered. The question
  belongs in the spec, in the section it blocks.
- **ready-for-agent** — every decision is made and written down. An agent can
  implement it without asking anything.
- **ready-for-human** — decided, but wants a person: a judgement call about
  taste, a credential, or something outside the repository.
- **wontfix** — decided against. Kept, with the reason, so it is not proposed
  again.
