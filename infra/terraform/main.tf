resource "openstack_compute_instance_v2" "buska_core" {
    name             = var.instance_name
    image_id         = var.image_id
    flavor_id        = var.flavor_id
    key_pair         = var.key_pair
    security_groups  = var.security_groups

    network {
        name = var.network_name
    }
}