# AWS EKS Retail Microservices Architecture

![AWS EKS Retail Microservices Architecture](aws-eks-retail-microservices-architecture.png)

Editable Eraser diagram:

[Open in Eraser](https://app.eraser.io/workspace/9CRHIYLWJjxIQj5I8kZp)

## Traffic model

- Public traffic enters through the internet-facing Application Load Balancer over HTTPS.
- The ALB routes only to Product and Order service endpoints in the private EKS subnets.
- Order calls Product synchronously for product and price validation.
- Order calls Inventory synchronously to reserve stock.
- Product reads Aurora/RDS and ElastiCache.
- Order reads and writes Aurora/RDS.
- Inventory reads and writes DynamoDB.
- Order publishes `OrderCreated` to EventBridge.
- EventBridge routes events to Inventory and Notification SQS queues.
- Inventory publishes `InventoryReserved` or `InventoryFailed`.
- Order publishes `OrderStatusUpdated` after processing the inventory result.
- Notification consumes notification events asynchronously.

## Security boundaries

- ALB security group: HTTPS from the internet.
- EKS node/pod security group: application traffic from the ALB and required EKS traffic.
- Aurora security group: MySQL `3306` from Product and Order workloads only.
- ElastiCache security group: Redis `6379` from Product workloads only.
- DynamoDB, SQS, EventBridge, ECR, Secrets Manager, and CloudWatch use IAM and VPC endpoints where appropriate; they do not require inbound security groups.
- Kubernetes NetworkPolicies provide pod-to-pod isolation inside EKS.
