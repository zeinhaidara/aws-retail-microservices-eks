# Current architecture

These diagrams describe the implemented paths plus the monitoring included in this PR.
Monitoring requires deployment. Historical Eraser/PNG assets are retained for reference
but are not authoritative. Edit this Mermaid source with the code changes.

## Runtime topology

```mermaid
flowchart TB
  browser["Customer browser"] -->|"DNS lookup"| dns["Route 53"]
  browser -->|"HTTPS after DNS resolution"| alb["Public ALB / ACM"]
  dns -. "Returns ALB address" .-> browser
  subgraph vpc["VPC us-east-2"]
    alb
    subgraph eks["EKS Fargate: private subnets"]
      web["Storefront: page + API proxy"]
      product["Product"]
      inventory["Inventory"]
      order["Order + outbox publisher"]
      notify["Notification + SQS worker"]
      planner["Trip planner"]
      prom["Prometheus: private"]
      grafana["Grafana: authenticated"]
      web --> product
      web --> inventory
      web --> order
      web --> notify
      web --> planner
      order --> product
      order --> inventory
      order -->|"Check email session"| notify
      notify -->|"Fetch saved order"| order
      planner -->|"Catalog context"| product
      prom -. "Scrape /metrics on all six app pods" .-> web
      prom -.-> product
      prom -.-> inventory
      prom -.-> order
      prom -.-> notify
      prom -.-> planner
      grafana -->|"PromQL"| prom
    end
    alb -->|"/"| web
    alb -->|"/grafana/"| grafana
    product -->|"TLS 6379"| cache["Private ElastiCache Valkey"]
    inventory -->|"AWS API / IRSA"| ddb["DynamoDB inventory"]
    order -->|"TCP 3306"| mysql["Private RDS MySQL: orders + outbox"]
    order -->|"IRSA: DB credential"| secrets["Secrets Manager"]
  end
  order -->|"OrderCreated via PutEvents"| bus["EventBridge bus + matching rule"]
  bus --> queue["SQS order-events"]
  queue -->|"Long poll"| notify
  queue -->|"After 3 receives"| dlq["SQS dead-letter queue"]
  notify -->|"IRSA: SendEmail"| ses["SES verified sender / sandbox recipients"]
  ses --> inbox["Customer inbox"]
  planner -->|"NAT / HTTPS"| ai["Cloudflare AI / Gemini fallback"]
```

Route 53 resolves names rather than forwarding HTTP. ALB TLS ends at the public listener.
The ALB routes directly to Fargate pod IPs selected by Kubernetes Services/Ingress.
MySQL and Valkey are private managed services outside the EKS cluster.
DynamoDB, EventBridge, SQS and SES are regional AWS services accessed through their APIs.

## Reservation and asynchronous delivery

```mermaid
sequenceDiagram
  actor Visitor
  participant Web as Storefront
  participant N as Notification
  participant SES
  participant O as Order
  participant P as Product
  participant I as Inventory / DynamoDB
  participant DB as MySQL
  participant E as EventBridge
  participant Q as SQS
  Visitor->>Web: Request email verification
  Web->>N: /email/verify
  N->>SES: VerifyEmailIdentity
  SES-->>Visitor: Verification link
  Visitor->>SES: Confirm identity
  Visitor->>Web: Check status and reserve
  Web->>O: POST /orders + email session token
  O->>N: Check verified session
  O->>P: Retrieve authoritative prices
  O->>I: Conditional seat reservation
  O->>DB: Commit order + outbox together
  O-->>Web: Confirmed order / email queued
  Web-->>Visitor: Reservation confirmation
  loop Pending outbox every 5 seconds
    O->>E: PutEvents OrderCreated
    E->>Q: Matching rule forwards event
    O->>DB: Mark published after acceptance
  end
  N->>Q: ReceiveMessage (long poll)
  N->>O: GET /orders/{id}
  O->>DB: Fetch persisted order
  O-->>N: Order details + recipient
  N->>SES: SendEmail
  SES-->>N: Accepted or rejected
  alt Accepted or order without email
    N->>Q: DeleteMessage
  else Failure
    Note over N,Q: After repeated failures, SQS moves the retained message to the DLQ
  end
```

SES acceptance does not guarantee final inbox delivery. User evidence confirmed a reservation
email in Gmail. Events/messages and sends may duplicate; there is no exactly-once guarantee.

## Delivery and security ownership

```mermaid
flowchart LR
  infraPR["Infrastructure PR into main"] --> checks["Terraform + chart checks"]
  checks --> plan["Manual Terraform plan / approval / apply"]
  plan --> aws["AWS infrastructure + workload IAM"]
  plan --> addons["Controllers + monitoring + Ingress"]
  appPR["Application PR into app"] --> ci["Unit / smoke / security checks"]
  appPR --> cd["After merge: App CD"]
  cd --> ecr["SHA-tagged ECR images"]
  ecr --> helm["Protected dev approval + Helm rollout"]
  aws --> helm
```

Require application CI before merge. CI and CD are separate workflows.
OIDC gives GitHub short-lived deployment credentials. IRSA gives each AWS-integrated app its
runtime permissions. A broader deployment role does not fix a denied notification runtime role.

## Explicit exclusions and constraints

No SNS topic/fanout, API Gateway, Lambda, Istio or Kinesis appears on the current deployed path.
EKS has no EC2 managed node group. RDS is single-AZ. Verification sessions and metrics storage
are ephemeral. The diagram describes a demonstrator, not a production availability commitment.
