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

# Outputs for GCP Foundation Module

# Network outputs
output "vpc_id" {
  description = "The ID of the VPC network"
  value       = google_compute_network.atp_vpc.id
}

output "vpc_name" {
  description = "The name of the VPC network"
  value       = google_compute_network.atp_vpc.name
}

output "subnet_id" {
  description = "The ID of the main subnet"
  value       = google_compute_subnetwork.atp_subnet.id
}

output "subnet_name" {
  description = "The name of the main subnet"
  value       = google_compute_subnetwork.atp_subnet.name
}

output "pods_secondary_range_name" {
  description = "The name of the pods secondary IP range"
  value       = "atp-pods"
}

output "services_secondary_range_name" {
  description = "The name of the services secondary IP range"
  value       = "atp-services"
}

# Load balancer outputs
output "global_ip_address" {
  description = "The global IP address for the load balancer"
  value       = google_compute_global_address.atp_lb_ip.address
}

output "global_ip_name" {
  description = "The name of the global IP address"
  value       = google_compute_global_address.atp_lb_ip.name
}

# Service account outputs
output "gke_service_account_email" {
  description = "Email of the GKE service account"
  value       = google_service_account.atp_gke_sa.email
}

output "workload_service_account_email" {
  description = "Email of the workload service account"
  value       = google_service_account.atp_workload_sa.email
}

# KMS outputs
output "database_kms_key_id" {
  description = "The ID of the database encryption key"
  value       = google_kms_crypto_key.atp_database_key.id
}

output "secrets_kms_key_id" {
  description = "The ID of the secrets encryption key"
  value       = google_kms_crypto_key.atp_secrets_key.id
}

output "kms_keyring_id" {
  description = "The ID of the KMS key ring"
  value       = google_kms_key_ring.atp_keyring.id
}

# DNS outputs
output "dns_zone_name" {
  description = "The name of the DNS zone"
  value       = var.manage_dns ? google_dns_managed_zone.atp_zone[0].name : null
}

output "dns_zone_name_servers" {
  description = "The name servers for the DNS zone"
  value       = var.manage_dns ? google_dns_managed_zone.atp_zone[0].name_servers : null
}

# Storage outputs
output "audit_logs_bucket_name" {
  description = "The name of the audit logs storage bucket"
  value       = google_storage_bucket.audit_logs.name
}

output "audit_logs_bucket_url" {
  description = "The URL of the audit logs storage bucket"
  value       = google_storage_bucket.audit_logs.url
}

# Monitoring outputs
output "notification_channel_ids" {
  description = "IDs of the monitoring notification channels"
  value       = google_monitoring_notification_channel.email[*].id
}

# Security outputs
output "security_notification_topic" {
  description = "The Pub/Sub topic for security notifications"
  value       = var.enable_security_center ? google_pubsub_topic.security_notifications[0].name : null
}

# Private service connection outputs
output "private_vpc_connection_id" {
  description = "The ID of the private VPC connection"
  value       = google_service_networking_connection.private_vpc_connection.id
}

output "private_ip_address_name" {
  description = "The name of the private IP address range"
  value       = google_compute_global_address.private_ip_address.name
}

# Router outputs
output "router_name" {
  description = "The name of the Cloud Router"
  value       = google_compute_router.atp_router.name
}

output "nat_name" {
  description = "The name of the Cloud NAT"
  value       = google_compute_router_nat.atp_nat.name
}

# Common labels output
output "common_labels" {
  description = "Common labels applied to all resources"
  value = {
    project     = var.project_name
    environment = var.environment
    component   = "atp-platform"
    managed_by  = "terraform"
  }
}

# Project information
output "project_id" {
  description = "The GCP project ID"
  value       = var.project_id
}

output "region" {
  description = "The GCP region"
  value       = var.region
}

output "zones" {
  description = "The GCP zones"
  value       = var.zones
}