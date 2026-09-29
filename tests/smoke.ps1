$ErrorActionPreference = "Stop"

$services = @{
  product = 8081
  inventory = 8082
  order = 8083
  notification = 8084
}

foreach ($service in $services.Keys) {
  $response = Invoke-RestMethod "http://localhost:$($services[$service])/health"
  if ($response.status -ne "ok") { throw "$service health check failed" }
  Write-Output "${service}: ok"
}

$order = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8083/orders" `
  -ContentType "application/json" `
  -Body '{"items":[{"sku":"demo-1","quantity":1}]}'

if ($order.event -ne "OrderCreated") { throw "order flow failed" }
Write-Output "order flow: ok ($($order.orderId))"
