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

# ATP Infrastructure Variables
# Comprehensive variable definitions for multi-cloud deployment

# Global Configuration
variable "project_name" {
  description = "Name of the project"
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

variable "owner" {
  description = "Owner of the infrastructure"
  type        = string
  default     = "atp-team"
}

variable "cost_center" {
  description = "Cost center for billing"
  type        = string
  default     = "engineering"
}

# Cloud Provider Configuration
variable "cloud_provider" {
  description = "Primary cloud provider (gcp, aws, azure)"
  type        = string
  default     = "gcp"
  validation {
    condition     = contains(["gcp", "aws", "azure"], var.cloud_provider)
    error_message = "Cloud provider must be one of: gcp, aws, azure."
  }
}

variable "multi_cloud" {
  description = "Enable multi-cloud deployment"
  type        = bool
  default     = false
}

# Terraform State Configuration
variable "terraform_state_bucket" {
  description = "GCS bucket for Terraform state"
  type        = string
  default     = "atp-terraform-state"
}

# Network Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

# Kubernetes Configuration
variable "kubernetes_version" {
  description = "Kubernetes version"
  type        = string
  default     = "1.28"
}

# GCP Configuration
variable "gcp_project_id" {
  description = "GCP project ID"
  type        = string
  default     = ""
}

variable "gcp_region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "gcp_node_pools" {
  description = "GKE node pool configurations"
  type = list(object({
    name               = string
    machine_type       = string
    min_count         = number
    max_count         = number
    initial_node_count = number
    disk_size_gb      = number
    disk_type         = string
    preemptible       = bool
    spot              = bool
    labels            = map(string)
    taints = list(object({
      key    = string
      value  = string
      effect = string
    }))
  }))
  default = [
    {
      name               = "general"
      machine_type       = "e2-standard-4"
      min_count         = 1
      max_count         = 10
      initial_node_count = 3
      disk_size_gb      = 100
      disk_type         = "pd-standard"
      preemptible       = false
      spot              = false
      labels = {
        role = "general"
      }
      taints = []
    },
    {
      name               = "compute"
      machine_type       = "c2-standard-8"
      min_count         = 0
      max_count         = 20
      initial_node_count = 2
      disk_size_gb      = 200
      disk_type         = "pd-ssd"
      preemptible       = false
      spot              = true
      labels = {
        role = "compute"
      }
      taints = [
        {
          key    = "compute"
          value  = "true"
          effect = "NO_SCHEDULE"
        }
      ]
    }
  ]
}

# AWS Configuration
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-west-2"
}

variable "aws_node_groups" {
  description = "EKS node group configurations"
  type = list(object({
    name           = string
    instance_types = list(string)
    min_size      = number
    max_size      = number
    desired_size  = number
    disk_size     = number
    capacity_type = string
    labels        = map(string)
    taints = list(object({
      key    = string
      value  = string
      effect = string
    }))
  }))
  default = [
    {
      name           = "general"
      instance_types = ["m5.xlarge"]
      min_size      = 1
      max_size      = 10
      desired_size  = 3
      disk_size     = 100
      capacity_type = "ON_DEMAND"
      labels = {
        role = "general"
      }
      taints = []
    },
    {
      name           = "compute"
      instance_types = ["c5.2xlarge"]
      min_size      = 0
      max_size      = 20
      desired_size  = 2
      disk_size     = 200
      capacity_type = "SPOT"
      labels = {
        role = "compute"
      }
      taints = [
        {
          key    = "compute"
          value  = "true"
          effect = "NO_SCHEDULE"
        }
      ]
    }
  ]
}

# Azure Configuration
variable "azure_location" {
  description = "Azure location"
  type        = string
  default     = "East US"
}

variable "azure_node_pools" {
  description = "AKS node pool configurations"
  type = list(object({
    name                = string
    vm_size            = string
    min_count          = number
    max_count          = number
    node_count         = number
    os_disk_size_gb    = number
    os_disk_type       = string
    priority           = string
    spot_max_price     = number
    node_labels        = map(string)
    node_taints        = list(string)
  }))
  default = [
    {
      name                = "general"
      vm_size            = "Standard_D4s_v3"
      min_count          = 1
      max_count          = 10
      node_count         = 3
      os_disk_size_gb    = 100
      os_disk_type       = "Managed"
      priority           = "Regular"
      spot_max_price     = -1
      node_labels = {
        role = "general"
      }
      node_taints = []
    },
    {
      name                = "compute"
      vm_size            = "Standard_F8s_v2"
      min_count          = 0
      max_count          = 20
      node_count         = 2
      os_disk_size_gb    = 200
      os_disk_type       = "Managed"
      priority           = "Spot"
      spot_max_price     = 0.1
      node_labels = {
        role = "compute"
      }
      node_taints = ["compute=true:NoSchedule"]
    }
  ]
}

# Database Configuration
variable "database_version" {
  description = "Database version"
  type        = string
  default     = "15"
}

variable "database_tier" {
  description = "Database instance tier/class"
  type        = string
  default     = "db-f1-micro"
}

# Redis Configuration
variable "redis_host" {
  description = "Redis host"
  type        = string
  default     = "redis-service"
}

# Application Configuration
variable "atp_image_tag" {
  description = "ATP application image tag"
  type        = string
  default     = "latest"
}

variable "atp_chart_version" {
  description = "ATP Helm chart version"
  type        = string
  default     = "1.0.0"
}

variable "atp_replicas" {
  description = "Number of ATP replicas"
  type        = number
  default     = 3
}

# Monitoring Configuration
variable "enable_monitoring" {
  description = "Enable monitoring stack"
  type        = bool
  default     = true
}

variable "prometheus_chart_version" {
  description = "Prometheus Helm chart version"
  type        = string
  default     = "45.0.0"
}

# Security Configuration
variable "enable_network_policies" {
  description = "Enable Kubernetes network policies"
  type        = bool
  default     = true
}

variable "enable_pod_security_policies" {
  description = "Enable pod security policies"
  type        = bool
  default     = true
}

variable "enable_rbac" {
  description = "Enable RBAC"
  type        = bool
  default     = true
}

# Backup Configuration
variable "enable_backups" {
  description = "Enable automated backups"
  type        = bool
  default     = true
}

variable "backup_retention_days" {
  description = "Backup retention period in days"
  type        = number
  default     = 30
}

# Scaling Configuration
variable "enable_autoscaling" {
  description = "Enable horizontal pod autoscaling"
  type        = bool
  default     = true
}

variable "enable_vertical_scaling" {
  description = "Enable vertical pod autoscaling"
  type        = bool
  default     = true
}

# Cost Optimization
variable "enable_spot_instances" {
  description = "Enable spot/preemptible instances"
  type        = bool
  default     = true
}

variable "cost_optimization_level" {
  description = "Cost optimization level (low, medium, high)"
  type        = string
  default     = "medium"
  validation {
    condition     = contains(["low", "medium", "high"], var.cost_optimization_level)
    error_message = "Cost optimization level must be one of: low, medium, high."
  }
}

# Disaster Recovery
variable "enable_disaster_recovery" {
  description = "Enable disaster recovery"
  type        = bool
  default     = true
}

variable "dr_region" {
  description = "Disaster recovery region"
  type        = string
  default     = ""
}

# Compliance
variable "compliance_standards" {
  description = "Compliance standards to enforce"
  type        = list(string)
  default     = ["soc2", "gdpr", "iso27001"]
}

variable "enable_audit_logging" {
  description = "Enable audit logging"
  type        = bool
  default     = true
}

# Development Configuration
variable "enable_development_tools" {
  description = "Enable development tools"
  type        = bool
  default     = false
}

variable "enable_debug_mode" {
  description = "Enable debug mode"
  type        = bool
  default     = false
}