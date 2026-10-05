# Prometheus and Grafana

## Deployment and access

The infrastructure branch owns deploy/helm/observability. Terraform CD's platform-addons
step installs Helm release monitoring in retail-<environment>, which already matches the
application Fargate profile. The application branch supplies /metrics in all six images.

Set protected Environment secret GRAFANA_ADMIN_PASSWORD to at least 16 characters before
Terraform apply. Open https://cloudbatch818.click/grafana/ with username admin and that
initial password. No new hostname/certificate/load balancer is needed. Anonymous access
and signup are disabled. Prometheus has only a ClusterIP Service, no public route.
The ALB explicitly returns 404 for /metrics, while Prometheus scrapes internal pod IPs.

This is a demo security baseline. Public Grafana still needs SSO, stronger perimeter controls
and operational password rotation before production. Do not share credentials on a slide.

## Metrics and interpretation

| Metric | Meaning |
| --- | --- |
| up{job="retail"} | Prometheus successfully scraped a pod, not an end-to-end dependency check |
| retail_http_requests_total | HTTP responses by method/status, excluding probes and scrapes |
| retail_http_request_duration_seconds | End-to-end handler histogram including internal waits |
| retail_events_total{event="orders_confirmed"} | Successful reservation responses |
| retail_events_total{event="email_sent"} | SendEmail succeeded; SES accepted the request |
| retail_events_total{event="email_failed"} | Processing failed before queue acknowledgement, not unique failed orders |
| retail_events_total{event="outbox_published"} | EventBridge accepted an outbox event |
| retail_events_total{event="outbox_failed"} | Outbox worker attempts that failed |

There are no email addresses, order IDs, request bodies or raw URL labels. Event names and
HTTP method/status labels are bounded. Counters reset per process restart; rate/increase
handle observed resets, but Prometheus pod replacement loses its ephemeral history.
Rates need at least two scrapes. One-hour increase is an estimate from observed samples,
not an audited business ledger. Use MySQL for exact reservation totals.

The provisioned Orbital Expeditions Operations dashboard shows scrape availability,
request and error rates, p95 latency, reservation count estimates, SES acceptance attempts
and outbox publication/retry rate. It does not collect node/container CPU, database internals,
SQS queue depth, DLQ count, SES delivery/bounce events or central logs.

Fargate does not support node-exporter DaemonSets or EBS-backed pods. This chart runs
ordinary Deployments with emptyDir data and no host privileges. Prometheus has only
get/list/watch pods in its own namespace. Grafana has no mounted API service-account token.

## Verification after both deployments

1. Verify Terraform CD's monitoring install and App CD rollout succeeded.
2. In Grafana, open the dashboard. The expected number of retail scrape targets is six
   with one replica per app; rolling updates temporarily change that number.
3. Use Explore to query up{job="retail"}. Each current app pod should return 1.
4. Browse the catalog, ask the planner and reserve a seat. Wait for several scrapes.
5. Check the request series and confirmed-order event. Check SES acceptance after the email
   arrives. If processing fails, inspect failure logs with an authorized operator.
6. Confirm public /metrics returns 404 and Grafana requests require authentication.

Optional authorized CLI checks:

```powershell
kubectl get pods -n retail-dev
kubectl logs deployment/monitoring-prometheus -n retail-dev --tail=100
kubectl logs deployment/monitoring-grafana -n retail-dev --tail=100
kubectl logs deployment/retail-notification -n retail-dev --tail=100
```

No Kubernetes access? Use the Grafana UI for metrics and an authorized cluster operator
for logs. Temporary notification diagnostic GitHub jobs are intentionally removed.
Metrics do not replace error logs. Never purge messages to hide a processing failure.

## Lifecycle and limits

Prometheus stores at most 24 hours / 1GB on ephemeral storage. Grafana re-provisions its
data source and dashboard from ConfigMaps. Password changes, users and UI edits in its local
SQLite database are not durable across replacement pods. The bootstrap Secret stays in
Kubernetes unless manually removed, but its contents are not a Grafana database backup.

Changing chart configuration changes a pod-template checksum and triggers a restart.
An infrastructure destroy uninstalls monitoring after removing Ingress and before removing
controllers/VPC. Protect any data you need before destroying the demo.

For production, evaluate durable/managed metrics, durable Grafana state, SSO, resource sizing,
queue/DLQ and SES delivery telemetry, alert routing, retention policies and dashboards based
on agreed SLOs. No alert thresholds or paging destinations are invented in this change.

## Primary references

- [AWS Fargate limitations](https://docs.aws.amazon.com/eks/latest/userguide/fargate.html)
- [Prometheus Kubernetes discovery](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [Grafana provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)
