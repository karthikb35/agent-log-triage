# The Agents

Four nodes, each a pure function `TriageState -> partial TriageState`. None of them
call an LLM; all are deterministic and unit-testable in isolation.

## 1. Classifier — `agents/classifier.py`

Assigns one of a **fixed taxonomy** of categories to each failure using ordered
keyword rules (first match wins):

| Category | Matches on | Auto-triaged? |
| --- | --- | --- |
| `timeout` | "timed out", "deadline exceeded" | ✅ |
| `dependency_unavailable` | "connection refused", "503", "502" | ✅ |
| `business_rule` | "declined", "insufficient", "rejected" | ✅ |
| `assertion` | "assertionerror", "expected", "did not match" | ✅ |
| `infrastructure` | "evicted", "oomkilled", "preempted" | ✅ |
| `unknown` | *(nothing matched)* | ❌ → human |

Adding institutional knowledge = **adding a rule**, not retraining a model. Order
matters: a *connection* timeout is caught by the `timeout` rule before the generic
dependency rule.

## 2. Correlator — `agents/correlator.py`

Collapses many failures into a few **incidents** by grouping on
`(service, category, signature)`. This is the de-duplication that makes triage
valuable: one dead dependency becomes **one** incident, not 200 tickets. Incidents
are sorted by count so the most impactful is first.

## 3. Root-cause — `agents/root_cause.py`

For each incident, calls the **MCP tool** `lookup_runbook(category)` to attach a
probable cause and a remediation runbook. An incident is `auto_triaged` when its
category is anything other than `unknown`.

## 4. Summarizer — `agents/summarizer.py`

Computes the headline metrics and assembles the report:

```python
automation_rate = auto_triaged_failures / total_failures
minutes_saved   = auto_triaged_failures * MANUAL_MINUTES_PER_FAILURE  # default 8
```

It also lists the incidents that still `needs_human`, and asks the optional LLM
adapter for a one-line narrative (falling back to a deterministic template).

!!! tip "Why nodes return *partial* state"
    `TriageState` is `total=False`, so each node returns only the key it owns
    (`{"failures": ...}`). LangGraph merges it back. This keeps nodes decoupled —
    the correlator neither knows nor cares how classification happened.
