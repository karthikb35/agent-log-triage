# Kubernetes Jobs

Triage is **batch work**: read a window of logs, produce a report, exit. That is the
textbook definition of a Kubernetes **Job**. This page is a compact Jobs primer plus
the manifests this repo ships.

## Mental model

> A **Deployment** is a *restaurant* — it keeps N waiters on the floor forever. A
> **Job** is a *catering order* — do this batch of work, confirm it's done, go home.
> A **CronJob** is the caterer who shows up every Friday.

The distinguishing property: **Jobs have a notion of "done."** Deployments never do.

## Basics

```yaml
apiVersion: batch/v1
kind: Job
spec:
  template:
    spec:
      restartPolicy: Never   # required: Never or OnFailure (not Always)
      containers: [{ name: triage, image: ... }]
  backoffLimit: 4            # retry the Pod up to 4x before the Job fails
```

Exit `0` → Pod `Succeeded` → Job `Complete`. Non-zero → retried with exponential
backoff up to `backoffLimit`.

## The knobs that matter

| Field | Controls |
| --- | --- |
| `completions: N` | Job done after N successful Pods |
| `parallelism: M` | Up to M Pods at once |
| `backoffLimit` | Pod-level retries before the Job fails |
| `activeDeadlineSeconds` | Hard wall-clock cap |
| `ttlSecondsAfterFinished` | Auto-delete Job+Pods after completion |
| `podFailurePolicy` | React differently to specific exit codes / conditions |

**Three Job shapes:** single-run, fixed-count parallel (`completions` + `parallelism`),
and **work-queue** (each Pod pulls until the queue drains) — the scalable pattern for
high-volume work. **Indexed Jobs** (`completionMode: Indexed`) give each Pod a static
shard index for deterministic partitioning with no queue.

## How this repo maps triage onto Jobs

- **[`deploy/job.yaml`](https://github.com/karthikb35/agent-log-triage/blob/main/deploy/job.yaml)** —
  a one-shot Job that runs `triage run` over the logs and exits.
- **[`deploy/cronjob.yaml`](https://github.com/karthikb35/agent-log-triage/blob/main/deploy/cronjob.yaml)** —
  a `*/15 * * * *` sweep with `concurrencyPolicy: Forbid`.

Both set the production-grade defaults: `restartPolicy: Never`, non-root +
`readOnlyRootFilesystem`, resource requests/limits, `ttlSecondsAfterFinished`, and a
`podFailurePolicy` that **fails fast on exit 1** (triage below threshold) but
**ignores node preemption** so disruptions don't burn the retry budget.

```yaml
podFailurePolicy:
  rules:
    - action: FailJob
      onExitCodes: { operator: In, values: [1] }
    - action: Ignore
      onPodConditions: [{ type: DisruptionTarget }]
```

## Is a Job always the right answer? No.

| Need | Better than a plain Job |
| --- | --- |
| **Real-time** triage on spikes | **KEDA-scaled Deployment** consuming a queue (scale-to-zero when idle) |
| **Complex DAG** / backfill / lineage | **Argo Workflows / Tekton** (Jobs become the runtime under an orchestrator) |
| **Event-driven** ("triage *this* deploy now") | **Argo Events / Knative** trigger → Job |
| **Durable, resumable agent state** | **Temporal** so a crashed agent resumes mid-graph |

**Rule of thumb:** scheduled or backfill triage → **CronJob + (Indexed) Job**.
Live triage → **KEDA**. Many interdependent stages → wrap Jobs in **Argo Workflows**.
This repo uses CronJob + Job as the spine and documents the upgrade paths.

## Apply it

```bash
kubectl create namespace triage
kubectl apply -k deploy/            # kustomization → Job + CronJob
kubectl create job --from=cronjob/log-triage-sweep triage-now -n triage
kubectl logs -f job/triage-now -n triage
```
