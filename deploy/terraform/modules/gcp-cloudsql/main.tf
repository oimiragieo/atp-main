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

# Cloud SQL Module for ATP Platform
# Provides highly available PostgreSQL database with security and monitoring

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
    random = {
      source  = "hashicorp/random"
      version = "~> 3.1"
    }
  }
}

# Local variables
locals {
  instance_name = "${var.project_name}-db-${var.environment}"
  
  common_labels = {
    project     = var.project_name
    environment = var.environment
    component   = "database"
    managed_by  = "terraform"
  }
}

# Random password for database users
resource "random_password" "db_password" {
  length  = 32
  special = true
}

resource "random_password" "replication_password" {
  count   = var.enable_read_replicas ? 1 : 0
  length  = 32
  special = true
}

# Cloud SQL instance
resource "google_sql_database_instance" "atp_db" {
  name             = local.instance_name
  database_version = var.database_version
  region           = var.region
  project          = var.project_id

  # Deletion protection
  deletion_protection = var.enable_deletion_protection

  settings {
    tier                        = var.machine_type
    availability_type           = var.high_availability ? "REGIONAL" : "ZONAL"
    disk_type                   = var.disk_type
    disk_size                   = var.disk_size
    disk_autoresize             = var.enable_disk_autoresize
    disk_autoresize_limit       = var.disk_autoresize_limit
    edition                     = var.database_edition
    user_labels                 = local.common_labels

    # Backup configuration
    backup_configuration {
      enabled                        = var.enable_backups
      start_time                     = var.backup_start_time
      location                       = var.backup_location
      point_in_time_recovery_enabled = var.enable_point_in_time_recovery
      transaction_log_retention_days = var.transaction_log_retention_days
      backup_retention_settings {
        retained_backups = var.backup_retention_count
        retention_unit   = "COUNT"
      }
    }

    # IP configuration
    ip_configuration {
      ipv4_enabled                                  = var.enable_public_ip
      private_network                               = var.vpc_id
      enable_private_path_for_google_cloud_services = true
      allocated_ip_range                            = var.private_ip_range_name

      dynamic "authorized_networks" {
        for_each = var.authorized_networks
        content {
          name  = authorized_networks.value.name
          value = authorized_networks.value.value
        }
      }

      require_ssl = var.require_ssl
    }

    # Maintenance window
    maintenance_window {
      day          = var.maintenance_window_day
      hour         = var.maintenance_window_hour
      update_track = var.maintenance_update_track
    }

    # Database flags
    dynamic "database_flags" {
      for_each = var.database_flags
      content {
        name  = database_flags.value.name
        value = database_flags.value.value
      }
    }

    # Insights configuration
    insights_config {
      query_insights_enabled  = var.enable_query_insights
      query_plans_per_minute  = var.query_plans_per_minute
      query_string_length     = var.query_string_length
      record_application_tags = var.record_application_tags
      record_client_address   = var.record_client_address
    }

    # Password validation
    password_validation_policy {
      min_length                  = var.password_min_length
      complexity                  = var.password_complexity
      reuse_interval             = var.password_reuse_interval
      disallow_username_substring = var.disallow_username_substring
      enable_password_policy      = var.enable_password_policy
    }

    # Data cache configuration
    data_cache_config {
      data_cache_enabled = var.enable_data_cache
    }

    # Advanced machine configuration
    advanced_machine_features {
      threads_per_core = var.threads_per_core
    }

    # Active Directory configuration
    dynamic "active_directory_config" {
      for_each = var.active_directory_domain != null ? [1] : []
      content {
        domain = var.active_directory_domain
      }
    }

    # Connector enforcement
    connector_enforcement = var.connector_enforcement

    # SQL Server audit configuration
    dynamic "sql_server_audit_config" {
      for_each = var.database_version == "SQLSERVER_2019_STANDARD" ? [1] : []
      content {
        bucket                      = var.audit_bucket_name
        retention_interval          = var.audit_retention_interval
        upload_interval             = var.audit_upload_interval
      }
    }
  }

  # Encryption
  encryption_key_name = var.kms_key_name

  depends_on = [
    var.private_vpc_connection_id
  ]

  lifecycle {
    prevent_destroy = true
  }
}

# Read replicas
resource "google_sql_database_instance" "read_replica" {
  count = var.enable_read_replicas ? var.read_replica_count : 0

  name                 = "${local.instance_name}-replica-${count.index + 1}"
  database_version     = var.database_version
  region               = var.read_replica_regions[count.index % length(var.read_replica_regions)]
  project              = var.project_id
  master_instance_name = google_sql_database_instance.atp_db.name

  # Deletion protection
  deletion_protection = var.enable_deletion_protection

  replica_configuration {
    failover_target = false
  }

  settings {
    tier                        = var.read_replica_machine_type
    availability_type           = "ZONAL"
    disk_type                   = var.disk_type
    disk_size                   = var.read_replica_disk_size
    disk_autoresize             = var.enable_disk_autoresize
    disk_autoresize_limit       = var.disk_autoresize_limit
    user_labels                 = merge(local.common_labels, { replica = "true" })

    # IP configuration
    ip_configuration {
      ipv4_enabled                                  = var.enable_public_ip
      private_network                               = var.vpc_id
      enable_private_path_for_google_cloud_services = true
      allocated_ip_range                            = var.private_ip_range_name
      require_ssl                                   = var.require_ssl
    }

    # Database flags
    dynamic "database_flags" {
      for_each = var.database_flags
      content {
        name  = database_flags.value.name
        value = database_flags.value.value
      }
    }

    # Insights configuration
    insights_config {
      query_insights_enabled  = var.enable_query_insights
      query_plans_per_minute  = var.query_plans_per_minute
      query_string_length     = var.query_string_length
      record_application_tags = var.record_application_tags
      record_client_address   = var.record_client_address
    }

    # Data cache configuration
    data_cache_config {
      data_cache_enabled = var.enable_data_cache
    }
  }

  # Encryption
  encryption_key_name = var.kms_key_name

  depends_on = [
    google_sql_database_instance.atp_db
  ]
}

# Database
resource "google_sql_database" "atp_database" {
  name     = var.database_name
  instance = google_sql_database_instance.atp_db.name
  project  = var.project_id

  # Character set and collation for SQL Server
  charset   = var.database_charset
  collation = var.database_collation

  # Deletion policy
  deletion_policy = var.database_deletion_policy
}

# Additional databases
resource "google_sql_database" "additional_databases" {
  for_each = toset(var.additional_databases)

  name     = each.value
  instance = google_sql_database_instance.atp_db.name
  project  = var.project_id

  charset   = var.database_charset
  collation = var.database_collation

  deletion_policy = var.database_deletion_policy
}

# Database users
resource "google_sql_user" "app_user" {
  name     = var.app_user_name
  instance = google_sql_database_instance.atp_db.name
  project  = var.project_id
  password = random_password.db_password.result

  # PostgreSQL specific settings
  dynamic "password_policy" {
    for_each = var.database_version == "POSTGRES_15" ? [1] : []
    content {
      allowed_failed_attempts      = var.user_allowed_failed_attempts
      password_expiration_duration = var.user_password_expiration_duration
      enable_failed_attempts_check = var.enable_failed_attempts_check
      enable_password_verification = var.enable_password_verification
    }
  }
}

resource "google_sql_user" "readonly_user" {
  count = var.create_readonly_user ? 1 : 0

  name     = var.readonly_user_name
  instance = google_sql_database_instance.atp_db.name
  project  = var.project_id
  password = random_password.db_password.result

  dynamic "password_policy" {
    for_each = var.database_version == "POSTGRES_15" ? [1] : []
    content {
      allowed_failed_attempts      = var.user_allowed_failed_attempts
      password_expiration_duration = var.user_password_expiration_duration
      enable_failed_attempts_check = var.enable_failed_attempts_check
      enable_password_verification = var.enable_password_verification
    }
  }
}

# Additional users
resource "google_sql_user" "additional_users" {
  for_each = var.additional_users

  name     = each.key
  instance = google_sql_database_instance.atp_db.name
  project  = var.project_id
  password = each.value.password != null ? each.value.password : random_password.db_password.result

  dynamic "password_policy" {
    for_each = var.database_version == "POSTGRES_15" ? [1] : []
    content {
      allowed_failed_attempts      = var.user_allowed_failed_attempts
      password_expiration_duration = var.user_password_expiration_duration
      enable_failed_attempts_check = var.enable_failed_attempts_check
      enable_password_verification = var.enable_password_verification
    }
  }
}

# SSL certificates
resource "google_sql_ssl_cert" "client_cert" {
  count = var.create_ssl_cert ? 1 : 0

  common_name = "${var.project_name}-client-cert-${var.environment}"
  instance    = google_sql_database_instance.atp_db.name
  project     = var.project_id
}

# Store database credentials in Secret Manager
resource "google_secret_manager_secret" "db_credentials" {
  secret_id = "${var.project_name}-db-credentials-${var.environment}"
  project   = var.project_id

  labels = local.common_labels

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "db_credentials" {
  secret = google_secret_manager_secret.db_credentials.id

  secret_data = jsonencode({
    host     = google_sql_database_instance.atp_db.private_ip_address
    port     = 5432
    database = google_sql_database.atp_database.name
    username = google_sql_user.app_user.name
    password = random_password.db_password.result
    ssl_mode = var.require_ssl ? "require" : "prefer"
  })
}

# Store readonly credentials if created
resource "google_secret_manager_secret" "readonly_credentials" {
  count = var.create_readonly_user ? 1 : 0

  secret_id = "${var.project_name}-db-readonly-credentials-${var.environment}"
  project   = var.project_id

  labels = local.common_labels

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "readonly_credentials" {
  count = var.create_readonly_user ? 1 : 0

  secret = google_secret_manager_secret.readonly_credentials[0].id

  secret_data = jsonencode({
    host     = google_sql_database_instance.atp_db.private_ip_address
    port     = 5432
    database = google_sql_database.atp_database.name
    username = google_sql_user.readonly_user[0].name
    password = random_password.db_password.result
    ssl_mode = var.require_ssl ? "require" : "prefer"
  })
}

# Database monitoring
resource "google_monitoring_alert_policy" "database_cpu" {
  display_name = "Database High CPU - ${var.environment}"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Database CPU usage above 80%"

    condition_threshold {
      filter          = "resource.type=\"cloudsql_database\" AND resource.labels.database_id=\"${var.project_id}:${google_sql_database_instance.atp_db.name}\""
      duration        = "300s"
      comparison      = "COMPARISON_GREATER_THAN"
      threshold_value = 0.8

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = var.notification_channel_ids

  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_alert_policy" "database_memory" {
  display_name = "Database High Memory - ${var.environment}"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Database memory usage above 90%"

    condition_threshold {
      filter          = "resource.type=\"cloudsql_database\" AND resource.labels.database_id=\"${var.project_id}:${google_sql_database_instance.atp_db.name}\""
      duration        = "300s"
      comparison      = "COMPARISON_GREATER_THAN"
      threshold_value = 0.9

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = var.notification_channel_ids

  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_alert_policy" "database_connections" {
  display_name = "Database High Connections - ${var.environment}"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Database connection count above threshold"

    condition_threshold {
      filter          = "resource.type=\"cloudsql_database\" AND resource.labels.database_id=\"${var.project_id}:${google_sql_database_instance.atp_db.name}\""
      duration        = "300s"
      comparison      = "COMPARISON_GREATER_THAN"
      threshold_value = var.max_connections * 0.8

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = var.notification_channel_ids

  alert_strategy {
    auto_close = "1800s"
  }
}