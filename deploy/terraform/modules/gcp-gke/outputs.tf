# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Outputs for GCP GKE Module

# Cluster information
output "cluster_id" {
  description = "The ID of the GKE cluster"
  value       = google_container_cluster.atp_cluster.id
}

output "cluster_name" {
  description = "The name of the GKE cluster"
  value       = google_container_cluster.atp_cluster.name
}

output "cluster_location" {
  description = "The location of the GKE cluster"
  value       = google_container_cluster.atp_cluster.location
}

output "cluster_endpoint" {
  description = "The endpoint of the GKE cluster"
  value       = google_container_cluster.atp_cluster.endpoint
  sensitive   = true
}

output "cluster_ca_certificate" {
  description = "The cluster CA certificate"
  value       = google_container_cluster.atp_cluster.master_auth[0].cluster_ca_certificate
  sensitive   = true
}

# Cluster configuration
output "cluster_version" {
  description = "The Kubernetes version of the cluster"
  value       = google_container_cluster.atp_cluster.master_version
}

output "cluster_ipv4_cidr" {
  description = "The IP range of the cluster"
  value       = google_container_cluster.atp_cluster.cluster_ipv4_cidr
}

output "services_ipv4_cidr" {
  description = "The IP range of the services"
  value       = google_container_cluster.atp_cluster.services_ipv4_cidr
}

# Node pool information
output "primary_node_pool_name" {
  description = "The name of the primary node pool"
  value       = google_container_node_pool.primary_nodes.name
}

output "primary_node_pool_version" {
  description = "The Kubernetes version of the primary node pool"
  value       = google_container_node_pool.primary_nodes.version
}

output "spot_node_pool_name" {
  description = "The name of the spot node pool"
  value       = var.enable_spot_nodes ? google_container_node_pool.spot_nodes[0].name : null
}

output "gpu_node_pool_name" {
  description = "The name of the GPU node pool"
  value       = var.enable_gpu_nodes ? google_container_node_pool.gpu_nodes[0].name : null
}

# Network information
output "network" {
  description = "The network of the cluster"
  value       = google_container_cluster.atp_cluster.network
}

output "subnetwork" {
  description = "The subnetwork of the cluster"
  value       = google_container_cluster.atp_cluster.subnetwork
}

# Security information
output "master_authorized_networks" {
  description = "The master authorized networks"
  value       = google_container_cluster.atp_cluster.master_authorized_networks_config
}

output "private_cluster_config" {
  description = "The private cluster configuration"
  value       = google_container_cluster.atp_cluster.private_cluster_config
}

# Workload Identity
output "workload_identity_config" {
  description = "The workload identity configuration"
  value       = google_container_cluster.atp_cluster.workload_identity_config
}

# Monitoring and logging
output "logging_service" {
  description = "The logging service used by the cluster"
  value       = google_container_cluster.atp_cluster.logging_service
}

output "monitoring_service" {
  description = "The monitoring service used by the cluster"
  value       = google_container_cluster.atp_cluster.monitoring_service
}

# Addons
output "addons_config" {
  description = "The addons configuration"
  value       = google_container_cluster.atp_cluster.addons_config
}

# Maintenance policy
output "maintenance_policy" {
  description = "The maintenance policy"
  value       = google_container_cluster.atp_cluster.maintenance_policy
}

# Resource labels
output "resource_labels" {
  description = "The resource labels applied to the cluster"
  value       = google_container_cluster.atp_cluster.resource_labels
}

# Kubectl connection command
output "kubectl_connection_command" {
  description = "Command to connect kubectl to the cluster"
  value       = "gcloud container clusters get-credentials ${google_container_cluster.atp_cluster.name} --location ${google_container_cluster.atp_cluster.location} --project ${var.project_id}"
}

# Cluster autoscaling
output "cluster_autoscaling" {
  description = "The cluster autoscaling configuration"
  value       = google_container_cluster.atp_cluster.cluster_autoscaling
}

# Node pool details
output "node_pools" {
  description = "Information about all node pools"
  value = {
    primary = {
      name         = google_container_node_pool.primary_nodes.name
      machine_type = google_container_node_pool.primary_nodes.node_config[0].machine_type
      disk_size_gb = google_container_node_pool.primary_nodes.node_config[0].disk_size_gb
      disk_type    = google_container_node_pool.primary_nodes.node_config[0].disk_type
      preemptible  = google_container_node_pool.primary_nodes.node_config[0].preemptible
      spot         = google_container_node_pool.primary_nodes.node_config[0].spot
    }
    spot = var.enable_spot_nodes ? {
      name         = google_container_node_pool.spot_nodes[0].name
      machine_type = google_container_node_pool.spot_nodes[0].node_config[0].machine_type
      disk_size_gb = google_container_node_pool.spot_nodes[0].node_config[0].disk_size_gb
      disk_type    = google_container_node_pool.spot_nodes[0].node_config[0].disk_type
      spot         = google_container_node_pool.spot_nodes[0].node_config[0].spot
    } : null
    gpu = var.enable_gpu_nodes ? {
      name         = google_container_node_pool.gpu_nodes[0].name
      machine_type = google_container_node_pool.gpu_nodes[0].node_config[0].machine_type
      disk_size_gb = google_container_node_pool.gpu_nodes[0].node_config[0].disk_size_gb
      disk_type    = google_container_node_pool.gpu_nodes[0].node_config[0].disk_type
      gpu_config   = google_container_node_pool.gpu_nodes[0].node_config[0].guest_accelerator
    } : null
  }
}

# Security posture
output "security_posture_config" {
  description = "The security posture configuration"
  value       = google_container_cluster.atp_cluster.security_posture_config
}

# Binary authorization
output "binary_authorization" {
  description = "The binary authorization configuration"
  value       = google_container_cluster.atp_cluster.binary_authorization
}

# Cost management
output "cost_management_config" {
  description = "The cost management configuration"
  value       = google_container_cluster.atp_cluster.cost_management_config
}

# Resource usage export
output "resource_usage_export_config" {
  description = "The resource usage export configuration"
  value       = google_container_cluster.atp_cluster.resource_usage_export_config
}