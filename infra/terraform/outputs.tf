output "instance_id" {
  description = "ID da instância criada."
  value       = openstack_compute_instance_v2.buska_core.id
}

output "ipv4" {
  description = "IPv4 de acesso da instância."
  value       = openstack_compute_instance_v2.buska_core.access_ip_v4
}

output "name" {
  description = "Nome da instância criada."
  value       = openstack_compute_instance_v2.buska_core.name
}
