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

Terraform is intentionally maintained on the separate `infra` branch.
