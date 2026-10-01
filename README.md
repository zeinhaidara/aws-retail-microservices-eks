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

The current local backend keeps product, inventory, and order data in memory. Restarting the services resets inventory and loses orders. This is a functional local demo, not durable production storage.

The fictional catalog covers all eight planets, a Moon orbit, and a heliocentric Sun grand tour. Concept package prices range from $99,000 for Earth Orbital Retreat to $3,250,000 for Solar Grand Tour. Durations and suggested months are storytelling inputs for the planner, not real launch windows or mission durations.

## Application workflows

All app changes go through pull requests into the protected `app` branch. `Application CI` has two visible stages: configuration validation, followed by parallel integration smoke tests and security checks (Trivy image/filesystem scans, CodeQL, and dependency review). New commits cancel stale CI runs, and Docker BuildKit caches speed up repeated image builds.

After a merge to `app`, `Application CD` follows distinct release stages: Helm chart preflight, build and publish immutable commit-tagged images, deploy and verify dev, then wait for approval from the protected `prod` GitHub Environment before promoting the same commit to prod. Full Compose/smoke validation runs once in CI rather than being repeated in CD. Release runs are serialized so deployments do not race.

GitHub repository variables used by CD: `AWS_ROLE_ARN`, `AWS_REGION`, `AWS_ACCOUNT_ID`, `PROJECT_NAME`, and `OWNER`. Create the `dev` and `prod` GitHub Environments; their names must match the Terraform environment names. Add environment variables `CLOUDFLARE_K8S_SECRET_NAME` and `GEMINI_K8S_SECRET_NAME` in both environments. These are names of pre-synced Kubernetes Secrets (not credential values); each must exist in its deployment namespace and contain the configured keys. The expected EKS clusters and ECR repositories follow `<PROJECT_NAME>-<OWNER>-<environment>`.

## Current AWS integration gaps

Terraform is intentionally maintained on the separate `main` branch. The current infrastructure does not yet provision all services required for a complete cloud application:

- Cognito User Pool and app client for customer authentication
- Relational database for product/order persistence, plus application migrations
- Application-side DynamoDB access and seed/setup flow for inventory
- SNS topic and SQS consumer queues/subscriptions for asynchronous order events and notifications
- AWS Load Balancer Controller/Ingress to provide a public storefront endpoint
- Runtime IAM permissions and configuration for the services to access those resources

The Terraform branch currently has an inventory table, one SQS queue with a DLQ, and an EventBridge bus, but the application does not yet publish/consume events from them. These integrations should be added only with their corresponding infrastructure and least-privilege IAM roles, then covered by integration tests.

## Branch separation

- `main`: Terraform infrastructure only.
- `app`: application source, Dockerfiles, Compose, Helm, tests, and application workflows.
- Feature branches merge into their respective protected branch by pull request.
