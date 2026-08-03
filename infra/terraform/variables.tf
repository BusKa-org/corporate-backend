variable "instance_name" {
  description = "Nome da VM."
  type        = string
}

variable "image_id" {
  description = "ID da imagem a usar."
  type        = string
}

variable "flavor_id" {
  description = "Flavor da VM."
  type        = string
}

variable "key_pair" {
  description = "Chave SSH registrada no OpenStack."
  type        = string
}

variable "security_groups" {
  description = "Lista de security groups."
  type        = list(string)
}

variable "network_name" {
  description = "Nome da rede para anexar."
  type        = string
}

variable "cloud_name" {
  description = "Entrada em clouds.yaml a ser usada pelo provider OpenStack."
  type        = string
  default     = "openstack"
}
