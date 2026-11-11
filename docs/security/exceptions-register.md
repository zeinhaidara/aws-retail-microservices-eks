# Exceptions register

Every scanner suppression needs an inline reason, owner and expiry in the code, plus a row here. Never skip a whole check ID without a reason. An expired inline ignore makes the scan fail again, which forces the review.

The dev stack is torn down. The resource this row covers does not exist at present; the row records what is accepted in the Terraform source and must be reviewed before the stack is rebuilt.

| ID | Tool and rule | Resource | Reason | Owner | Expiry | Link |
|---|---|---|---|---|---|---|
| EXC-001 | Trivy config `AWS-0040`, `AWS-0041` (also matched as `AVD-AWS-0040`, `AVD-AWS-0041`) | `module.eks` cluster endpoint (`terraform/modules/eks/main.tf`), in dev, test and prod roots | Public EKS API endpoint, open to 0.0.0.0/0. GitHub-hosted runners deploy through the public endpoint and their IP ranges are too many for the endpoint CIDR allow list. Compensating controls: IAM-authenticated API access only, OIDC deployment role, workloads on Fargate in private subnets, stack destroyed after the demo. Fix before any longer-lived use: private endpoint with a self-hosted runner in the VPC, or a restricted CIDR list. Inline ignore on the one module call only; all other Trivy rules, secret scanning and dependency review stay enforced. | Moulaye | 2027-05-11 | `terraform/modules/eks/main.tf`, `.github/workflows/terraform-ci.yml`, `.github/workflows/app-ci.yml` |
