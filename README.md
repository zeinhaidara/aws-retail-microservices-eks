# Retail Microservices Infrastructure

Terraform for the AWS platform behind the retail microservices demo. Application source,
containers, Helm application chart, and app CI/CD live in the separate `app` branch.

## What this repository deploys

- A VPC, public/private subnets, one NAT gateway, and an EKS cluster with managed nodes.
- Six immutable ECR repositories: product, inventory, order, notification, trip planner,
  and storefront.
- A lean data tier per environment: one private, single-AZ MySQL RDS instance, a DynamoDB
  inventory table, and a private Valkey Serverless cache.
- An order-events SQS queue with a dead-letter queue and an EventBridge event bus.
- Service-scoped Secrets Manager entries and workload IAM roles.
- An ACM certificate and IAM roles for the ingress and DNS controllers.
- On Terraform `apply`, the workflow installs the AWS Load Balancer Controller and
  ExternalDNS, then applies the storefront Ingress.

Public traffic follows this path:

```text
Browser -> Route 53 -> ALB (ACM HTTPS; HTTP redirects to HTTPS)
        -> EKS Ingress -> retail-storefront Service -> storefront pod
```

The app deployment must create `retail-storefront` on port `80` in `retail-<environment>`.
ExternalDNS publishes the ALB address for the Ingress hostname. The domain must use the
nameservers of the existing public Route 53 hosted zone.

EventBridge rules/targets, queue consumers, and SES email delivery are not created yet.
The architecture diagram is a broader target design; see
[architecture notes](docs/architecture/README.md) for the current boundary.

Each environment keeps MySQL and Valkey in private subnets and allows access only from
EKS worker nodes. RDS manages its master credential in Secrets Manager; applications
should use a restricted runtime DB user rather than the master account. Valkey is a
cache-aside learning component for product reads, never the source of truth for inventory.
The RDS instance and Serverless cache have ongoing costs while provisioned; destroy an
environment when it is not needed. DynamoDB uses on-demand billing.

The workflow supports `dev`, `test`, and `prod`, each with an independent state key and
environment-specific CIDR/domain defaults. These are functional demo stacks, not a
production-hardened reference architecture. Applying test or prod creates additional
billable infrastructure; keep those GitHub Environments approval-protected and destroy
the stacks when finished.

## Repository structure

```text
terraform/bootstrap/             One-time state bucket
terraform/environments/          Separate dev, test, and prod state
terraform/modules/platform/      Composes the platform modules
terraform/modules/               Network, EKS, data, messaging, ECR, secrets, edge, IRSA
scripts/                         Post-apply controllers and runtime-secret sync
.github/workflows/               Manual Terraform and state-bootstrap workflows
```

Each environment's `main.tf` calls only `modules/platform`. The platform module owns the
shared service catalog and composes the reusable infrastructure modules.

## GitHub configuration

Set these repository variables:

| Variable | Purpose |
| --- | --- |
| `AWS_REGION` | Deployment region; use the same region for EKS and ACM |
| `AWS_ROLE_ARN` | GitHub Actions OIDC role ARN |
| `OWNER` | Resource-name prefix component, currently `zein` |
| `PROJECT_NAME` | Resource-name prefix component, currently `cloudbatch818` |
| `TF_STATE_BUCKET` | S3 bucket created by the bootstrap workflow |
| `ROUTE53_ZONE_ID` | Existing public hosted zone ID shared by the environments |

The workflow derives the environment from the selected input. CIDRs and domains are set
in each Terraform root: dev uses
`10.40.0.0/16` and `cloudbatch818.click`, test uses `10.50.0.0/16` and
`test.cloudbatch818.click`, and prod uses `10.60.0.0/16` and
`prod.cloudbatch818.click`. All three hostnames must exist within the selected public
Route 53 hosted zone. NAT gateways are enabled by default in every environment.
Each Terraform root pins its EKS Kubernetes version; update the environment's
`cluster_version` default when upgrading the cluster.

Do not create a second hosted zone. Confirm the domain registration delegates to the
existing zone's Route 53 name servers. The configured hostname must be inside that zone.

Create GitHub Environments named `dev`, `test`, and `prod`; configure required reviewers
for each before using `apply` or `destroy`. Add the following secrets to every environment
you intend to apply:

| Secret | Used by |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | Trip-planner AI provider |
| `CLOUDFLARE_ACCOUNT_ID` | Trip-planner AI provider configuration |
| `GEMINI_API_KEY` | Trip-planner fallback provider |

These are seeded into Secrets Manager on `apply`, then synced to Kubernetes. Secret values
do not enter Terraform variables or state. Add future credentials to the `managed_secrets`
map in `terraform/modules/platform/main.tf` and extend the owning service's sync/deployment
integration. Use IAM workload identity for AWS access; do not create AWS access keys.

Current mapping:

```text
<project>-<owner>-<environment>/services/trip-planner/cloudflare -> cloudflare-ai-credentials
<project>-<owner>-<environment>/services/trip-planner/gemini     -> gemini-ai-credentials
```

The External Secrets IAM role is provisioned, but the External Secrets controller is not
installed yet; the Terraform workflow performs the current Kubernetes Secret sync.

The scripts are workflow glue, not application services:

- `platform-addons.sh` configures `kubectl`, installs the AWS Load Balancer Controller and
  ExternalDNS, then applies the storefront Ingress. On destroy, it removes the Ingress and
  controllers first so the ALB and DNS cleanup can finish before Terraform removes the VPC.
- `sync-runtime-secrets.sh` validates GitHub credentials, writes them to the existing
  Secrets Manager entries without passing values through Terraform, then syncs Kubernetes
  Secrets for the trip-planner deployment.

## Resource naming and tags

Resource names use `cloudbatch818-zein-<environment>` as their base (some grouped names
continue with `/services/...`). AWS resources receive `Owner=zein`, `Project=Cloudbatch818`,
`Environment=<environment>`, and `ManagedBy=terraform`; these values are applied through
provider defaults and passed into modules that create child resources. The Ingress also
tags its AWS load balancer. Keep GitHub repository variables `OWNER=zein` and
`PROJECT_NAME=cloudbatch818` so names remain consistent. Route 53 record sets and inline IAM
policies do not support resource tags; their owning zone/role is the taggable AWS resource.

The app branch also needs `AWS_ACCOUNT_ID`, `CLOUDFLARE_K8S_SECRET_NAME`, and
`GEMINI_K8S_SECRET_NAME` as GitHub Environment variables for its image and Helm deploy jobs.

## CI and CD flow

The infrastructure workflows live on the infrastructure branch; they do not build or
deploy application images.

- **Infra CI:** pull requests targeting `main` run Terraform format/validate plus Trivy
  Terraform misconfiguration and secret scans. A merge to `main` triggers the same checks.
- **Infra CD:** only `workflow_dispatch` runs it, and only from `main`. Choose `dev`, `test`,
  or `prod`. `plan` creates a review artifact without applying. `apply` and `destroy`
  create the corresponding saved plan, publish it for review, then pause at the selected
  protected GitHub Environment before applying that exact plan. Plan artifacts contain
  Terraform plan data and are retained for one day; restrict repository artifact access.
- **Bootstrap:** also manual and main-only. It creates the state bucket and applies its
  own plan in that run; run it once before infrastructure CD.

The plan job runs without a GitHub Environment so it can finish before the approval gate.
Put shared deployment configuration in repository variables as listed above. Configure
the AWS OIDC role trust to allow the `main` branch subject for plans and the `dev`, `test`,
and `prod` Environment subjects for applies. Keep AWS permissions as narrow as possible.

The application workflows are separate on the `app` branch:

- **App CI/CD:** pull requests targeting `app` run Compose/Helm validation, smoke tests,
  CodeQL, Trivy source/image scans, and dependency review; they do not publish or deploy.
  A merge creates a push to `app`, which reruns the checks. On success, the same workflow
  publishes immutable SHA-tagged images, pauses at the protected `dev` Environment for
  approval, then deploys that commit. This is automatic after merge, with a manual approval
  gate; no Actions-tab manual dispatch is required. GitHub requires `workflow_dispatch` and
  `workflow_run` definitions to exist on the repository's default branch, so the app flow
  stays in one push-triggered workflow on `app` instead of chaining a second workflow.

Require CI/security checks in branch protection for `main` and `app`, and disallow direct
pushes. Branch separation organizes workflows but does not isolate repository secrets; use
separate repositories and OIDC roles if you need a hard security boundary.

## First deployment

1. Configure the GitHub OIDC role and repository variables.
2. Run **Bootstrap Terraform State** once; copy its bucket output to `TF_STATE_BUCKET`.
3. Configure environment variables and secrets above.
4. From `main`, run **Terraform Infrastructure** with `environment=dev`, `action=plan`; review
   the artifact, especially the billable RDS and ElastiCache resources.
5. Run it again with `action=apply`; after reviewing the saved-plan artifact, approve the
   `dev` Environment gate to apply that same plan.
6. Merge the application PR into `app`. After CI passes, approve the `dev` Environment
   deployment. DNS and ALB health become ready after the Ingress, storefront Service,
   certificate validation, and controller reconciliation complete.

The state bucket has versioning, encryption, and public-access blocks. Environment states
are isolated at `environments/<environment>/terraform.tfstate` and use S3 lockfiles.

## Workflow actions

- `plan`: format check, validate, and show a plan; makes no infrastructure changes.
- `apply`: apply the reviewed Terraform plan, install cluster add-ons, configure HTTPS
  ingress, and sync runtime credentials.
- `destroy`: plan destruction, remove the Ingress/controllers, then apply the destroy plan.

Useful local checks (no AWS apply):

```powershell
terraform fmt -check -recursive terraform
terraform -chdir=terraform/environments/dev init -backend=false
terraform -chdir=terraform/environments/dev validate
```

Terraform state and plan files are ignored by Git. Never commit `.tfstate`, `.tfplan`,
`.tfvars`, or `.env` files.
