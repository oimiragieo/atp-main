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

# Variables for GCP Foundation Module

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
  description = "The GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "zones" {
  description = "The GCP zones for multi-zone deployments"
  type        = list(string)
  default     = ["us-central1-a", "us-central1-b", "us-central1-c"]
}

# Networking variables
variable "subnet_cidr" {
  description = "CIDR block for the main subnet"
  type        = string
  default     = "10.0.0.0/16"
}

variable "pods_cidr" {
  description = "CIDR block for GKE pods"
  type        = string
  default     = "10.1.0.0/16"
}

variable "services_cidr" {
  description = "CIDR block for GKE services"
  type        = string
  default     = "10.2.0.0/16"
}

variable "ssh_source_ranges" {
  description = "Source IP ranges allowed for SSH access"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# DNS variables
variable "manage_dns" {
  description = "Whether to manage DNS zone in this module"
  type        = bool
  default     = false
}

variable "domain_name" {
  description = "Domain name for DNS zone"
  type        = string
  default     = "atp.example.com"
}

# Kubernetes variables
variable "k8s_namespace" {
  description = "Kubernetes namespace for workload identity"
  type        = string
  default     = "atp-system"
}

variable "k8s_service_account" {
  description = "Kubernetes service account for workload identity"
  type        = string
  default     = "atp-workload"
}

# Monitoring variables
variable "alert_email_addresses" {
  description = "Email addresses for monitoring alerts"
  type        = list(string)
  default     = []
}

# Security variables
variable "enable_security_center" {
  description = "Enable Security Command Center notifications"
  type        = bool
  default     = false
}

variable "organization_id" {
  description = "GCP Organization ID (required for Security Command Center)"
  type        = string
  default     = ""
}

# Resource sizing variables
variable "enable_deletion_protection" {
  description = "Enable deletion protection for critical resources"
  type        = bool
  default     = true
}

variable "backup_retention_days" {
  description = "Number of days to retain backups"
  type        = number
  default     = 30
}

# Cost optimization variables
variable "enable_preemptible_nodes" {
  description = "Enable preemptible nodes for cost optimization"
  type        = bool
  default     = false
}

variable "enable_autoscaling" {
  description = "Enable cluster autoscaling"
  type        = bool
  default     = true
}

# Compliance variables
variable "enable_audit_logs" {
  description = "Enable comprehensive audit logging"
  type        = bool
  default     = true
}

variable "enable_binary_authorization" {
  description = "Enable Binary Authorization for container security"
  type        = bool
  default     = false
}

variable "enable_pod_security_policy" {
  description = "Enable Pod Security Policy"
  type        = bool
  default     = true
}

# High availability variables
variable "enable_multi_zone" {
  description = "Enable multi-zone deployment for high availability"
  type        = bool
  default     = true
}

variable "enable_regional_persistent_disk" {
  description = "Enable regional persistent disks for high availability"
  type        = bool
  default     = true
}

# Performance variables
variable "enable_network_policy" {
  description = "Enable Kubernetes network policies"
  type        = bool
  default     = true
}

variable "enable_ip_alias" {
  description = "Enable IP aliasing for better network performance"
  type        = bool
  default     = true
}

# Tagging and labeling
variable "additional_labels" {
  description = "Additional labels to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "resource_tags" {
  description = "Tags to apply to compute resources"
  type        = list(string)
  default     = ["atp-platform"]
}