# A batch is ephemeral and in-process, like a run

Submitting several episode URLs at once starts a **batch**: the URLs are validated and de-duplicated up front, then summarized one after another on a single worker thread, with the queue's progress reaching the browser as Server-Sent Events. A batch is not written down anywhere. It has a token, a buffered event stream, and exactly one terminal event — the same machinery a single run uses — and a restart loses it. The episodes that finished before the restart are saved as ordinary runs, because that is what they are.

## Considered Options

- **A persisted batch, with a table and a resumable queue.** Rejected: it buys recovery from a restart, and pays for it with a job table, a state machine, and a worker that has to be reconciled against it — the machinery this app deliberately does not have. An in-flight *run* already does not survive a restart; a batch surviving one would be the only durable piece of work in the application.
- **Running the episodes in parallel.** Rejected: every edge is a blocking library, and the failure that ends a batch is YouTube deciding it has seen enough requests. Serial keeps one caption fetch in flight and turns rate-limiting into a slower batch rather than a dead one.

## Consequences

- The queue panel is lost on reload or restart; History is where the finished episodes are found. This is the same bargain a single run already makes.
- A failing episode does not stop the batch. It stays in the queue with its failure kind, and the batch ends when every episode is terminal.
- There is no batch in the domain model below the UI: nothing downstream of the queue knows an episode arrived as part of one, and a saved run carries no batch identifier.
