$ErrorActionPreference = "Stop"

$services = @{
  product = 8081
  inventory = 8082
  order = 8083
  notification = 8084
  storefront = 8085
  tripPlanner = 8086
}

foreach ($service in $services.Keys) {
  $response = Invoke-RestMethod "http://localhost:$($services[$service])/health"
  if ($response.status -ne "ok") { throw "$service health check failed" }
  Write-Output "${service}: ok"
}

$catalog = Invoke-RestMethod "http://localhost:8081/products"
if ($catalog.items.Count -lt 1) { throw "catalog returned no products" }
Write-Output "catalog: ok ($($catalog.items.Count) products)"

$inventory = Invoke-RestMethod "http://localhost:8082/inventory/orbit-001"
if ($inventory.available -lt 1) { throw "inventory returned no stock" }
Write-Output "inventory lookup: ok ($($inventory.available) available)"

$order = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8083/orders" `
  -ContentType "application/json" `
  -Body '{"items":[{"productId":"orbit-001","quantity":1}]}'

if ($order.event -ne "OrderCreated" -or $order.status -ne "CONFIRMED") { throw "order flow failed" }
if ($order.total -ne 249000) { throw "order total failed" }
Write-Output "order flow: ok ($($order.orderId), total $($order.total))"

$storefrontCatalog = Invoke-RestMethod "http://localhost:8085/api/products"
if ($storefrontCatalog.items.Count -lt 1) { throw "storefront catalog returned no products" }
$storefrontInventory = Invoke-RestMethod "http://localhost:8085/api/inventory"
if ($storefrontInventory.items.Count -ne $storefrontCatalog.items.Count) { throw "storefront inventory does not match catalog" }
Write-Output "storefront catalog and stock: ok"

$storefrontOrder = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8085/api/orders" `
  -ContentType "application/json" `
  -Body '{"items":[{"productId":"orbit-002","quantity":1},{"productId":"orbit-003","quantity":1}]}'

if ($storefrontOrder.event -ne "OrderCreated" -or $storefrontOrder.status -ne "CONFIRMED") { throw "storefront order flow failed" }
if ($storefrontOrder.total -ne 2140000) { throw "storefront order total failed: $($storefrontOrder.total)" }
$remainingInventory = Invoke-RestMethod "http://localhost:8085/api/inventory"
$marsSeatsLeft = ($remainingInventory.items | Where-Object productId -eq "orbit-002").available
$europaSeatsLeft = ($remainingInventory.items | Where-Object productId -eq "orbit-003").available
if ($marsSeatsLeft -ne 3 -or $europaSeatsLeft -ne 5) { throw "storefront checkout did not reserve requested inventory" }
Write-Output "storefront multi-item checkout and inventory reservation: ok"

$tripPlan = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8085/api/trip-plan" `
  -ContentType "application/json" `
  -Body '{"interest":"lunar views","priority":"shortest","traveler":"curious explorer"}'

if ($tripPlan.recommendedProductIds -notcontains "orbit-006") { throw "trip planner did not recommend the shortest catalog journey" }
if ($tripPlan.mode -ne "demo" -and $tripPlan.mode -ne "ai") { throw "trip planner mode missing" }
Write-Output "trip planner: ok ($($tripPlan.mode))"
