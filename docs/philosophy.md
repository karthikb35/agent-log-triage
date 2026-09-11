# Philosophy

Five principles drive every design decision in this repo.

## 1. Determinism first, LLMs at the edge

"Agentic" too often means "non-reproducible." We invert that. The **control flow**
(which agent runs next) and the **decisions** (classification, correlation, root
cause) are pure Python over a fixed graph. An LLM is allowed only to *narrate* an
already-computed result, and only when `TRIAGE_LLM=1`. If the model is down, the
platform still produces identical numbers.

!!! quote "The test"
    Run the pipeline twice on the same logs. If you get a different triage, you
    built a slot machine, not a triage system.

## 2. Structure is the leverage

Manual triage is slow because a human parses **unstructured** logs. The 50%
reduction comes from refusing to start there: `pytest-resumable-stepmetrics`
emits a **stable JSON schema** (named steps, per-attempt status, typed
`service_calls`). Agents read *fields*, not prose. Structured in → structured out.

## 3. Small agents with one job each

Four nodes — classify, correlate, root-cause, summarize — each doing one thing.
Small nodes are testable, auditable, and cheap to reason about. "Multi-agent" is a
property of the graph, not of any node's cleverness.

## 4. Tools over hard-coding (that's what MCP is for)

Institutional knowledge (which runbook fits which failure) lives behind **MCP
tools**, not scattered `if` branches. The same typed tool surface can be published
to any MCP client, so an engineer in their IDE and the automated Job call the
*exact same* `lookup_runbook`.

## 5. Batch work belongs in a Job

Triage has a beginning and an end: read a window of logs, produce a report, exit.
That is the textbook definition of a **Kubernetes Job** — run to completion, then
stop. We resist the temptation to make it a long-lived service it doesn't need to
be. When the workload *does* become streaming, the [Jobs chapter](kubernetes-jobs.md)
shows the KEDA / Argo upgrade paths.

## What "reduced triage effort by 50%" actually means here

It is a **computed metric**, not a slogan. The summarizer reports the
**automation rate** = failures auto-resolved to a known root cause ÷ total
failures. Everything in that numerator never reached a human. The demo lands at
~80% on the sample logs; the CI gate (`--fail-under`) fails the build if coverage
regresses below your target.
