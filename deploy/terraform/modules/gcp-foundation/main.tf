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

# GCP Foundation Module for ATP Platform
# Provides core GCP infrastructure including networking, security, and monitoring

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
  common_labels = {
    project     = var.project_name
    environment = var.environment
    component   = "atp-platform"
    managed_by  = "terraform"
  }
}

# Enable required APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "compute.googleapis.com",
    "container.googleapis.com",
    "cloudsql.googleapis.com",
    "redis.googleapis.com",
    "secretmanager.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "cloudtrace.googleapis.com",
    "servicenetworking.googleapis.com",
    "cloudkms.googleapis.com",
    "iamcredentials.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "dns.googleapis.com",
    "certificatemanager.googleapis.com"
  ])

  project = var.project_id
  service = each.value

  disable_dependent_services = false
  disable_on_destroy         = false
}

# VPC Network
resource "google_compute_network" "atp_vpc" {
  name                    = "${var.project_name}-vpc-${var.environment}"
  auto_create_subnetworks = false
  mtu                     = 1460
  project                 = var.project_id

  depends_on = [google_project_service.required_apis]
}

# Subnets
resource "google_compute_subnetwork" "atp_subnet" {
  name          = "${var.project_name}-subnet-${var.environment}"
  ip_cidr_range = var.subnet_cidr
  region        = var.region
  network       = google_compute_network.atp_vpc.id
  project       = var.project_id

  # Secondary ranges for GKE
  secondary_ip_range {
    range_name    = "atp-pods"
    ip_cidr_range = var.pods_cidr
  }

  secondary_ip_range {
    range_name    = "atp-services"
    ip_cidr_range = var.services_cidr
  }

  # Enable private Google access
  private_ip_google_access = true

  # Enable flow logs for security monitoring
  log_config {
    aggregation_interval = "INTERVAL_10_MIN"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# Cloud Router for NAT
resource "google_compute_router" "atp_router" {
  name    = "${var.project_name}-router-${var.environment}"
  region  = var.region
  network = google_compute_network.atp_vpc.id
  project = var.project_id

  bgp {
    asn = 64514
  }
}

# Cloud NAT for outbound internet access
resource "google_compute_router_nat" "atp_nat" {
  name                               = "${var.project_name}-nat-${var.environment}"
  router                             = google_compute_router.atp_router.name
  region                             = var.region
  project                            = var.project_id
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

# Firewall rules
resource "google_compute_firewall" "allow_internal" {
  name    = "${var.project_name}-allow-internal-${var.environment}"
  network = google_compute_network.atp_vpc.name
  project = var.project_id

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "icmp"
  }

  source_ranges = [var.subnet_cidr, var.pods_cidr, var.services_cidr]
  target_tags   = ["atp-internal"]
}

resource "google_compute_firewall" "allow_health_checks" {
  name    = "${var.project_name}-allow-health-checks-${var.environment}"
  network = google_compute_network.atp_vpc.name
  project = var.project_id

  allow {
    protocol = "tcp"
    ports    = ["8080", "8443", "9090", "9443"]
  }

  source_ranges = ["130.211.0.0/22", "35.191.0.0/16"]
  target_tags   = ["atp-health-check"]
}

resource "google_compute_firewall" "allow_ssh" {
  name    = "${var.project_name}-allow-ssh-${var.environment}"
  network = google_compute_network.atp_vpc.name
  project = var.project_id

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = var.ssh_source_ranges
  target_tags   = ["atp-ssh"]
}

# Global IP for load balancer
resource "google_compute_global_address" "atp_lb_ip" {
  name         = "${var.project_name}-lb-ip-${var.environment}"
  project      = var.project_id
  address_type = "EXTERNAL"
}

# DNS Zone (if managing DNS)
resource "google_dns_managed_zone" "atp_zone" {
  count       = var.manage_dns ? 1 : 0
  name        = "${var.project_name}-zone-${var.environment}"
  dns_name    = "${var.domain_name}."
  description = "ATP Platform DNS zone for ${var.environment}"
  project     = var.project_id

  labels = local.common_labels

  dnssec_config {
    state = "on"
  }
}

# KMS Key Ring
resource "google_kms_key_ring" "atp_keyring" {
  name     = "${var.project_name}-keyring-${var.environment}"
  location = var.region
  project  = var.project_id
}

# KMS Keys
resource "google_kms_crypto_key" "atp_database_key" {
  name     = "database-encryption-key"
  key_ring = google_kms_key_ring.atp_keyring.id
  purpose  = "ENCRYPT_DECRYPT"

  version_template {
    algorithm = "GOOGLE_SYMMETRIC_ENCRYPTION"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_kms_crypto_key" "atp_secrets_key" {
  name     = "secrets-encryption-key"
  key_ring = google_kms_key_ring.atp_keyring.id
  purpose  = "ENCRYPT_DECRYPT"

  version_template {
    algorithm = "GOOGLE_SYMMETRIC_ENCRYPTION"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Service Accounts
resource "google_service_account" "atp_gke_sa" {
  account_id   = "${var.project_name}-gke-${var.environment}"
  display_name = "ATP GKE Service Account"
  description  = "Service account for ATP GKE cluster"
  project      = var.project_id
}

resource "google_service_account" "atp_workload_sa" {
  account_id   = "${var.project_name}-workload-${var.environment}"
  display_name = "ATP Workload Service Account"
  description  = "Service account for ATP workloads"
  project      = var.project_id
}

# IAM bindings for service accounts
resource "google_project_iam_member" "gke_sa_bindings" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/cloudtrace.agent"
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.atp_gke_sa.email}"
}

resource "google_project_iam_member" "workload_sa_bindings" {
  for_each = toset([
    "roles/secretmanager.secretAccessor",
    "roles/cloudsql.client",
    "roles/redis.editor",
    "roles/monitoring.metricWriter",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent"
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.atp_workload_sa.email}"
}

# Workload Identity binding
resource "google_service_account_iam_binding" "workload_identity_binding" {
  service_account_id = google_service_account.atp_workload_sa.name
  role               = "roles/iam.workloadIdentityUser"

  members = [
    "serviceAccount:${var.project_id}.svc.id.goog[${var.k8s_namespace}/${var.k8s_service_account}]"
  ]
}

# Private Service Connection for Cloud SQL
resource "google_compute_global_address" "private_ip_address" {
  name          = "${var.project_name}-private-ip-${var.environment}"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.atp_vpc.id
  project       = var.project_id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.atp_vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_address.name]

  depends_on = [google_project_service.required_apis]
}

# Monitoring and Logging
resource "google_logging_project_sink" "atp_audit_sink" {
  name        = "${var.project_name}-audit-sink-${var.environment}"
  destination = "storage.googleapis.com/${google_storage_bucket.audit_logs.name}"
  project     = var.project_id

  filter = "protoPayload.serviceName=\"cloudaudit.googleapis.com\" OR protoPayload.serviceName=\"k8s.io\""

  unique_writer_identity = true
}

# Storage bucket for audit logs
resource "google_storage_bucket" "audit_logs" {
  name          = "${var.project_name}-audit-logs-${var.environment}-${random_id.bucket_suffix.hex}"
  location      = var.region
  project       = var.project_id
  force_destroy = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }

  encryption {
    default_kms_key_name = google_kms_crypto_key.atp_secrets_key.id
  }

  labels = local.common_labels
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# IAM binding for audit log sink
resource "google_storage_bucket_iam_member" "audit_sink_writer" {
  bucket = google_storage_bucket.audit_logs.name
  role   = "roles/storage.objectCreator"
  member = google_logging_project_sink.atp_audit_sink.writer_identity
}

# Monitoring notification channels
resource "google_monitoring_notification_channel" "email" {
  count        = length(var.alert_email_addresses)
  display_name = "Email Notification ${count.index + 1}"
  type         = "email"
  project      = var.project_id

  labels = {
    email_address = var.alert_email_addresses[count.index]
  }
}

# Basic monitoring alert policy
resource "google_monitoring_alert_policy" "high_cpu_usage" {
  display_name = "High CPU Usage - ${var.environment}"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "CPU usage above 80%"

    condition_threshold {
      filter          = "resource.type=\"gce_instance\""
      duration        = "300s"
      comparison      = "COMPARISON_GREATER_THAN"
      threshold_value = 0.8

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = google_monitoring_notification_channel.email[*].id

  alert_strategy {
    auto_close = "1800s"
  }
}

# Security Command Center (if available)
resource "google_security_center_notification_config" "atp_scc_notification" {
  count           = var.enable_security_center ? 1 : 0
  config_id       = "${var.project_name}-scc-${var.environment}"
  organization    = var.organization_id
  description     = "ATP Security Command Center notifications"
  pubsub_topic    = google_pubsub_topic.security_notifications[0].id
  streaming_config {
    filter = "state=\"ACTIVE\""
  }
}

resource "google_pubsub_topic" "security_notifications" {
  count   = var.enable_security_center ? 1 : 0
  name    = "${var.project_name}-security-notifications-${var.environment}"
  project = var.project_id

  labels = local.common_labels
}