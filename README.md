# aws-retail-microservices-eks

Orbital Expeditions is a fictional space-tourism storefront built to demonstrate a fast, cloud-native AWS EKS deployment. Visitors compare Moon, Mars, and Europa expedition concepts, use an AI mission concierge to explore itinerary and packing ideas, add a destination to the cart, and reserve it through the commerce services. The journeys are imaginative demo concepts, not currently bookable travel.

## Run locally

For local development only, start the services and run the end-to-end smoke checks:

```powershell
docker compose up --build --detach
pwsh -File tests/smoke.ps1
docker compose down --volumes --remove-orphans
```

Open the storefront at `http://localhost:8085`. It loads destinations and availability through Product and Inventory APIs. The cart submits to Order, which retrieves authoritative product prices and asks Inventory to reserve seats. The browser cannot set prices. The animated orbital hero and destination cards use plain CSS and JavaScript, keeping the frontend build-free.

The mission concierge compares the catalog's `durationDays` and `bestMonth`, then returns an itinerary concept, packing inspiration, and matching package IDs. Trip planning runs as its own `trip-planner` service; the storefront forwards `/api/trip-plan` requests to it. The planner defaults to Cloudflare Workers AI with `@cf/meta/llama-3.2-3b-instruct`. If Cloudflare times out after 15 seconds or returns a transient 408/429/5xx error, it falls back to Gemini's `gemini-3.8-flash` when a Gemini key is configured.

To enable Gemini fallback locally, create a key in [Google AI Studio](https://aistudio.google.com/api-keys) and set `GEMINI_API_KEY` in `.env`. `.env` is git-ignored. The key is passed only to the trip-planner container, never to browser code. Gemini free-tier availability and quotas vary by model/account, and free-tier content may be used to improve Google's products.

To enable Cloudflare primary locally, create a Workers AI API token and copy your Cloudflare account ID from the [Workers AI dashboard](https://dash.cloudflare.com/). Set `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` in `.env`. Cloudflare's free allocation is limited (currently 10,000 Neurons per day); requests beyond it require a paid Workers plan. Without either configured provider, the planner uses deterministic demo responses. For Kubernetes, store provider credentials in AWS Secrets Manager and sync them to namespace-scoped Kubernetes Secrets; set Helm values `geminiSecret.name` and `cloudflareSecret.name` to inject them. Do not store credentials in Helm values or commit them to GitHub.

The GitHub Actions OIDC role provides keyless AWS authentication for Terraform and application workflows. App releases follow the protected `app` branch flow and deploy to the configured dev/prod EKS environments; Terraform remains maintained on the separate protected `main` branch.

Cloud deployments do not use Docker Compose. Build and publish the service images independently, then deploy them with the Helm chart in `deploy/helm/retail`. Each backend has an isolated source directory and Docker build context under `services/`.

| Service | Local port | Responsibility |
| --- | ---: | --- |
| Storefront | 8085 | Customer page and API proxy |
| Product | 8081 | Product catalog and authoritative prices |
| Inventory | 8082 | Available-stock lookup and reservation |
| Order | 8083 | Order validation, totals, and confirmation |
| Notification | 8084 | Notification service placeholder |
| Trip Planner | 8086 | AI itinerary generation and catalog-grounded recommendations |

Compose runs a local demo mode with in-memory inventory and orders and no AWS credentials. In EKS, Inventory uses DynamoDB for atomic seat reservations, Order stores confirmed orders and an outbox in MySQL, Product caches catalog reads in Valkey, and EventBridge routes outbox events to SQS for the Notification consumer. Queue delivery is at-least-once; failed notifications retry and eventually reach the configured dead-letter queue.

The storefront checkout accepts an optional email. The notification service sends a fixed SES confirmation when an address and `SES_FROM_ADDRESS` are configured; otherwise it logs that the event was handled without email. Terraform verifies the dev sender domain with Route 53 DKIM records. SES sandbox accounts can send only to verified recipients until production access is granted.

The fictional catalog covers all eight planets, a Moon orbit, and a heliocentric Sun grand tour. Concept package prices range from $99,000 for Earth Orbital Retreat to $3,250,000 for Solar Grand Tour. Durations and suggested months are storytelling inputs for the planner, not real launch windows or mission durations.

## Application workflows

All app changes go through pull requests into the protected `app` branch. `Application CI` has two visible stages: configuration validation, followed by parallel integration smoke tests and security checks (Trivy image/filesystem scans, CodeQL, and dependency review). New commits cancel stale CI runs, and Docker BuildKit caches speed up repeated image builds.

After a merge to `app`, `Application CD` lints the chart, builds and publishes immutable commit-tagged dev images, reads applied dev outputs from Terraform state, and deploys/verifies dev. This lab intentionally does not deploy test or prod. Full Compose/smoke validation runs once in CI rather than being repeated in CD. Release runs are serialized so deployments do not race.

GitHub repository variables used by CD: `AWS_ROLE_ARN`, `AWS_REGION`, `AWS_ACCOUNT_ID`, `PROJECT_NAME`, `OWNER`, and `TF_STATE_BUCKET`. Create a protected `dev` GitHub Environment. The app CD workflow reads the dev Terraform outputs so database endpoints, queue/table names, and workload role ARNs do not need to be copied into GitHub variables. The expected EKS cluster and ECR repositories follow `<PROJECT_NAME>-<OWNER>-dev`.

## AWS integration

Terraform is maintained on the separate `main` branch. Its dev platform provides:

- DynamoDB inventory table with a least-privilege inventory service role
- RDS MySQL order/outbox tables created by the Order service on startup; its role can read only the RDS-managed credential secret
- Valkey catalog cache, accessed privately by Product
- EventBridge order rule and SQS consumer queue/DLQ, with separate publisher and consumer roles
- SES dev domain identity and Route 53 DKIM records; the Notification role can send from that identity
- Helm service accounts annotated with their workload-specific IAM roles
- HTTPS storefront ingress and external DNS

`Application CI` runs local Compose smoke tests and does not contact AWS. After Terraform CD has applied dev, app CD reads its outputs and injects resource endpoints and role ARNs into Helm. In SES sandbox mode, verify each test recipient in SES before expecting delivery.

## Branch separation

- `main`: Terraform infrastructure only.
- `app`: application source, Dockerfiles, Compose, Helm, tests, and application workflows.
- Feature branches merge into their respective protected branch by pull request.
