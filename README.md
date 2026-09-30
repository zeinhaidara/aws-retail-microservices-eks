# aws-retail-microservices-eks - Infrastructure

Terraform Infrastructure-as-Code for the retail microservices platform.

The `main` branch contains infrastructure only. Application source code, Dockerfiles, Docker Compose, Helm charts, and application tests belong on the `app` branch.

## Layout

```text
terraform/
├── bootstrap/                 # One-time Terraform state bucket
└── environments/
    └── dev/                   # Current development environment

.github/workflows/
├── bootstrap.yml              # One-time state bucket workflow
└── terraform.yml              # Format, validate, plan, apply, destroy

docs/
└── architecture/              # System architecture documentation
```

Future environments use the same structure:

```text
terraform/environments/test/
terraform/environments/prod/
```

## Architecture

The system architecture diagram, traffic flow, security boundaries, and editable Eraser link are documented in [docs/architecture/README.md](docs/architecture/README.md).

## GitHub configuration

Repository variables:

```text
AWS_REGION
AWS_ROLE_ARN
OWNER
PROJECT_NAME
TF_STATE_BUCKET
```

Required repository variable values:

```text
OWNER=zein
PROJECT_NAME=cloudbatch818
```

Environment variables for `dev`:

```text
ENVIRONMENT=dev
VPC_CIDR=10.40.0.0/16
CLUSTER_VERSION=1.33
ENABLE_NAT_GATEWAY=true
```

Create the same environment variable names for `test` and `prod` later, using different non-overlapping VPC CIDRs.

Terraform applies the following tags to supported AWS resources:

```text
Owner=zein
Project=cloudbatch818
```

Resource names use the `cloudbatch818-zein` prefix followed by the environment where applicable.

No AWS access keys, database passwords, `.tfvars` files, or Terraform state files are committed.

## Initial setup

1. Create the GitHub OIDC IAM role and configure `AWS_ROLE_ARN`.
2. Run **Bootstrap Terraform State** manually from GitHub Actions.
3. Copy the emitted S3 bucket name into `TF_STATE_BUCKET`.
4. Run the Terraform workflow for the selected environment.

## Terraform workflow

The workflow is manual only. In GitHub Actions, select an environment and action:

```text
plan    -> create and display a Terraform plan
apply   -> create a plan, then apply that exact plan
destroy -> create a destroy plan, then apply that exact plan
```

The selected GitHub Environment controls environment-specific variables and approval rules.

Terraform state is isolated by environment:

```text
environments/dev/terraform.tfstate
environments/test/terraform.tfstate
environments/prod/terraform.tfstate
```

Terraform state is never manually edited or committed to Git.
```

This keeps the correct architecture:

- `main`: Terraform and infrastructure documentation
- `app`: application source, Docker, Helm, and tests
- Manual Terraform execution only
- Environment-specific state and variables
- No automatic PR or push Terraform runs.