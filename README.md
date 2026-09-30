# aws-retail-microservices-eks

Retail microservices platform for EKS, Terraform, Kubernetes, event-driven workflows, and CI/CD.

## Application quick start

The application branch contains the service code and local container workflow. The initial scaffold provides health endpoints for Product, Inventory, Order, and Notification services plus a minimal `OrderCreated` response flow.

```powershell
docker compose up --build -d
.\tests\smoke.ps1
docker compose down
```

Service endpoints:

| Service | Local port |
| --- | ---: |
| Product | 8081 |
| Inventory | 8082 |
| Order | 8083 |
| Notification | 8084 |

Terraform is maintained on the separate `main` branch.

## Application pipelines

`Application CI` runs on pull requests and pushes to `app`:

- Docker Compose validation
- Helm chart linting
- Local smoke tests
- CodeQL analysis
- Dependency Review on pull requests
- Trivy source/configuration scanning
- Trivy HIGH/CRITICAL image scanning

`Application CD` runs after a successful CI run on `app`, or manually with `workflow_dispatch`:

- Publishes immutable commit-SHA images to ECR
- Waits for approval from the selected GitHub Environment
- Deploys the Helm release to the matching EKS cluster

The CD workflow expects these repository variables:

| Variable | Purpose |
| --- | --- |
| `AWS_ROLE_ARN` | GitHub OIDC deployment role |
| `AWS_REGION` | AWS region |
| `AWS_ACCOUNT_ID` | ECR registry account |
| `PROJECT_NAME` | Resource prefix, currently `cloudbatch818` |

Create `dev`, `test`, and `prod` GitHub Environments as needed. Configure required reviewers on each environment to gate the EKS deployment. The environment name must match the Terraform naming convention: `<PROJECT_NAME>-<environment>`.
