# GCP Infrastructure for ATP Enterprise AI Platform

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 4.0"
    }
  }
}

# Variables
variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP Zone"
  type        = string
  default     = "us-central1-a"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "prod"
}

# Provider configuration
provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# Enable required APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "run.googleapis.com",
    "sql.googleapis.com",
    "redis.googleapis.com",
    "secretmanager.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "container.googleapis.com",
    "compute.googleapis.com",
    "vpcaccess.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com"
  ])

  project = var.project_id
  service = each.value

  disable_dependent_services = true
}

# VPC Network
resource "google_compute_network" "atp_network" {
  name                    = "atp-network-${var.environment}"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.required_apis]
}

resource "google_compute_subnetwork" "atp_subnet" {
  name          = "atp-subnet-${var.environment}"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.atp_network.id

  private_ip_google_access = true
}

# VPC Access Connector for Cloud Run
resource "google_vpc_access_connector" "atp_connector" {
  name          = "atp-connector-${var.environment}"
  region        = var.region
  network       = google_compute_network.atp_network.name
  ip_cidr_range = "10.1.0.0/28"
  
  depends_on = [google_project_service.required_apis]
}

# Cloud SQL Instance
resource "google_sql_database_instance" "atp_postgres" {
  name             = "atp-postgres-${var.environment}"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier                        = "db-custom-2-4096"
    availability_type           = "REGIONAL"
    disk_type                   = "PD_SSD"
    disk_size                   = 100
    disk_autoresize             = true
    disk_autoresize_limit       = 500

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
      backup_retention_settings {
        retained_backups = 30
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.atp_network.id
      require_ssl     = true
    }

    database_flags {
      name  = "log_statement"
      value = "all"
    }

    database_flags {
      name  = "log_min_duration_statement"
      value = "1000"
    }
  }

  deletion_protection = true
  depends_on         = [google_project_service.required_apis]
}

resource "google_sql_database" "atp_database" {
  name     = "atp"
  instance = google_sql_database_instance.atp_postgres.name
}

resource "google_sql_user" "atp_user" {
  name     = "atp"
  instance = google_sql_database_instance.atp_postgres.name
  password = random_password.db_password.result
}

resource "random_password" "db_password" {
  length  = 32
  special = true
}

# Memorystore Redis
resource "google_redis_instance" "atp_redis" {
  name           = "atp-redis-${var.environment}"
  tier           = "STANDARD_HA"
  memory_size_gb = 4
  region         = var.region

  authorized_network = google_compute_network.atp_network.id
  redis_version      = "REDIS_7_0"

  display_name = "ATP Redis Cache"
  
  depends_on = [google_project_service.required_apis]
}

# Service Accounts
resource "google_service_account" "atp_cloud_run" {
  account_id   = "atp-cloud-run"
  display_name = "ATP Cloud Run Service Account"
  description  = "Service account for ATP Cloud Run services"
}

resource "google_project_iam_member" "atp_cloud_run_roles" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/redis.editor",
    "roles/secretmanager.secretAccessor",
    "roles/monitoring.metricWriter",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent"
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.atp_cloud_run.email}"
}

# Secrets
resource "google_secret_manager_secret" "database_url" {
  secret_id = "database-url"
  
  replication {
    automatic = true
  }
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = "postgresql://${google_sql_user.atp_user.name}:${random_password.db_password.result}@${google_sql_database_instance.atp_postgres.private_ip_address}:5432/${google_sql_database.atp_database.name}"
}

resource "google_secret_manager_secret" "redis_url" {
  secret_id = "redis-url"
  
  replication {
    automatic = true
  }
}

resource "google_secret_manager_secret_version" "redis_url" {
  secret      = google_secret_manager_secret.redis_url.id
  secret_data = "redis://${google_redis_instance.atp_redis.host}:${google_redis_instance.atp_redis.port}"
}

# Load Balancer
resource "google_compute_global_address" "atp_ip" {
  name = "atp-ip-${var.environment}"
}

resource "google_compute_managed_ssl_certificate" "atp_ssl" {
  name = "atp-ssl-${var.environment}"

  managed {
    domains = ["atp.yourdomain.com"]
  }
}

# Cloud Armor Security Policy
resource "google_compute_security_policy" "atp_security_policy" {
  name        = "atp-security-policy-${var.environment}"
  description = "Security policy for ATP services"

  rule {
    action   = "allow"
    priority = "1000"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Allow all traffic"
  }

  rule {
    action   = "deny(403)"
    priority = "2147483647"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default deny rule"
  }

  # Rate limiting rule
  rule {
    action   = "rate_based_ban"
    priority = "100"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 1000
        interval_sec = 60
      }
      ban_duration_sec = 300
    }
    description = "Rate limit rule"
  }
}

# Outputs
output "database_connection_name" {
  value = google_sql_database_instance.atp_postgres.connection_name
}

output "redis_host" {
  value = google_redis_instance.atp_redis.host
}

output "vpc_connector_name" {
  value = google_vpc_access_connector.atp_connector.name
}

output "service_account_email" {
  value = google_service_account.atp_cloud_run.email
}

output "load_balancer_ip" {
  value = google_compute_global_address.atp_ip.address
}