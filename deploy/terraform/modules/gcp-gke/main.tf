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

# GKE Module for ATP Platform
# Provides enterprise-grade Kubernetes cluster with security and monitoring

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }
}

# Local variables
locals {
  cluster_name = "${var.project_name}-gke-${var.environment}"
  
  common_labels = {
    project     = var.project_name
    environment = var.environment
    component   = "gke-cluster"
    managed_by  = "terraform"
  }

  node_pool_labels = merge(local.common_labels, {
    component = "gke-node-pool"
  })
}

# GKE Cluster
resource "google_container_cluster" "atp_cluster" {
  name     = local.cluster_name
  location = var.regional_cluster ? var.region : var.zones[0]
  project  = var.project_id

  # Network configuration
  network    = var.vpc_name
  subnetwork = var.subnet_name

  # IP allocation policy for VPC-native cluster
  ip_allocation_policy {
    cluster_secondary_range_name  = var.pods_secondary_range_name
    services_secondary_range_name = var.services_secondary_range_name
  }

  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  # Cluster configuration
  min_master_version = var.kubernetes_version

  # Enable Workload Identity
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Network policy
  network_policy {
    enabled  = var.enable_network_policy
    provider = var.enable_network_policy ? "CALICO" : null
  }

  # Enable network policy addon
  addons_config {
    network_policy_config {
      disabled = !var.enable_network_policy
    }

    horizontal_pod_autoscaling {
      disabled = !var.enable_hpa
    }

    http_load_balancing {
      disabled = !var.enable_http_load_balancing
    }

    dns_cache_config {
      enabled = var.enable_dns_cache
    }

    gcp_filestore_csi_driver_config {
      enabled = var.enable_filestore_csi
    }

    gce_persistent_disk_csi_driver_config {
      enabled = true
    }

    config_connector_config {
      enabled = var.enable_config_connector
    }

    gke_backup_agent_config {
      enabled = var.enable_backup_agent
    }
  }

  # Cluster autoscaling
  dynamic "cluster_autoscaling" {
    for_each = var.enable_cluster_autoscaling ? [1] : []
    content {
      enabled = true
      resource_limits {
        resource_type = "cpu"
        minimum       = var.cluster_autoscaling_cpu_min
        maximum       = var.cluster_autoscaling_cpu_max
      }
      resource_limits {
        resource_type = "memory"
        minimum       = var.cluster_autoscaling_memory_min
        maximum       = var.cluster_autoscaling_memory_max
      }
      auto_provisioning_defaults {
        service_account = var.gke_service_account_email
        oauth_scopes = [
          "https://www.googleapis.com/auth/cloud-platform"
        ]
      }
    }
  }

  # Master auth configuration
  master_auth {
    client_certificate_config {
      issue_client_certificate = false
    }
  }

  # Private cluster configuration
  private_cluster_config {
    enable_private_nodes    = var.enable_private_nodes
    enable_private_endpoint = var.enable_private_endpoint
    master_ipv4_cidr_block  = var.master_ipv4_cidr_block

    master_global_access_config {
      enabled = var.enable_master_global_access
    }
  }

  # Master authorized networks
  dynamic "master_authorized_networks_config" {
    for_each = length(var.master_authorized_networks) > 0 ? [1] : []
    content {
      dynamic "cidr_blocks" {
        for_each = var.master_authorized_networks
        content {
          cidr_block   = cidr_blocks.value.cidr_block
          display_name = cidr_blocks.value.display_name
        }
      }
    }
  }

  # Maintenance policy
  maintenance_policy {
    recurring_window {
      start_time = var.maintenance_start_time
      end_time   = var.maintenance_end_time
      recurrence = var.maintenance_recurrence
    }
  }

  # Resource usage export
  resource_usage_export_config {
    enable_network_egress_metering       = true
    enable_resource_consumption_metering = true
    bigquery_destination {
      dataset_id = var.usage_export_dataset_id
    }
  }

  # Logging and monitoring
  logging_service    = "logging.googleapis.com/kubernetes"
  monitoring_service = "monitoring.googleapis.com/kubernetes"

  logging_config {
    enable_components = [
      "SYSTEM_COMPONENTS",
      "WORKLOADS",
      "API_SERVER"
    ]
  }

  monitoring_config {
    enable_components = [
      "SYSTEM_COMPONENTS",
      "WORKLOADS",
      "APISERVER",
      "SCHEDULER",
      "CONTROLLER_MANAGER"
    ]

    managed_prometheus {
      enabled = var.enable_managed_prometheus
    }
  }

  # Binary Authorization
  dynamic "binary_authorization" {
    for_each = var.enable_binary_authorization ? [1] : []
    content {
      evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
    }
  }

  # Security posture
  security_posture_config {
    mode               = var.security_posture_mode
    vulnerability_mode = var.vulnerability_mode
  }

  # Cost management
  cost_management_config {
    enabled = var.enable_cost_management
  }

  # Node pool defaults
  node_pool_defaults {
    node_config_defaults {
      logging_variant = "DEFAULT"
    }
  }

  # Deletion protection
  deletion_protection = var.enable_deletion_protection

  # Labels
  resource_labels = local.common_labels

  depends_on = [
    var.vpc_id,
    var.subnet_id
  ]
}

# Primary node pool
resource "google_container_node_pool" "primary_nodes" {
  name       = "${local.cluster_name}-primary-pool"
  location   = google_container_cluster.atp_cluster.location
  cluster    = google_container_cluster.atp_cluster.name
  project    = var.project_id

  # Node count configuration
  initial_node_count = var.regional_cluster ? null : var.primary_node_count
  
  dynamic "node_count" {
    for_each = var.regional_cluster ? [] : [1]
    content {
      node_count = var.primary_node_count
    }
  }

  # Autoscaling
  dynamic "autoscaling" {
    for_each = var.enable_node_autoscaling ? [1] : []
    content {
      min_node_count       = var.primary_min_nodes
      max_node_count       = var.primary_max_nodes
      location_policy      = var.node_location_policy
      total_min_node_count = var.regional_cluster ? var.primary_min_nodes * length(var.zones) : null
      total_max_node_count = var.regional_cluster ? var.primary_max_nodes * length(var.zones) : null
    }
  }

  # Node configuration
  node_config {
    preemptible  = var.enable_preemptible_nodes
    machine_type = var.primary_machine_type
    disk_type    = var.primary_disk_type
    disk_size_gb = var.primary_disk_size
    image_type   = var.node_image_type

    # Service account
    service_account = var.gke_service_account_email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    # Security
    shielded_instance_config {
      enable_secure_boot          = var.enable_secure_boot
      enable_integrity_monitoring = var.enable_integrity_monitoring
    }

    # Workload metadata
    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    # Node taints
    dynamic "taint" {
      for_each = var.primary_node_taints
      content {
        key    = taint.value.key
        value  = taint.value.value
        effect = taint.value.effect
      }
    }

    # Labels
    labels = merge(local.node_pool_labels, {
      node_pool = "primary"
    })

    # Tags
    tags = concat(var.node_tags, ["atp-gke-node", "atp-primary-pool"])

    # Metadata
    metadata = {
      disable-legacy-endpoints = "true"
    }

    # Local SSD configuration
    dynamic "local_ssd_config" {
      for_each = var.primary_local_ssd_count > 0 ? [1] : []
      content {
        count = var.primary_local_ssd_count
      }
    }

    # Reservation affinity
    dynamic "reservation_affinity" {
      for_each = var.reservation_affinity != null ? [1] : []
      content {
        consume_reservation_type = var.reservation_affinity.consume_reservation_type
        key                      = var.reservation_affinity.key
        values                   = var.reservation_affinity.values
      }
    }
  }

  # Upgrade settings
  upgrade_settings {
    strategy        = var.upgrade_strategy
    max_surge       = var.max_surge
    max_unavailable = var.max_unavailable

    blue_green_settings {
      standard_rollout_policy {
        batch_percentage    = var.blue_green_batch_percentage
        batch_node_count    = var.blue_green_batch_node_count
        batch_soak_duration = var.blue_green_batch_soak_duration
      }
      node_pool_soak_duration = var.blue_green_node_pool_soak_duration
    }
  }

  # Management
  management {
    auto_repair  = var.enable_auto_repair
    auto_upgrade = var.enable_auto_upgrade
  }

  # Network configuration
  network_config {
    create_pod_range     = false
    enable_private_nodes = var.enable_private_nodes
  }

  lifecycle {
    ignore_changes = [initial_node_count]
  }
}

# Spot node pool for cost optimization
resource "google_container_node_pool" "spot_nodes" {
  count = var.enable_spot_nodes ? 1 : 0

  name       = "${local.cluster_name}-spot-pool"
  location   = google_container_cluster.atp_cluster.location
  cluster    = google_container_cluster.atp_cluster.name
  project    = var.project_id

  # Autoscaling
  autoscaling {
    min_node_count       = var.spot_min_nodes
    max_node_count       = var.spot_max_nodes
    location_policy      = var.node_location_policy
    total_min_node_count = var.regional_cluster ? var.spot_min_nodes * length(var.zones) : null
    total_max_node_count = var.regional_cluster ? var.spot_max_nodes * length(var.zones) : null
  }

  # Node configuration
  node_config {
    spot         = true
    machine_type = var.spot_machine_type
    disk_type    = var.spot_disk_type
    disk_size_gb = var.spot_disk_size
    image_type   = var.node_image_type

    # Service account
    service_account = var.gke_service_account_email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    # Security
    shielded_instance_config {
      enable_secure_boot          = var.enable_secure_boot
      enable_integrity_monitoring = var.enable_integrity_monitoring
    }

    # Workload metadata
    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    # Node taints for spot instances
    taint {
      key    = "cloud.google.com/gke-spot"
      value  = "true"
      effect = "NO_SCHEDULE"
    }

    # Labels
    labels = merge(local.node_pool_labels, {
      node_pool = "spot"
      spot      = "true"
    })

    # Tags
    tags = concat(var.node_tags, ["atp-gke-node", "atp-spot-pool"])

    # Metadata
    metadata = {
      disable-legacy-endpoints = "true"
    }
  }

  # Upgrade settings
  upgrade_settings {
    strategy        = "SURGE"
    max_surge       = var.spot_max_surge
    max_unavailable = var.spot_max_unavailable
  }

  # Management
  management {
    auto_repair  = var.enable_auto_repair
    auto_upgrade = var.enable_auto_upgrade
  }

  # Network configuration
  network_config {
    create_pod_range     = false
    enable_private_nodes = var.enable_private_nodes
  }
}

# GPU node pool (optional)
resource "google_container_node_pool" "gpu_nodes" {
  count = var.enable_gpu_nodes ? 1 : 0

  name       = "${local.cluster_name}-gpu-pool"
  location   = google_container_cluster.atp_cluster.location
  cluster    = google_container_cluster.atp_cluster.name
  project    = var.project_id

  # Autoscaling
  autoscaling {
    min_node_count  = var.gpu_min_nodes
    max_node_count  = var.gpu_max_nodes
    location_policy = var.node_location_policy
  }

  # Node configuration
  node_config {
    machine_type = var.gpu_machine_type
    disk_type    = var.gpu_disk_type
    disk_size_gb = var.gpu_disk_size
    image_type   = var.node_image_type

    # GPU configuration
    guest_accelerator {
      type  = var.gpu_type
      count = var.gpu_count
      gpu_driver_installation_config {
        gpu_driver_version = "DEFAULT"
      }
    }

    # Service account
    service_account = var.gke_service_account_email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    # Security
    shielded_instance_config {
      enable_secure_boot          = var.enable_secure_boot
      enable_integrity_monitoring = var.enable_integrity_monitoring
    }

    # Workload metadata
    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    # Node taints for GPU nodes
    taint {
      key    = "nvidia.com/gpu"
      value  = "true"
      effect = "NO_SCHEDULE"
    }

    # Labels
    labels = merge(local.node_pool_labels, {
      node_pool = "gpu"
      gpu_type  = var.gpu_type
    })

    # Tags
    tags = concat(var.node_tags, ["atp-gke-node", "atp-gpu-pool"])

    # Metadata
    metadata = {
      disable-legacy-endpoints = "true"
    }
  }

  # Upgrade settings
  upgrade_settings {
    strategy        = "SURGE"
    max_surge       = 1
    max_unavailable = 0
  }

  # Management
  management {
    auto_repair  = var.enable_auto_repair
    auto_upgrade = var.enable_auto_upgrade
  }

  # Network configuration
  network_config {
    create_pod_range     = false
    enable_private_nodes = var.enable_private_nodes
  }
}