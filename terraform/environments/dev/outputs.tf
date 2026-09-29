output "cluster_name" { value = module.platform.cluster_name }
output "cluster_endpoint" { value = module.platform.cluster_endpoint }
output "ecr_repository_urls" { value = module.platform.ecr_repository_urls }
output "inventory_table_name" { value = module.platform.inventory_table_name }
output "order_events_queue_url" { value = module.platform.order_events_queue_url }
output "order_events_queue_arn" { value = module.platform.order_events_queue_arn }
output "event_bus_name" { value = module.platform.event_bus_name }
