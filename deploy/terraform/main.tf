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

# ATP Enterprise Infrastructure as Code
# Comprehensive Terraform configuration for multi-cloud deployment

terraform {
  required_version = ">= 1.5.0"
  
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # Remote state configuration
  backend "gcs" {
    bucket = var.terraform_state_bucket
    prefix = "terraform/state"
  }
}

# Local variables
locals {
  common_tags = {
    Project     = "ATP"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Owner       = var.owner
    CostCenter  = var.cost_center
  }
  
  # Generate unique resource names
  resource_prefix = "${var.project_name}-${var.environment}"
  
  # Network configuration
  vpc_cidr = var.vpc_cidr
  
  # Kubernetes configuration
  k8s_version = var.kubernetes_version
}

# Data sources
data "google_client_config" "default" {}

data "google_container_cluster" "primary" {
  count    = var.cloud_provider == "gcp" ? 1 : 0
  name     = module.gcp_gke[0].cluster_name
  location = var.gcp_region
  
  depends_on = [module.gcp_gke]
}

# Random password for databases
resource "random_password" "db_password" {
  length  = 32
  special = true
}

# GCP Infrastructure
module "gcp_foundation" {
  count  = var.cloud_provider == "gcp" || var.multi_cloud ? 1 : 0
  source = "./modules/gcp-foundation"
  
  project_id      = var.gcp_project_id
  region          = var.gcp_region
  environment     = var.environment
  resource_prefix = local.resource_prefix
  vpc_cidr        = local.vpc_cidr
  
  tags = local.common_tags
}

module "gcp_gke" {
  count  = var.cloud_provider == "gcp" || var.multi_cloud ? 1 : 0
  source = "./modules/gcp-gke"
  
  project_id         = var.gcp_project_id
  region             = var.gcp_region
  environment        = var.environment
  resource_prefix    = local.resource_prefix
  kubernetes_version = local.k8s_version
  
  # Network configuration
  network_name    = module.gcp_foundation[0].network_name
  subnet_name     = module.gcp_foundation[0].subnet_name
  
  # Node pool configuration
  node_pools = var.gcp_node_pools
  
  tags = local.common_tags
  
  depends_on = [module.gcp_foundation]
}

module "gcp_cloudsql" {
  count  = var.cloud_provider == "gcp" || var.multi_cloud ? 1 : 0
  source = "./modules/gcp-cloudsql"
  
  project_id      = var.gcp_project_id
  region          = var.gcp_region
  environment     = var.environment
  resource_prefix = local.resource_prefix
  
  # Database configuration
  database_version = var.database_version
  database_tier    = var.database_tier
  
  # Network configuration
  network_id = module.gcp_foundation[0].network_id
  
  # Security configuration
  database_password = random_password.db_password.result
  
  tags = local.common_tags
  
  depends_on = [module.gcp_foundation]
}

# AWS Infrastructure
module "aws_foundation" {
  count  = var.cloud_provider == "aws" || var.multi_cloud ? 1 : 0
  source = "./modules/aws-foundation"
  
  region          = var.aws_region
  environment     = var.environment
  resource_prefix = local.resource_prefix
  vpc_cidr        = local.vpc_cidr
  
  tags = local.common_tags
}

module "aws_eks" {
  count  = var.cloud_provider == "aws" || var.multi_cloud ? 1 : 0
  source = "./modules/aws-eks"
  
  region             = var.aws_region
  environment        = var.environment
  resource_prefix    = local.resource_prefix
  kubernetes_version = local.k8s_version
  
  # Network configuration
  vpc_id     = module.aws_foundation[0].vpc_id
  subnet_ids = module.aws_foundation[0].private_subnet_ids
  
  # Node group configuration
  node_groups = var.aws_node_groups
  
  tags = local.common_tags
  
  depends_on = [module.aws_foundation]
}

module "aws_rds" {
  count  = var.cloud_provider == "aws" || var.multi_cloud ? 1 : 0
  source = "./modules/aws-rds"
  
  region          = var.aws_region
  environment     = var.environment
  resource_prefix = local.resource_prefix
  
  # Database configuration
  engine_version = var.database_version
  instance_class = var.database_tier
  
  # Network configuration
  vpc_id     = module.aws_foundation[0].vpc_id
  subnet_ids = module.aws_foundation[0].private_subnet_ids
  
  # Security configuration
  database_password = random_password.db_password.result
  
  tags = local.common_tags
  
  depends_on = [module.aws_foundation]
}

# Azure Infrastructure
module "azure_foundation" {
  count  = var.cloud_provider == "azure" || var.multi_cloud ? 1 : 0
  source = "./modules/azure-foundation"
  
  location        = var.azure_location
  environment     = var.environment
  resource_prefix = local.resource_prefix
  
  tags = local.common_tags
}

module "azure_aks" {
  count  = var.cloud_provider == "azure" || var.multi_cloud ? 1 : 0
  source = "./modules/azure-aks"
  
  location           = var.azure_location
  environment        = var.environment
  resource_prefix    = local.resource_prefix
  kubernetes_version = local.k8s_version
  
  # Network configuration
  resource_group_name = module.azure_foundation[0].resource_group_name
  vnet_id            = module.azure_foundation[0].vnet_id
  subnet_id          = module.azure_foundation[0].subnet_id
  
  # Node pool configuration
  node_pools = var.azure_node_pools
  
  tags = local.common_tags
  
  depends_on = [module.azure_foundation]
}

module "azure_database" {
  count  = var.cloud_provider == "azure" || var.multi_cloud ? 1 : 0
  source = "./modules/azure-database"
  
  location        = var.azure_location
  environment     = var.environment
  resource_prefix = local.resource_prefix
  
  # Database configuration
  postgresql_version = var.database_version
  sku_name          = var.database_tier
  
  # Network configuration
  resource_group_name = module.azure_foundation[0].resource_group_name
  subnet_id          = module.azure_foundation[0].subnet_id
  
  # Security configuration
  administrator_password = random_password.db_password.result
  
  tags = local.common_tags
  
  depends_on = [module.azure_foundation]
}

# Kubernetes provider configuration
provider "kubernetes" {
  host                   = var.cloud_provider == "gcp" ? "https://${data.google_container_cluster.primary[0].endpoint}" : null
  token                  = var.cloud_provider == "gcp" ? data.google_client_config.default.access_token : null
  cluster_ca_certificate = var.cloud_provider == "gcp" ? base64decode(data.google_container_cluster.primary[0].master_auth.0.cluster_ca_certificate) : null
  
  # AWS EKS configuration would go here
  # Azure AKS configuration would go here
}

provider "helm" {
  kubernetes {
    host                   = var.cloud_provider == "gcp" ? "https://${data.google_container_cluster.primary[0].endpoint}" : null
    token                  = var.cloud_provider == "gcp" ? data.google_client_config.default.access_token : null
    cluster_ca_certificate = var.cloud_provider == "gcp" ? base64decode(data.google_container_cluster.primary[0].master_auth.0.cluster_ca_certificate) : null
  }
}

# Kubernetes resources
resource "kubernetes_namespace" "atp" {
  metadata {
    name = "atp"
    
    labels = {
      name        = "atp"
      environment = var.environment
      managed-by  = "terraform"
    }
    
    annotations = {
      "description" = "ATP Enterprise AI Platform namespace"
    }
  }
}

resource "kubernetes_namespace" "atp_monitoring" {
  metadata {
    name = "atp-monitoring"
    
    labels = {
      name        = "atp-monitoring"
      environment = var.environment
      managed-by  = "terraform"
    }
  }
}

# Helm releases
resource "helm_release" "atp" {
  name       = "atp"
  repository = "file://../helm/atp"
  chart      = "atp"
  namespace  = kubernetes_namespace.atp.metadata[0].name
  version    = var.atp_chart_version
  
  values = [
    templatefile("${path.module}/helm-values/${var.environment}.yaml", {
      environment     = var.environment
      image_tag      = var.atp_image_tag
      database_host  = var.cloud_provider == "gcp" ? module.gcp_cloudsql[0].connection_name : ""
      redis_host     = var.redis_host
      replicas       = var.atp_replicas
    })
  ]
  
  depends_on = [kubernetes_namespace.atp]
}

# Monitoring stack
resource "helm_release" "prometheus" {
  count = var.enable_monitoring ? 1 : 0
  
  name       = "prometheus"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  namespace  = kubernetes_namespace.atp_monitoring.metadata[0].name
  version    = var.prometheus_chart_version
  
  values = [
    file("${path.module}/helm-values/prometheus.yaml")
  ]
  
  depends_on = [kubernetes_namespace.atp_monitoring]
}

# Outputs
output "cluster_endpoint" {
  description = "Kubernetes cluster endpoint"
  value = var.cloud_provider == "gcp" ? (
    length(module.gcp_gke) > 0 ? module.gcp_gke[0].cluster_endpoint : null
  ) : null
}

output "database_connection_string" {
  description = "Database connection string"
  value = var.cloud_provider == "gcp" ? (
    length(module.gcp_cloudsql) > 0 ? module.gcp_cloudsql[0].connection_name : null
  ) : null
  sensitive = true
}

output "namespace" {
  description = "ATP namespace"
  value = kubernetes_namespace.atp.metadata[0].name
}
