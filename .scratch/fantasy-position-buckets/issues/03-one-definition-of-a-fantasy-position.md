# 03 — One definition of a fantasy position

**What to build:** A prefactor with no visible behaviour. The six positions a fantasy manager can start — quarterback, running back, fullback, wide receiver, tight end, kicker — are currently written down twice: once as the prompt's position filter, once implicitly in what the Players page is about to need. After this ticket they are declared once, where the player reference is assembled, and the prompt builder imports that definition instead of holding its own copy.

Nothing a reader sees changes, and nothing Claude receives changes. Ticket 04 is what makes it visible.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

See [../spec.md](../spec.md).

- [ ] The fantasy position set is declared once, in the module that assembles the player reference
- [ ] The prompt builder uses that definition rather than declaring its own
- [ ] A test asserts the two are the same object, so a future edit cannot fork them
- [ ] The existing byte-for-byte prompt tests pass without modification — if they need editing, this ticket has changed the summaries and has gone wrong
- [ ] The depth-rank cut stays where it is; only the position set moves
