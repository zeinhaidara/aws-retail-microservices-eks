# aws-retail-microservices-eks - Infrastructure

Terraform Infrastructure-as-Code for the retail microservices platform.

This `main` branch contains infrastructure only. Application source code, Dockerfiles, Docker Compose, Helm charts, and application tests belong on the `app` branch.

## Layout

```text
terraform/
├── bootstrap/                 # One-time Terraform state bucket
└── environments/
    └── dev/                   # Current development environment

.github/workflows/
├── bootstrap.yml              # One-time state bucket workflow
└── terraform.yml              # Format, validate, plan, apply
```

Future environments use the same structure:

```text
terraform/environments/test/
terraform/environments/prod/
```

## GitHub configuration

Repository variables:

```text
AWS_REGION
AWS_ROLE_ARN
OWNER
PROJECT_NAME
TF_STATE_BUCKET
```

Environment variables for `dev`:

```text
ENVIRONMENT=dev
VPC_CIDR=10.40.0.0/16
CLUSTER_VERSION=1.33
ENABLE_NAT_GATEWAY=true
```

Terraform applies `Owner=zein` and `Project=cloudbatch818` to supported AWS resources. Resource names use the `cloudbatch818-zein` prefix followed by the environment where applicable.

Set these repository variable values before running the workflows:

```text
OWNER=zein
PROJECT_NAME=cloudbatch818
```

Create the same environment variable names for `test` and `prod` later, using different values such as non-overlapping VPC CIDRs.

No AWS access keys, database passwords, `.tfvars` files, or Terraform state files are committed.

## Initial setup

1. Create the GitHub OIDC IAM role and configure the repository variable `AWS_ROLE_ARN`.
2. Run **Bootstrap Terraform State** manually from GitHub Actions.
3. Copy the emitted S3 bucket name into the repository variable `TF_STATE_BUCKET`.
4. Run the Terraform workflow for `dev`.

## Terraform workflow

Pull requests to `main` run:

```text
terraform init
terraform fmt -check
terraform validate
terraform plan
```

Pushes to `main` and manual workflow runs upload the plan as an artifact. The selected GitHub Environment controls approval before the exact saved plan is applied.

The state keys are isolated by environment:

```text
environments/dev/terraform.tfstate
environments/test/terraform.tfstate
environments/prod/terraform.tfstate
```

Terraform state is never manually edited or committed to Git.
