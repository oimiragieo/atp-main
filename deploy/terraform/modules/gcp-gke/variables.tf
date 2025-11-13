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

# Variables for GCP GKE Module

# Basic configuration
variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "project_name" {
  description = "The project name used for resource naming"
  type        = string
  default     = "atp"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "region" {
  description = "The GCP region for the cluster"
  type        = string
  default     = "us-central1"
}

variable "zones" {
  description = "The GCP zones for the cluster"
  type        = list(string)
  default     = ["us-central1-a", "us-central1-b", "us-central1-c"]
}

# Network configuration
variable "vpc_id" {
  description = "The VPC network ID"
  type        = string
}

variable "vpc_name" {
  description = "The VPC network name"
  type        = string
}

variable "subnet_id" {
  description = "The subnet ID"
  type        = string
}

variable "subnet_name" {
  description = "The subnet name"
  type        = string
}

variable "pods_secondary_range_name" {
  description = "The name of the pods secondary IP range"
  type        = string
  default     = "atp-pods"
}

variable "services_secondary_range_name" {
  description = "The name of the services secondary IP range"
  type        = string
  default     = "atp-services"
}

# Cluster configuration
variable "kubernetes_version" {
  description = "The Kubernetes version for the cluster"
  type        = string
  default     = "1.28"
}

variable "regional_cluster" {
  description = "Whether to create a regional cluster"
  type        = bool
  default     = true
}

variable "enable_deletion_protection" {
  description = "Enable deletion protection for the cluster"
  type        = bool
  default     = true
}

# Service accounts
variable "gke_service_account_email" {
  description = "Email of the GKE service account"
  type        = string
}

# Private cluster configuration
variable "enable_private_nodes" {
  description = "Enable private nodes"
  type        = bool
  default     = true
}

variable "enable_private_endpoint" {
  description = "Enable private endpoint"
  type        = bool
  default     = false
}

variable "master_ipv4_cidr_block" {
  description = "The IP range for the master network"
  type        = string
  default     = "172.16.0.0/28"
}

variable "enable_master_global_access" {
  description = "Enable global access to the master endpoint"
  type        = bool
  default     = false
}

variable "master_authorized_networks" {
  description = "List of master authorized networks"
  type = list(object({
    cidr_block   = string
    display_name = string
  }))
  default = []
}

# Network policy
variable "enable_network_policy" {
  description = "Enable network policy"
  type        = bool
  default     = true
}

# Addons configuration
variable "enable_hpa" {
  description = "Enable horizontal pod autoscaling"
  type        = bool
  default     = true
}

variable "enable_http_load_balancing" {
  description = "Enable HTTP load balancing"
  type        = bool
  default     = true
}

variable "enable_dns_cache" {
  description = "Enable DNS cache"
  type        = bool
  default     = true
}

variable "enable_filestore_csi" {
  description = "Enable Filestore CSI driver"
  type        = bool
  default     = false
}

variable "enable_config_connector" {
  description = "Enable Config Connector"
  type        = bool
  default     = false
}

variable "enable_backup_agent" {
  description = "Enable GKE backup agent"
  type        = bool
  default     = true
}

# Cluster autoscaling
variable "enable_cluster_autoscaling" {
  description = "Enable cluster autoscaling"
  type        = bool
  default     = true
}

variable "cluster_autoscaling_cpu_min" {
  description = "Minimum CPU for cluster autoscaling"
  type        = number
  default     = 1
}

variable "cluster_autoscaling_cpu_max" {
  description = "Maximum CPU for cluster autoscaling"
  type        = number
  default     = 100
}

variable "cluster_autoscaling_memory_min" {
  description = "Minimum memory for cluster autoscaling (GB)"
  type        = number
  default     = 1
}

variable "cluster_autoscaling_memory_max" {
  description = "Maximum memory for cluster autoscaling (GB)"
  type        = number
  default     = 1000
}

# Maintenance policy
variable "maintenance_start_time" {
  description = "Start time for maintenance window"
  type        = string
  default     = "2023-01-01T02:00:00Z"
}

variable "maintenance_end_time" {
  description = "End time for maintenance window"
  type        = string
  default     = "2023-01-01T06:00:00Z"
}

variable "maintenance_recurrence" {
  description = "Recurrence for maintenance window"
  type        = string
  default     = "FREQ=WEEKLY;BYDAY=SA"
}

# Monitoring and logging
variable "enable_managed_prometheus" {
  description = "Enable managed Prometheus"
  type        = bool
  default     = true
}

variable "usage_export_dataset_id" {
  description = "BigQuery dataset ID for usage export"
  type        = string
  default     = ""
}

# Security
variable "enable_binary_authorization" {
  description = "Enable Binary Authorization"
  type        = bool
  default     = false
}

variable "security_posture_mode" {
  description = "Security posture mode"
  type        = string
  default     = "BASIC"
  validation {
    condition     = contains(["DISABLED", "BASIC", "ENTERPRISE"], var.security_posture_mode)
    error_message = "Security posture mode must be one of: DISABLED, BASIC, ENTERPRISE."
  }
}

variable "vulnerability_mode" {
  description = "Vulnerability scanning mode"
  type        = string
  default     = "VULNERABILITY_BASIC"
  validation {
    condition     = contains(["VULNERABILITY_DISABLED", "VULNERABILITY_BASIC", "VULNERABILITY_ENTERPRISE"], var.vulnerability_mode)
    error_message = "Vulnerability mode must be one of: VULNERABILITY_DISABLED, VULNERABILITY_BASIC, VULNERABILITY_ENTERPRISE."
  }
}

variable "enable_cost_management" {
  description = "Enable cost management"
  type        = bool
  default     = true
}

# Primary node pool configuration
variable "primary_node_count" {
  description = "Number of nodes in the primary node pool"
  type        = number
  default     = 3
}

variable "enable_node_autoscaling" {
  description = "Enable node pool autoscaling"
  type        = bool
  default     = true
}

variable "primary_min_nodes" {
  description = "Minimum number of nodes in primary pool"
  type        = number
  default     = 1
}

variable "primary_max_nodes" {
  description = "Maximum number of nodes in primary pool"
  type        = number
  default     = 10
}

variable "primary_machine_type" {
  description = "Machine type for primary nodes"
  type        = string
  default     = "e2-standard-4"
}

variable "primary_disk_type" {
  description = "Disk type for primary nodes"
  type        = string
  default     = "pd-ssd"
}

variable "primary_disk_size" {
  description = "Disk size for primary nodes (GB)"
  type        = number
  default     = 100
}

variable "primary_local_ssd_count" {
  description = "Number of local SSDs for primary nodes"
  type        = number
  default     = 0
}

variable "enable_preemptible_nodes" {
  description = "Enable preemptible nodes in primary pool"
  type        = bool
  default     = false
}

variable "primary_node_taints" {
  description = "Taints for primary nodes"
  type = list(object({
    key    = string
    value  = string
    effect = string
  }))
  default = []
}

# Spot node pool configuration
variable "enable_spot_nodes" {
  description = "Enable spot node pool"
  type        = bool
  default     = true
}

variable "spot_min_nodes" {
  description = "Minimum number of spot nodes"
  type        = number
  default     = 0
}

variable "spot_max_nodes" {
  description = "Maximum number of spot nodes"
  type        = number
  default     = 20
}

variable "spot_machine_type" {
  description = "Machine type for spot nodes"
  type        = string
  default     = "e2-standard-2"
}

variable "spot_disk_type" {
  description = "Disk type for spot nodes"
  type        = string
  default     = "pd-standard"
}

variable "spot_disk_size" {
  description = "Disk size for spot nodes (GB)"
  type        = number
  default     = 50
}

variable "spot_max_surge" {
  description = "Max surge for spot node pool upgrades"
  type        = number
  default     = 1
}

variable "spot_max_unavailable" {
  description = "Max unavailable for spot node pool upgrades"
  type        = number
  default     = 0
}

# GPU node pool configuration
variable "enable_gpu_nodes" {
  description = "Enable GPU node pool"
  type        = bool
  default     = false
}

variable "gpu_min_nodes" {
  description = "Minimum number of GPU nodes"
  type        = number
  default     = 0
}

variable "gpu_max_nodes" {
  description = "Maximum number of GPU nodes"
  type        = number
  default     = 5
}

variable "gpu_machine_type" {
  description = "Machine type for GPU nodes"
  type        = string
  default     = "n1-standard-4"
}

variable "gpu_disk_type" {
  description = "Disk type for GPU nodes"
  type        = string
  default     = "pd-ssd"
}

variable "gpu_disk_size" {
  description = "Disk size for GPU nodes (GB)"
  type        = number
  default     = 100
}

variable "gpu_type" {
  description = "GPU type"
  type        = string
  default     = "nvidia-tesla-t4"
}

variable "gpu_count" {
  description = "Number of GPUs per node"
  type        = number
  default     = 1
}

# Node configuration
variable "node_image_type" {
  description = "Node image type"
  type        = string
  default     = "COS_CONTAINERD"
}

variable "enable_secure_boot" {
  description = "Enable secure boot for nodes"
  type        = bool
  default     = true
}

variable "enable_integrity_monitoring" {
  description = "Enable integrity monitoring for nodes"
  type        = bool
  default     = true
}

variable "node_location_policy" {
  description = "Node location policy for autoscaling"
  type        = string
  default     = "BALANCED"
  validation {
    condition     = contains(["BALANCED", "ANY"], var.node_location_policy)
    error_message = "Node location policy must be either BALANCED or ANY."
  }
}

variable "node_tags" {
  description = "Network tags for nodes"
  type        = list(string)
  default     = ["atp-gke-node"]
}

# Upgrade configuration
variable "enable_auto_repair" {
  description = "Enable auto repair for nodes"
  type        = bool
  default     = true
}

variable "enable_auto_upgrade" {
  description = "Enable auto upgrade for nodes"
  type        = bool
  default     = true
}

variable "upgrade_strategy" {
  description = "Upgrade strategy for node pools"
  type        = string
  default     = "BLUE_GREEN"
  validation {
    condition     = contains(["SURGE", "BLUE_GREEN"], var.upgrade_strategy)
    error_message = "Upgrade strategy must be either SURGE or BLUE_GREEN."
  }
}

variable "max_surge" {
  description = "Maximum surge for node pool upgrades"
  type        = number
  default     = 1
}

variable "max_unavailable" {
  description = "Maximum unavailable for node pool upgrades"
  type        = number
  default     = 0
}

# Blue-green upgrade settings
variable "blue_green_batch_percentage" {
  description = "Batch percentage for blue-green upgrades"
  type        = number
  default     = 0.2
}

variable "blue_green_batch_node_count" {
  description = "Batch node count for blue-green upgrades"
  type        = number
  default     = null
}

variable "blue_green_batch_soak_duration" {
  description = "Batch soak duration for blue-green upgrades"
  type        = string
  default     = "60s"
}

variable "blue_green_node_pool_soak_duration" {
  description = "Node pool soak duration for blue-green upgrades"
  type        = string
  default     = "300s"
}

# Reservation affinity
variable "reservation_affinity" {
  description = "Reservation affinity configuration"
  type = object({
    consume_reservation_type = string
    key                      = string
    values                   = list(string)
  })
  default = null
}