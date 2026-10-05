# Orbital Expeditions on AWS EKS

A working, fictional space-travel storefront that demonstrates an AWS application from
customer request through inventory reservation, durable order storage and email delivery.
The business scenario is a demo. Package prices are fictional, not revenue or real bookings.

Development deployment: **https://cloudbatch818.click** in **us-east-2**.
Terraform's S3 backend remains in **us-east-1**. Those regions serve different purposes.

## What works and what still needs deployment

The storefront, reservation flow, recipient verification and an SES confirmation reaching
Gmail have been demonstrated. This change adds Fargate-compatible Prometheus/Grafana and
application metrics. Monitoring is **not live until both review branches merge and deploy**.

| Component | Responsibility | Implementation |
| --- | --- | --- |
| Storefront | Page, cart and same-origin API proxy | Python HTTP server, HTML/CSS/JavaScript |
| Product | Authoritative concept catalog and prices | In-code catalog, Valkey cache-aside reads |
| Inventory | Seat availability and conditional reservation | DynamoDB transactions in AWS, memory locally |
| Order | Validate prices, reserve inventory, store order + event | RDS MySQL orders and transactional outbox |
| Notification | Verify recipients, consume events, send email | SES, SQS long polling, internal Order API |
| Trip planner | Catalog-grounded AI itinerary and concierge | Cloudflare primary, Gemini fallback, demo fallback |
| Prometheus | Scrape each pod's metrics | Namespace-scoped discovery, 15-second interval |
| Grafana | View application health and delivery attempts | Provisioned dashboard, authenticated HTTPS subpath |

Six independently built application images run on EKS Fargate in private subnets.
Monitoring adds two pods in the existing application namespace. No EC2 node group,
node-exporter DaemonSet, privileged container or EBS volume is required.

SNS is **not implemented** in the current path. EventBridge routes directly to SQS.
SNS remains a project acceptance requirement: implement and verify its fanout separately;
do not present it as deployed. API Gateway, Lambda, Istio, Kinesis and CloudFront are also
not part of this implementation.

## Request and data flows

1. Route 53 resolves the hostname. The browser connects to the internet-facing ALB.
   ACM handles TLS at the ALB. HTTP redirects to HTTPS.
2. The ALB forwards to the Storefront pod through an IP target group. The storefront
   proxies browser API calls to private Kubernetes Services. Route 53 is DNS, not an HTTP proxy.
3. Product supplies catalog prices. Product uses Valkey with a 60-second cache lifetime
   and falls back to its source catalog when the cache fails. Valkey is not inventory storage.
4. Inventory reads DynamoDB and reserves all requested seats atomically with a sufficient-stock
   condition. Insufficient seats return a conflict, rather than confirming a sold-out order.
5. Order recalculates totals using Product data. It commits the order and an outbox event
   together in MySQL. If persistence fails, it requests an inventory release.
6. The outbox worker publishes every five seconds to the EventBridge bus. The matching
   OrderCreated rule forwards the event to SQS.
7. Notification receives the SQS event, fetches the saved order over the private Order
   Service, calls SES, then deletes the message only after successful processing.
8. Failed processing retries after visibility expires. After three receives, SQS moves
   the message to the dead-letter queue. Duplicate delivery remains possible.

The outbox protects against losing the event between a database commit and publication.
It does not provide exactly-once delivery or a transaction spanning MySQL and DynamoDB.

[Architecture and sequence diagrams](docs/architecture/README.md) are maintained as Mermaid
source in Git.

## Directory structure and branch ownership

The protected branches intentionally contain different files:

```text
main
├── .github/workflows/
│   ├── bootstrap.yml                 One-time remote-state bootstrap
│   ├── terraform-ci.yml              Terraform, security and monitoring-chart checks
│   └── terraform-cd.yml              Manual plan/apply/destroy with approval
├── terraform/
│   ├── bootstrap/                    S3 state bucket
│   ├── environments/{dev,test,prod}/  Separate roots and state keys
│   └── modules/
│       ├── platform/                 Composition and application IAM policies
│       ├── network/                  VPC, subnets, route tables, NAT
│       ├── eks/                      Fargate cluster and CoreDNS
│       ├── data/                     DynamoDB, MySQL, Valkey and data SG
│       ├── messaging/                EventBridge rule/target, SQS and DLQ
│       ├── edge/                     ACM, SES DKIM, controller IAM, Ingress
│       ├── ecr/                      Immutable image repositories
│       ├── secrets/                  Provider secret resources
│       └── irsa-role/                OIDC trust and workload role policy
├── deploy/helm/observability/
│   ├── Chart.yaml / values.yaml
│   ├── templates/                    Monitoring workloads, discovery RBAC, configuration
│   └── dashboards/retail.json         Provisioned Grafana dashboard
├── scripts/
│   ├── platform-addons.sh             Controllers, monitoring and Ingress lifecycle
│   └── sync-runtime-secrets.sh        Provider credentials into AWS/Kubernetes Secrets
└── docs/
    ├── architecture/README.md         Current topology and sequence diagrams
    └── observability.md               Dashboard, metrics and deployment verification

app
├── .github/workflows/{app-ci,app-cd}.yml
├── services/
│   ├── product-service/              app.py, metrics.py, Dockerfile, requirements.txt
│   ├── inventory-service/            app.py, metrics.py, Dockerfile, requirements.txt
│   ├── order-service/                app.py, metrics.py, Dockerfile, requirements.txt
│   ├── notification-service/         app.py, metrics.py, Dockerfile, requirements.txt
│   ├── trip-planner/                 app.py, metrics.py, Dockerfile
│   └── storefront/                   server.py, metrics.py, index.html, assets/, Dockerfile
├── deploy/helm/retail/                Application Deployments, Services and IRSA accounts
├── docker-compose.yml                Local development only
├── tests/                            Smoke, verification and metrics tests
└── docs/email-notifications.md        Visitor verification flow and limitations
```

Each service retains an independent Docker build context. The small metrics collector
is copied into each service so no backend depends on another backend's source folder.
Tests ensure those copies match. There is no shared runtime service.

## GitHub configuration

Repository variables:

| Variable | Purpose |
| --- | --- |
| AWS_REGION | Resource deployment region, currently us-east-2 |
| AWS_ACCOUNT_ID | ECR account used by App CD |
| AWS_ROLE_ARN | GitHub Actions OIDC deployment role |
| PROJECT_NAME / OWNER | Naming components: cloudbatch818 / zein |
| TF_STATE_BUCKET | Existing bootstrap state bucket |
| ROUTE53_ZONE_ID | Existing public hosted zone |

Protected GitHub Environments: dev, test, prod. Configure approval rules before apply/destroy.
Infrastructure supports all three. Application CD currently deploys **dev only**.
Creating test/prod infrastructure creates separate billable stacks.

Secrets for each environment you apply:

| Secret | Purpose |
| --- | --- |
| CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN | Trip-planner primary provider |
| GEMINI_API_KEY | Trip-planner fallback provider |
| GRAFANA_ADMIN_PASSWORD | At least 16 characters, initial Grafana admin login |

Grafana username is `admin`. The workflow creates the `grafana-admin` Kubernetes Secret
only when absent. Changing the GitHub secret does not rotate an existing Grafana user
password. Rotate the user through Grafana's authenticated administration UI, and keep the
bootstrap secret consistent. No password enters Terraform state or Helm values.

Provider credentials enter Secrets Manager and namespace-scoped Kubernetes Secrets.
The External Secrets IAM role exists, but the External Secrets controller is not installed.
The current workflow performs the sync. No AWS access keys belong in application images.

## Merge and deploy this change

1. Merge the infrastructure review branch into main after checks pass.
2. Add GRAFANA_ADMIN_PASSWORD under Settings / Environments / dev / Environment secrets.
3. Run Terraform CD from main with environment=dev and action=plan. Review the change.
   The SES permission must cover account/region recipient identities while restricting
   ses:FromAddress to orders@cloudbatch818.click. No region or data-resource migration is intended.
4. Run Terraform CD with action=apply and approve the protected environment after reviewing
   its newly generated saved plan. It applies IAM, then installs monitoring and updates Ingress.
5. Merge the application review branch into app after CI passes. App CD builds immutable
   commit-tagged images and waits for dev approval before deploying.
6. Open https://cloudbatch818.click/grafana/ and log in. Choose Orbital Expeditions Operations.
   Expect six retail scrape targets. A metric rate needs a few scrapes before showing data.
7. Browse the catalog and place one reservation with a verified recipient. Confirm the
   order, the inbox email, and dashboard counters. SES acceptance is not proof of inbox delivery.
8. Once the Terraform permission has applied successfully, the manually added SendOrderEmails
   inline policy can be removed by an authorized administrator. Keep it until the managed
   policy is verified; it is not automatically adopted or removed by Terraform.

No AWS apply, order creation, email send or DLQ redrive occurs simply by opening a PR.
Monitoring-only infrastructure changes do not rebuild app images; app metrics require App CD.

## CI/CD and safety

Infrastructure PRs target main. Terraform CI checks format, offline validation and security.
It also lints/renders the monitoring chart and checks Prometheus configuration with promtool.
Terraform CD is manual. plan changes nothing. apply/destroy pause for environment approval.

Application PRs target app. App CI validates Compose/Helm, runs unit and integration tests,
and checks Trivy, CodeQL and dependencies. App CD publishes SHA-tagged ECR images, reads
applied Terraform outputs from main, deploys Helm and verifies the rollout.
App CI and CD are separate workflows; require App CI checks before merging.

Temporary notification-debug workflows/scripts and automatic log dumps have been removed.
Routine access, probe and successful-email logs are suppressed. Failure/retry logs remain
so an operator can investigate failures. Prometheus/Grafana are metrics, not a log archive.

Terraform apply is not transactional. Preserve failed-apply state and reconcile resources;
do not restore an old state file as a substitute for deleting resources.
If a saved plan is stale, generate/review a fresh plan. Serialize operations on the same state.

The versioned S3 backend uses environment keys and lockfiles. Backend location can differ
from resource location. Never switch a deployment region against existing state without a
documented reconciliation/migration plan.

## Networking and permissions

Fargate pods use private subnet IPs. Internal Service DNS and CoreDNS connect the services.
The data security group permits MySQL TCP 3306 and Valkey TCP 6379 from the EKS cluster
security group. Security groups are stateful, so replies to permitted connections do not
require a mirrored inbound rule. Egress, route tables and NAT still determine outbound reachability.

The ALB uses public subnets; RDS/Valkey are private. Private pods reach external AI services
and AWS APIs through the configured egress path. TLS terminates at ALB; application traffic
inside the VPC uses HTTP. Kubernetes NetworkPolicies are not installed/enforced by this project.

IRSA binds inventory, order, notification and controllers to specific namespace/service-account
subjects. Fargate pod execution roles pull images; they do not grant application AWS access.
The GitHub Terraform deployment role is managed outside this repository and has separate
permissions from the notification runtime role.

## Email behavior

Recipients enter their own email, request SES verification, confirm the SES link and check
status before reserving. Order validates that session before reserving inventory.
No fixed demo recipient replaces the customer's address.

SES remains in sandbox until AWS grants production access. Verified sender and recipient
identities are required in sandbox; verification does not remove send-rate/daily quotas.
Demo session tokens and verification rate limits live in one notification process. Keep one
replica until shared durable session/rate-limit storage exists. Verification is not user login.

SQS has a 60-second visibility timeout and a three-receive DLQ policy. After fixing a failure,
inspect DLQ messages and use an authorized SQS redrive deliberately. Do not purge the queue.
At-least-once processing can duplicate email if a send succeeds but acknowledgement fails.

## Local development and validation

On app, Compose uses in-memory orders/inventory and does not prove AWS integration:

```powershell
docker compose up --build --detach
pwsh -File tests/smoke.ps1
python -m unittest discover -s tests -p 'test_*.py'
docker compose down
```

Storefront: http://localhost:8085. Product/Inventory/Order/Notification/Planner local ports:
8081/8082/8083/8084/8086. In Kubernetes all app containers listen on 8080; Services map
their published ports to that container port. Compose is never the cloud deployment mechanism.

On main:

```powershell
terraform fmt -check -recursive terraform
terraform -chdir=terraform/environments/dev init -backend=false
terraform -chdir=terraform/environments/dev validate
helm lint deploy/helm/observability
helm template monitoring deploy/helm/observability --namespace retail-dev
```

Do not commit credentials, .env, state, plans or real customer records.

## Cost and production boundary

No validated monthly bill, load benchmark, SLA or ROI is claimed. Use AWS billing data and a
workload model before quoting figures. Always-on costs include EKS control plane, NAT, ALB,
RDS and the cache. Fargate bills provisioned pod capacity; managed services add usage charges.
Monitoring adds two continuously running pods. Application data and metrics have different lifecycles.

RDS is single-AZ db.t3.micro with one-day backups. Deletion protection is disabled and destroy
skips the final snapshot: preserve orders with an explicit backup before any destructive run.
Prometheus and Grafana use emptyDir storage. Metrics history and Grafana UI changes/users reset
with replacement pods; source-controlled dashboard/data-source provisioning recreates the baseline.

Before production: shared verification sessions/rate limits, notification idempotency,
reliable compensation, restricted DB user, longer backups/restore drills, multi-AZ design,
SSO and stronger admin perimeter, durable monitoring, alert routing, queue/DLQ alarms,
secret rotation, abuse protection and least-privilege review of the deployment role.
SNS fanout remains an outstanding project acceptance item.

Before presenting: finish the two deployments, verify six scrape targets, confirm spare
inventory and one email, prepare a recorded/screenshot fallback and rehearse the
ten-minute presentation. Keep slide decks, presenter notes and private demo evidence
outside this repository.
