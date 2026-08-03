# OpenStack Infrastructure

## File Structure

This Terraform configuration consists of the following files:

- **`versions.tf`** – Specifies minimum Terraform and provider versions
- **`providers.tf`** – Configures the OpenStack provider using the `cloud_name` from your local `clouds.yaml`
- **`main.tf`** – Defines all infrastructure resources (VMs, networks, etc.)
- **`variables.tf`** – Declares input variables
- **`outputs.tf`** – Exports useful values (instance ID, name, and IPv4 address)
- **`terraform.tfvars.example`** – Example configuration template
- **`clouds.yaml`** – OpenStack credentials (git-ignored, must be created locally)

## Prerequisites

- Terraform 1.5 or higher
- A valid `clouds.yaml` file with OpenStack credentials

Place your `clouds.yaml` in one of these locations:
- `~/.config/openstack/clouds.yaml` (recommended)
- Current directory with `OS_CLIENT_CONFIG_FILE=$(pwd)/clouds.yaml` exported

## Getting Started

1. Copy `terraform.tfvars.example` to `terraform.tfvars` and update the values
2. (Optional) Update the `cloud_name` if using a non-default OpenStack cloud entry
3. Initialize Terraform: `terraform init`
4. Preview changes: `terraform plan`
5. Apply configuration: `terraform apply`

## Best Practices

- Never commit `terraform.tfvars`, `clouds.yaml`, or `.tfstate` files – these are already excluded in `.gitignore`
- Always review `terraform plan` output before applying changes
- Use meaningful variable values and consider using remote state for team environments