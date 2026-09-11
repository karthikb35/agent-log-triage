# Quickstart

## Prerequisites

- Python 3.10+
- (Optional) Docker + a Kubernetes cluster for the Job manifests

## 1. Install

```bash
git clone https://github.com/karthikb35/agentic-log-triage
cd agentic-log-triage
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e . pytest pytest-resumable-stepmetrics
```

## 2. Triage the bundled sample logs (no test run needed)

```bash
triage run --reports examples/sample_steplogs --format md
```

You should see ~80% automation rate, six incidents, and one that `needs_human`.

## 3. Generate fresh logs from the test suite, then triage

```bash
pytest --steplog-json --steplog-json-dir=reports
triage run --reports reports --format md --fail-under 0.5
```

`--fail-under 0.5` exits non-zero if fewer than 50% of failures auto-triaged — wire
it into CI to keep triage quality from regressing.

## 4. Optional: enable an LLM narrative

```bash
pip install "agentic-log-triage[llm]"
export OPENAI_API_KEY=sk-...
export TRIAGE_LLM=1
triage run --reports reports --format md
```

The LLM only writes the one-line narrative; every number is still computed
deterministically. With no key or no flag, a deterministic template is used.

## 5. Run it as a Kubernetes Job

```bash
docker build -t registry.internal/tickethub/agentic-log-triage:0.1.0 -f deploy/Dockerfile .
kubectl create namespace triage
kubectl apply -k deploy/
kubectl create job --from=cronjob/log-triage-sweep triage-now -n triage
kubectl logs -f job/triage-now -n triage
```

## CLI reference

```text
triage run
  --reports PATH        file or dir of step-log JSON (default: .steplog)
  --out FILE            write report here instead of stdout
  --format {json,md}    output format (default: json)
  --fail-under FLOAT    exit non-zero if automation rate < this (0..1)
```
