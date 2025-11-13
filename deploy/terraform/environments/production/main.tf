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

# ATP Platform Production Infrastructure
# Comprehensive Infrastructure as Code for enterprise deployment

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
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
  }

  # Remote state backend
  backend "gcs" {
    bucket = "atp-terraform-state-prod"
    prefix = "terraform/state"
  }
}

# Configure providers
provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# Local variables
locals {
  environment = "prod"
  project_name = "atp"
  
  common_labels = {
    project     = local.project_name
    environment = local.environment
    managed_by  = "terraform"
    team        = "platform"
  }
}

# Data sources
data "google_client_config" "default" {}

# GCP Foundation Module
module "foundation" {
  source = "../../modules/gcp-foundation"

  project_id   = var.project_id
  project_name = local.project_name
  environment  = local.environment
  region       = var.region
  zones        = var.zones

  # Network configuration
  subnet_cidr    = var.subnet_cidr
  pods_cidr      = var.pods_cidr
  services_cidr  = var.services_cidr

  # DNS configuration
  manage_dns  = var.manage_dns
  domain_name = var.domain_name

  # Security configuration
  ssh_source_ranges        = var.ssh_source_ranges
  enable_security_center   = var.enable_security_center
  organization_id          = var.organization_id

  # Monitoring configuration
  alert_email_addresses = var.alert_email_addresses

  # Kubernetes configuration
  k8s_namespace        = var.k8s_namespace
  k8s_service_account  = var.k8s_service_account

  # Additional labels
  additional_labels = local.common_labels
}

# GKE Cluster Module
module "gke" {
  source = "../../modules/gcp-gke"

  project_id   = var.project_id
  project_name = local.project_name
  environment  = local.environment
  region       = var.region
  zones        = var.zones

  # Network configuration
  vpc_id                        = module.foundation.vpc_id
  vpc_name                      = module.foundation.vpc_name
  subnet_id                     = module.foundation.subnet_id
  subnet_name                   = module.foundation.subnet_name
  pods_secondary_range_name     = module.foundation.pods_secondary_range_name
  services_secondary_range_name = module.foundation.services_secondary_range_name

  # Service accounts
  gke_service_account_email = module.foundation.gke_service_account_email

  # Cluster configuration
  kubernetes_version       = var.kubernetes_version
  regional_cluster         = var.regional_cluster
  enable_deletion_protection = var.enable_deletion_protection

  # Private cluster configuration
  enable_private_nodes         = var.enable_private_nodes
  enable_private_endpoint      = var.enable_private_endpoint
  master_ipv4_cidr_block      = var.master_ipv4_cidr_block
  enable_master_global_access = var.enable_master_global_access
  master_authorized_networks  = var.master_authorized_networks

  # Security configuration
  enable_network_policy        = var.enable_network_policy
  enable_binary_authorization  = var.enable_binary_authorization
  security_posture_mode       = var.security_posture_mode
  vulnerability_mode          = var.vulnerability_mode

  # Node pool configuration
  primary_machine_type     = var.primary_machine_type
  primary_disk_size        = var.primary_disk_size
  primary_min_nodes        = var.primary_min_nodes
  primary_max_nodes        = var.primary_max_nodes
  enable_node_autoscaling  = var.enable_node_autoscaling

  # Spot nodes for cost optimization
  enable_spot_nodes    = var.enable_spot_nodes
  spot_machine_type    = var.spot_machine_type
  spot_min_nodes       = var.spot_min_nodes
  spot_max_nodes       = var.spot_max_nodes

  # GPU nodes (optional)
  enable_gpu_nodes     = var.enable_gpu_nodes
  gpu_machine_type     = var.gpu_machine_type
  gpu_type             = var.gpu_type
  gpu_count            = var.gpu_count

  # Monitoring and logging
  enable_managed_prometheus = var.enable_managed_prometheus
  usage_export_dataset_id   = var.usage_export_dataset_id

  # Maintenance configuration
  maintenance_start_time = var.maintenance_start_time
  maintenance_end_time   = var.maintenance_end_time
  maintenance_recurrence = var.maintenance_recurrence

  depends_on = [module.foundation]
}

# Cloud SQL Module
module "cloudsql" {
  source = "../../modules/gcp-cloudsql"

  project_id   = var.project_id
  project_name = local.project_name
  environment  = local.environment
  region       = var.region

  # Network configuration
  vpc_id                      = module.foundation.vpc_id
  private_ip_range_name       = module.foundation.private_ip_address_name
  private_vpc_connection_id   = module.foundation.private_vpc_connection_id

  # Database configuration
  database_version    = var.database_version
  machine_type        = var.database_machine_type
  disk_type          = var.database_disk_type
  disk_size          = var.database_disk_size
  high_availability  = var.database_high_availability

  # Security configuration
  enable_deletion_protection = var.enable_deletion_protection
  require_ssl               = var.database_require_ssl
  kms_key_name             = module.foundation.database_kms_key_id

  # Backup configuration
  enable_backups                    = var.database_enable_backups
  backup_start_time                = var.database_backup_start_time
  enable_point_in_time_recovery    = var.database_enable_point_in_time_recovery
  backup_retention_count           = var.database_backup_retention_count

  # Read replicas
  enable_read_replicas     = var.database_enable_read_replicas
  read_replica_count       = var.database_read_replica_count
  read_replica_regions     = var.database_read_replica_regions

  # Database and users
  database_name        = var.database_name
  app_user_name        = var.database_app_user_name
  create_readonly_user = var.database_create_readonly_user
  readonly_user_name   = var.database_readonly_user_name

  # Monitoring
  notification_channel_ids = module.foundation.notification_channel_ids

  depends_on = [module.foundation]
}

# Redis (Memorystore) Module
module "redis" {
  source = "../../modules/gcp-redis"

  project_id   = var.project_id
  project_name = local.project_name
  environment  = local.environment
  region       = var.region

  # Network configuration
  vpc_id = module.foundation.vpc_id

  # Redis configuration
  redis_version      = var.redis_version
  memory_size_gb     = var.redis_memory_size_gb
  tier              = var.redis_tier
  replica_count     = var.redis_replica_count

  # Security configuration
  auth_enabled              = var.redis_auth_enabled
  transit_encryption_mode   = var.redis_transit_encryption_mode
  kms_key_name             = module.foundation.secrets_kms_key_id

  # Backup configuration
  enable_backup_configuration = var.redis_enable_backup_configuration
  backup_start_time           = var.redis_backup_start_time

  # Monitoring
  notification_channel_ids = module.foundation.notification_channel_ids

  depends_on = [module.foundation]
}

# Configure Kubernetes provider
provider "kubernetes" {
  host                   = "https://${module.gke.cluster_endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(module.gke.cluster_ca_certificate)
}

# Configure Helm provider
provider "helm" {
  kubernetes {
    host                   = "https://${module.gke.cluster_endpoint}"
    token                  = data.google_client_config.default.access_token
    cluster_ca_certificate = base64decode(module.gke.cluster_ca_certificate)
  }
}

# Kubernetes namespace
resource "kubernetes_namespace" "atp_system" {
  metadata {
    name = var.k8s_namespace
    labels = merge(local.common_labels, {
      name = var.k8s_namespace
    })
  }

  depends_on = [module.gke]
}

# Kubernetes service account with Workload Identity
resource "kubernetes_service_account" "atp_workload" {
  metadata {
    name      = var.k8s_service_account
    namespace = kubernetes_namespace.atp_system.metadata[0].name
    annotations = {
      "iam.gke.io/gcp-service-account" = module.foundation.workload_service_account_email
    }
    labels = local.common_labels
  }

  depends_on = [kubernetes_namespace.atp_system]
}

# Install cert-manager for TLS certificates
resource "helm_release" "cert_manager" {
  name       = "cert-manager"
  repository = "https://charts.jetstack.io"
  chart      = "cert-manager"
  version    = var.cert_manager_version
  namespace  = "cert-manager"

  create_namespace = true

  set {
    name  = "installCRDs"
    value = "true"
  }

  set {
    name  = "global.leaderElection.namespace"
    value = "cert-manager"
  }

  depends_on = [module.gke]
}

# Install ingress-nginx
resource "helm_release" "ingress_nginx" {
  name       = "ingress-nginx"
  repository = "https://kubernetes.github.io/ingress-nginx"
  chart      = "ingress-nginx"
  version    = var.ingress_nginx_version
  namespace  = "ingress-nginx"

  create_namespace = true

  values = [
    yamlencode({
      controller = {
        service = {
          loadBalancerIP = module.foundation.global_ip_address
          annotations = {
            "cloud.google.com/load-balancer-type" = "External"
          }
        }
        config = {
          use-proxy-protocol = "true"
        }
        metrics = {
          enabled = true
          serviceMonitor = {
            enabled = true
          }
        }
      }
    })
  ]

  depends_on = [module.gke]
}

# Install Prometheus monitoring stack
resource "helm_release" "kube_prometheus_stack" {
  name       = "kube-prometheus-stack"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  version    = var.prometheus_stack_version
  namespace  = "monitoring"

  create_namespace = true

  values = [
    yamlencode({
      prometheus = {
        prometheusSpec = {
          retention = "30d"
          storageSpec = {
            volumeClaimTemplate = {
              spec = {
                storageClassName = "ssd"
                accessModes      = ["ReadWriteOnce"]
                resources = {
                  requests = {
                    storage = "50Gi"
                  }
                }
              }
            }
          }
        }
      }
      grafana = {
        adminPassword = var.grafana_admin_password
        persistence = {
          enabled = true
          size    = "10Gi"
        }
        ingress = {
          enabled = true
          hosts   = ["grafana.${var.domain_name}"]
          tls = [{
            secretName = "grafana-tls"
            hosts      = ["grafana.${var.domain_name}"]
          }]
        }
      }
      alertmanager = {
        alertmanagerSpec = {
          storage = {
            volumeClaimTemplate = {
              spec = {
                storageClassName = "ssd"
                accessModes      = ["ReadWriteOnce"]
                resources = {
                  requests = {
                    storage = "10Gi"
                  }
                }
              }
            }
          }
        }
      }
    })
  ]

  depends_on = [module.gke, helm_release.ingress_nginx]
}

# Install Jaeger for distributed tracing
resource "helm_release" "jaeger" {
  name       = "jaeger"
  repository = "https://jaegertracing.github.io/helm-charts"
  chart      = "jaeger"
  version    = var.jaeger_version
  namespace  = "tracing"

  create_namespace = true

  values = [
    yamlencode({
      provisionDataStore = {
        cassandra = false
        elasticsearch = true
      }
      elasticsearch = {
        replicas = 3
        minimumMasterNodes = 2
      }
      agent = {
        daemonset = {
          useHostPort = true
        }
      }
      collector = {
        service = {
          type = "ClusterIP"
        }
      }
      query = {
        ingress = {
          enabled = true
          hosts   = ["jaeger.${var.domain_name}"]
          tls = [{
            secretName = "jaeger-tls"
            hosts      = ["jaeger.${var.domain_name}"]
          }]
        }
      }
    })
  ]

  depends_on = [module.gke, helm_release.ingress_nginx]
}

# Install ArgoCD for GitOps
resource "helm_release" "argocd" {
  name       = "argocd"
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argo-cd"
  version    = var.argocd_version
  namespace  = "argocd"

  create_namespace = true

  values = [
    yamlencode({
      server = {
        ingress = {
          enabled = true
          hosts   = ["argocd.${var.domain_name}"]
          tls = [{
            secretName = "argocd-server-tls"
            hosts      = ["argocd.${var.domain_name}"]
          }]
        }
        config = {
          "application.instanceLabelKey" = "argocd.argoproj.io/instance"
        }
      }
      configs = {
        secret = {
          argocdServerAdminPassword = var.argocd_admin_password
        }
      }
    })
  ]

  depends_on = [module.gke, helm_release.ingress_nginx]
}

# Create ClusterIssuer for Let's Encrypt certificates
resource "kubernetes_manifest" "cluster_issuer" {
  manifest = {
    apiVersion = "cert-manager.io/v1"
    kind       = "ClusterIssuer"
    metadata = {
      name = "letsencrypt-prod"
    }
    spec = {
      acme = {
        server = "https://acme-v02.api.letsencrypt.org/directory"
        email  = var.letsencrypt_email
        privateKeySecretRef = {
          name = "letsencrypt-prod"
        }
        solvers = [{
          http01 = {
            ingress = {
              class = "nginx"
            }
          }
        }]
      }
    }
  }

  depends_on = [helm_release.cert_manager]
}

# Create storage classes
resource "kubernetes_storage_class" "ssd" {
  metadata {
    name = "ssd"
    labels = local.common_labels
  }

  storage_provisioner    = "kubernetes.io/gce-pd"
  reclaim_policy        = "Retain"
  allow_volume_expansion = true
  volume_binding_mode   = "WaitForFirstConsumer"

  parameters = {
    type             = "pd-ssd"
    replication-type = "regional-pd"
    zones            = join(",", var.zones)
  }

  depends_on = [module.gke]
}

resource "kubernetes_storage_class" "standard" {
  metadata {
    name = "standard"
    labels = local.common_labels
  }

  storage_provisioner    = "kubernetes.io/gce-pd"
  reclaim_policy        = "Delete"
  allow_volume_expansion = true
  volume_binding_mode   = "WaitForFirstConsumer"

  parameters = {
    type             = "pd-standard"
    replication-type = "regional-pd"
    zones            = join(",", var.zones)
  }

  depends_on = [module.gke]
}

# Network policies for security
resource "kubernetes_network_policy" "deny_all" {
  metadata {
    name      = "deny-all"
    namespace = kubernetes_namespace.atp_system.metadata[0].name
    labels    = local.common_labels
  }

  spec {
    pod_selector {}
    policy_types = ["Ingress", "Egress"]
  }

  depends_on = [kubernetes_namespace.atp_system]
}

resource "kubernetes_network_policy" "allow_atp_internal" {
  metadata {
    name      = "allow-atp-internal"
    namespace = kubernetes_namespace.atp_system.metadata[0].name
    labels    = local.common_labels
  }

  spec {
    pod_selector {
      match_labels = {
        app = "atp"
      }
    }

    policy_types = ["Ingress", "Egress"]

    ingress {
      from {
        pod_selector {
          match_labels = {
            app = "atp"
          }
        }
      }
    }

    egress {
      to {
        pod_selector {
          match_labels = {
            app = "atp"
          }
        }
      }
    }

    # Allow DNS
    egress {
      to {
        namespace_selector {
          match_labels = {
            name = "kube-system"
          }
        }
      }
      ports {
        protocol = "UDP"
        port     = "53"
      }
    }
  }

  depends_on = [kubernetes_namespace.atp_system]
}