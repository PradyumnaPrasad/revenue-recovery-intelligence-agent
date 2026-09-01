# ADR-003: No broker, no agent framework, no vector DB

## Status
Accepted.

## Context
Three infrastructure additions were considered and rejected, each for a
different reason.

## Decisions

**No Celery / Redis / RabbitMQ.** The system needs a way to advance a
recovery workflow over time — a reminder today, a promise due in nine
days, an escalation ladder that respects cooldowns. At this scale (one
process, a few hundred invoices in a demo batch), a Postgres table and an
explicit tick function invoked on demand is strictly better than a message
broker: zero extra containers, zero extra infrastructure cost, trivially
debuggable with a plain SQL query instead of inspecting queue internals,
and one `docker compose up` for anyone evaluating the repo. Adding a
broker here would be resume-driven architecture — solving a scaling
problem this project doesn't have yet, at the cost of real operational
complexity it would have immediately.

**No LangChain / agent framework.** The control flow in this system is an
eight-step state machine, and the code states that plainly: observe,
diagnose, predict, rank, govern, execute, listen, verify. A framework
would wrap that same sequence in abstractions (chains, agents, tools-as-
callables) that exist to support *more* flexibility than this system
wants — the entire point of the policy engine is that the flow is
*not* flexible about what's allowed to happen. Auditability is this
project's central claim; a framework's implicit control flow would work
against demonstrating it.

**No vector database / RAG.** There is no corpus to retrieve over. The
one LLM call in this system (reply extraction) takes a single customer
reply and a fixed system prompt — nothing is retrieved, nothing is
indexed. Adding a vector store would be decoration with no retrieval task
behind it.

## Consequences
The stack is one Postgres container and one FastAPI process. If this
project needed to scale out later, `scheduled_actions` (not yet built) can
become a real queue via `SELECT ... FOR UPDATE SKIP LOCKED` without a
schema change — the table already looks like a queue, it just isn't
polled by a broker.
