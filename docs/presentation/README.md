# Executive presentation and technical rehearsal

[Download the editable ten-slide PowerPoint](https://github.com/zeinhaidara/aws-retail-microservices-eks/blob/main/docs/presentation/Orbital-Expeditions-Executive.pptx).
The deck includes speaker notes. Architecture is maintained as code in
[the Mermaid diagrams](../architecture/README.md), not as an unmaintained screenshot.
Evidence boundary: the user confirmed a reservation email in Gmail; the new
monitoring implementation requires both review branches to be merged and deployed.
Do not describe monitoring as live until its acceptance checks pass.

## Ten-minute running order

| Slide | Time | Message |
| --- | --- | --- |
| 1 — Orbital Expeditions | 0:30 | Fictional travel scenario, real AWS integration. |
| 2 — Business purpose | 0:45 | One customer journey; independent business capabilities. |
| 3 — Customer demonstration | 1:30 | Browse, reserve one available seat, show the confirmation email. |
| 4 — Application architecture | 1:30 | HTTPS entry, private services, managed data stores. |
| 5 — Confirmation and recovery | 1:15 | Transactional outbox, EventBridge, SQS, Notification, SES. |
| 6 — Controlled release | 1:00 | Reviewed infrastructure and immutable application releases. |
| 7 — Operational visibility | 1:00 | Health, traffic, latency, reservations and email attempts. |
| 8 — Cost and operating model | 1:00 | Explain cost drivers; do not invent monthly cost or ROI. |
| 9 — Production boundary | 1:00 | Working demonstrator versus documented control gaps. |
| 10 — Next decision | 0:30 | Bounded pilot, named owner, reliability and budget targets. |
| **Total** | **10:00** | Leave detailed implementation questions for discussion. |

Opening: “Orbital Expeditions is a fictional reservation experience backed by real
AWS services. I will show the customer journey, explain how requests and data move,
and separate what works today from what a production pilot would require.”

Closing: “This demonstrates an end-to-end delivery capability. My recommendation
is a bounded pilot with explicit ownership, reliability criteria and a spending
ceiling, after closing the documented control gaps.”

## Before the meeting

1. Merge and deploy the infrastructure review first, then the application review.
   Add the protected Environment secret `GRAFANA_ADMIN_PASSWORD` (at least
   16 characters) before Terraform CD. Review a fresh plan before applying.
2. Open the storefront in a clean browser session; confirm catalog and inventory
   load. Choose stock that is available. Do not repeatedly consume demo stock.
3. Complete email verification before the meeting. A notification-process restart
   loses its browser verification sessions; repeat verification if needed.
4. Make one rehearsal reservation and confirm its reference matches the email.
   Keep a dated screenshot of both as the fallback; never present it as live.
5. Verify the Grafana login and dashboard at `https://cloudbatch818.click/grafana/`.
   Confirm six retail scrape targets and generate modest traffic for panels.
   An empty request panel is not proof of failure; it may have no recent samples.
6. Keep the deck, storefront and inbox in separate prepared tabs. Do not expose
   IAM policies, credentials, recipient lists or private console pages on screen.
7. Rehearse once with a timer. If the live demo stalls, switch to the dated
   fallback after 30 seconds. Do not spend the presentation troubleshooting.
8. If monitoring has not deployed, say “implemented for review, deployment pending”
   and use the architecture explanation instead of an invented dashboard result.

## Understand the flow

### Public request and response

Route 53 answers DNS; it does not proxy the request. HTTPS goes to an
internet-facing Application Load Balancer. ACM provides its TLS certificate.
The ALB matches the host/path rule and forwards to the storefront pod IP.
The storefront serves HTML/assets and proxies same-origin `/api/*` calls to
Kubernetes Services. CoreDNS resolves these internal service names. Responses
return through the storefront and ALB to the browser.

The API server is the Kubernetes management interface, not the public
application endpoint. EKS Fargate runs pods without this project managing an EC2
node group. Application pods and managed data endpoints use private subnets.
Security groups control network reachability; IAM controls AWS API authorization.
Passing a security-group check does not grant permission to DynamoDB or SES.

### Catalog, inventory and reservations

Product owns the catalog and caches it in managed ElastiCache Serverless Valkey.
Valkey is Redis-compatible caching, not DynamoDB DAX and not a pod in EKS.
Inventory owns stock in DynamoDB and performs conditional reservation updates.
Order obtains authoritative product information and reserves inventory before
persisting the order in RDS MySQL. The browser's price is not authoritative.

Order and an outbox event are committed together in MySQL. This prevents the
ordinary “order saved but event never recorded” gap. A separate worker publishes
pending events to EventBridge and marks accepted events published. A crash between
publication and marking can cause duplicates. The outbox is not exactly-once
delivery and the inventory/database work is not a single distributed transaction.

### Email verification and asynchronous delivery

Notification requests SES verification, checks identity status and issues a
short-lived browser session token. Order validates that session before accepting
an email-bearing reservation. Verification proves the address is verified with
SES; it is not a full application account or login system. Tokens and rate limits
are process-local in this demonstrator.

EventBridge routes matching OrderCreated events into SQS. Notification long-polls
SQS, retrieves the saved order from Order, and calls SES with
`orders@cloudbatch818.click` as the sender. It deletes a successfully processed
message. Processing failures leave the message for retry; the queue's redrive
policy sends repeatedly received messages to its DLQ after the configured
threshold of three receives. DLQ messages require reviewed remediation/redrive.

“Queued” means the order workflow accepted the asynchronous work, not inbox
delivery. SES acceptance also does not prove inbox delivery. SES sandbox limits
still apply and recipients must be verified. SNS is not currently in this path;
SNS fanout remains a required scope item, not an implemented capability.

### Deployment and monitoring

Infrastructure PRs target `main`; application PRs target `app`. Terraform CD
uses a manually selected action/environment, a fresh plan and protected approval.
Application CD builds commit-tagged images in ECR and deploys with Helm after
approval. GitHub uses OIDC to obtain temporary credentials. Runtime service roles
are separate from the infrastructure deployment role.

Prometheus discovers the six application pods and scrapes private `/metrics`
endpoints every 15 seconds. Grafana uses that private Prometheus Service as its
data source. Grafana is behind login on the existing HTTPS ALB; Prometheus has no
public Ingress, and the public `/metrics` route is explicitly blocked.
Two additional ordinary Fargate pods run monitoring; no privileged node agents
or EC2 node group are introduced. Monitoring storage is temporary, capped at
24 hours/1 GB for Prometheus. It is not durable monitoring, log aggregation,
queue-depth collection or a production alerting system.

## Code-reading map

Application paths below are on the `app` branch; infrastructure paths are on
`main`. See the root README for the full combined directory structure.

| Concern | Source |
| --- | --- |
| Browser UX and same-origin API proxy | `services/storefront/server.py`, `services/storefront/index.html` |
| Catalog and Valkey cache | `services/product-service/app.py` |
| DynamoDB stock reservation/release | `services/inventory-service/app.py` |
| Validation, order persistence, transactional outbox | `services/order-service/app.py` |
| Recipient verification, SQS worker, SES send | `services/notification-service/app.py` |
| Catalog-grounded AI planner | `services/trip-planner/app.py` |
| Bounded metrics, probe/access-log suppression | Each service's `metrics.py` |
| App workload configuration and service accounts | `deploy/helm/retail/templates/`, `values.yaml` |
| Fargate profiles and cluster add-ons | `terraform/modules/eks/main.tf` |
| Private network and data services | `terraform/modules/network/`, `terraform/modules/data/` |
| EventBridge, SQS and DLQ | `terraform/modules/messaging/main.tf` |
| Runtime IAM role policies | `terraform/modules/platform/main.tf`, `irsa-role/` |
| Certificate, public routes and DNS | `terraform/modules/edge/` |
| Prometheus/Grafana chart | `deploy/helm/observability/` |
| Post-apply controller/monitoring installation | `scripts/platform-addons.sh` |
| Approval and delivery gates | `.github/workflows/terraform-cd.yml`, `app-cd.yml` |

## Likely executive questions

**What has been proven?** A working HTTPS demonstrator, backend availability and
reservation flow, persisted orders, and user-confirmed reservation email. New
monitoring must be accepted after deployment. No measured SLA or scale claim.

**What is the business value?** A reusable reservation/delivery pattern and an
observable, reviewable platform. A real business case needs actual users,
measured benefits, operating costs and acceptance criteria.

**How much does it cost?** No verified dollar estimate is supplied. EKS, NAT,
ALB, RDS, cache and running Fargate pods incur baseline costs; requests, messages,
email, data transfer and AI add usage-sensitive costs. Obtain account billing
evidence and a workload forecast before quoting a monthly total or ROI.

**Does Fargate make it free or infinitely scalable?** No. It removes node
management, not charges, quotas or capacity planning. The current single-replica
application and single-AZ database are demonstrator choices.

**What if email fails?** Orders do not wait on email delivery. The durable queue
retries; repeated failures go to a DLQ. Operations must investigate and redrive
safely. Durable notification idempotency is still needed to prevent duplicates.

**Is it secure?** There are HTTPS, private subnets, workload-specific roles,
managed secrets and protected releases. This is not a completed security audit.
SES verification is not account authentication; database access, shared session
state, abuse controls and IAM least privilege need production hardening.

**Can Terraform automatically roll everything back?** No. A failed apply can
leave resources and updated state. Reconcile state and cloud resources and
review a new plan. Restoring an old state file does not roll back AWS.

**What remains before production?** SNS fanout to satisfy scope; shared verification
state; durable idempotency; restricted DB credentials; availability/backups and
restore tests; durable metrics, alarms and delivery/bounce telemetry; load tests,
budget controls and explicit service ownership.

## Keep the story honest

No payments are processed. Package prices are fictional, not revenue.
AI recommendations do not override catalog prices or inventory.
Do not imply that scrape reachability proves successful reservations.
Do not describe SES-accepted attempts as unique emails or inbox delivery.
Do not call an ephemeral dashboard a durable audit or production SLA.
