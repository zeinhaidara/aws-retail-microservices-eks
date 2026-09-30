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

$catalog = Invoke-RestMethod "http://localhost:8081/products"
if ($catalog.items.Count -lt 1) { throw "catalog returned no products" }
Write-Output "catalog: ok ($($catalog.items.Count) products)"

$inventory = Invoke-RestMethod "http://localhost:8082/inventory/prod-001"
if ($inventory.available -lt 1) { throw "inventory returned no stock" }
Write-Output "inventory lookup: ok ($($inventory.available) available)"

$order = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8083/orders" `
  -ContentType "application/json" `
  -Body '{"items":[{"productId":"prod-001","quantity":1}]}'

if ($order.event -ne "OrderCreated" -or $order.status -ne "CONFIRMED") { throw "order flow failed" }
if ($order.total -ne 49.99) { throw "order total failed" }
Write-Output "order flow: ok ($($order.orderId), total $($order.total))"
