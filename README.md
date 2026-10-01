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

`Application CI/CD` runs on pull requests and pushes to `app`:

- Docker Compose validation
- Helm chart linting
- Local smoke tests
- CodeQL analysis
- Dependency Review on pull requests
- Trivy source/configuration scanning
- Trivy HIGH/CRITICAL image scanning

On a merge to `app`, the same workflow continues into release jobs only after all required
CI jobs pass. Keeping CI and CD together also avoids the default-branch requirement GitHub
places on `workflow_dispatch` and `workflow_run` workflows:

- Publishes immutable commit-SHA images to ECR
- Pauses at the protected `dev` GitHub Environment for deployment approval
- Deploys the same commit to the dev EKS cluster after approval

The application workflow expects these repository variables:

| Variable | Purpose |
| --- | --- |
| `AWS_ROLE_ARN` | GitHub OIDC deployment role |
| `AWS_REGION` | AWS region |
| `AWS_ACCOUNT_ID` | ECR registry account |
| `PROJECT_NAME` | Resource prefix, currently `cloudbatch818` |
| `OWNER` | Resource owner prefix, currently `zein` |

Create the `dev` GitHub Environment and configure required reviewers. Pull requests run
verification only; they do not publish images or deploy. The merge push runs the checks,
publishes images on success, then waits for environment approval before deploying. Resource
names follow `<PROJECT_NAME>-<OWNER>-<environment>`.
