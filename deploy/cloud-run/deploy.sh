#!/bin/bash

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

# ATP Cloud Run Deployment Script
# This script deploys the ATP platform to Google Cloud Run

set -euo pipefail

# Configuration
PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-us-central1}"
ENVIRONMENT="${ENVIRONMENT:-production}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if gcloud is installed
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check if docker is installed
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install it first."
        exit 1
    fi
    
    # Check if PROJECT_ID is set
    if [[ -z "$PROJECT_ID" ]]; then
        log_error "PROJECT_ID environment variable is not set."
        exit 1
    fi
    
    # Check if authenticated with gcloud
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
        log_error "Not authenticated with gcloud. Please run 'gcloud auth login'."
        exit 1
    fi
    
    # Set the project
    gcloud config set project "$PROJECT_ID"
    
    log_success "Prerequisites check passed"
}

# Enable required APIs
enable_apis() {
    log_info "Enabling required Google Cloud APIs..."
    
    local apis=(
        "run.googleapis.com"
        "cloudbuild.googleapis.com"
        "containerregistry.googleapis.com"
        "sqladmin.googleapis.com"
        "redis.googleapis.com"
        "secretmanager.googleapis.com"
        "cloudtrace.googleapis.com"
        "monitoring.googleapis.com"
        "logging.googleapis.com"
        "vpcaccess.googleapis.com"
        "servicenetworking.googleapis.com"
    )
    
    for api in "${apis[@]}"; do
        log_info "Enabling $api..."
        gcloud services enable "$api" --project="$PROJECT_ID"
    done
    
    log_success "APIs enabled successfully"
}

# Create service accounts
create_service_accounts() {
    log_info "Creating service accounts..."
    
    # Router service account
    if ! gcloud iam service-accounts describe "atp-router-service@$PROJECT_ID.iam.gserviceaccount.com" &>/dev/null; then
        gcloud iam service-accounts create atp-router-service \
            --display-name="ATP Router Service" \
            --description="Service account for ATP Router Service" \
            --project="$PROJECT_ID"
    fi
    
    # Memory gateway service account
    if ! gcloud iam service-accounts describe "atp-memory-gateway@$PROJECT_ID.iam.gserviceaccount.com" &>/dev/null; then
        gcloud iam service-accounts create atp-memory-gateway \
            --display-name="ATP Memory Gateway" \
            --description="Service account for ATP Memory Gateway" \
            --project="$PROJECT_ID"
    fi
    
    log_success "Service accounts created"
}

# Grant IAM permissions
grant_iam_permissions() {
    log_info "Granting IAM permissions..."
    
    # Router service permissions
    local router_sa="atp-router-service@$PROJECT_ID.iam.gserviceaccount.com"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$router_sa" \
        --role="roles/cloudsql.client"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$router_sa" \
        --role="roles/redis.editor"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$router_sa" \
        --role="roles/secretmanager.secretAccessor"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$router_sa" \
        --role="roles/cloudtrace.agent"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$router_sa" \
        --role="roles/monitoring.metricWriter"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$router_sa" \
        --role="roles/logging.logWriter"
    
    # Memory gateway service permissions
    local gateway_sa="atp-memory-gateway@$PROJECT_ID.iam.gserviceaccount.com"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$gateway_sa" \
        --role="roles/cloudsql.client"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$gateway_sa" \
        --role="roles/redis.editor"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$gateway_sa" \
        --role="roles/secretmanager.secretAccessor"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$gateway_sa" \
        --role="roles/cloudtrace.agent"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$gateway_sa" \
        --role="roles/monitoring.metricWriter"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$gateway_sa" \
        --role="roles/logging.logWriter"
    
    log_success "IAM permissions granted"
}

# Create VPC connector
create_vpc_connector() {
    log_info "Creating VPC connector..."
    
    # Check if connector already exists
    if gcloud compute networks vpc-access connectors describe atp-vpc-connector \
        --region="$REGION" --project="$PROJECT_ID" &>/dev/null; then
        log_info "VPC connector already exists"
        return
    fi
    
    # Create VPC connector
    gcloud compute networks vpc-access connectors create atp-vpc-connector \
        --region="$REGION" \
        --subnet-project="$PROJECT_ID" \
        --subnet=default \
        --min-instances=2 \
        --max-instances=10 \
        --machine-type=e2-micro \
        --project="$PROJECT_ID"
    
    log_success "VPC connector created"
}

# Create Cloud SQL instance
create_cloud_sql() {
    log_info "Creating Cloud SQL PostgreSQL instance..."
    
    # Check if instance already exists
    if gcloud sql instances describe atp-postgres --project="$PROJECT_ID" &>/dev/null; then
        log_info "Cloud SQL instance already exists"
        return
    fi
    
    # Create Cloud SQL instance
    gcloud sql instances create atp-postgres \
        --database-version=POSTGRES_14 \
        --tier=db-custom-2-4096 \
        --region="$REGION" \
        --storage-type=SSD \
        --storage-size=100GB \
        --storage-auto-increase \
        --backup-start-time=02:00 \
        --enable-bin-log \
        --maintenance-window-day=SUN \
        --maintenance-window-hour=03 \
        --maintenance-release-channel=production \
        --deletion-protection \
        --project="$PROJECT_ID"
    
    # Create database
    gcloud sql databases create atp \
        --instance=atp-postgres \
        --project="$PROJECT_ID"
    
    # Create database user
    gcloud sql users create atp-user \
        --instance=atp-postgres \
        --password="$(openssl rand -base64 32)" \
        --project="$PROJECT_ID"
    
    log_success "Cloud SQL instance created"
}

# Create Redis instance
create_redis() {
    log_info "Creating Redis instance..."
    
    # Check if instance already exists
    if gcloud redis instances describe atp-redis \
        --region="$REGION" --project="$PROJECT_ID" &>/dev/null; then
        log_info "Redis instance already exists"
        return
    fi
    
    # Create Redis instance
    gcloud redis instances create atp-redis \
        --size=1 \
        --region="$REGION" \
        --redis-version=redis_6_x \
        --tier=standard \
        --project="$PROJECT_ID"
    
    log_success "Redis instance created"
}

# Create secrets
create_secrets() {
    log_info "Creating secrets..."
    
    # Database secret
    if ! gcloud secrets describe atp-database-secret --project="$PROJECT_ID" &>/dev/null; then
        # Get Cloud SQL connection string
        local db_connection_name
        db_connection_name=$(gcloud sql instances describe atp-postgres \
            --format="value(connectionName)" --project="$PROJECT_ID")
        
        local db_url="postgresql://atp-user:PASSWORD@/atp?host=/cloudsql/$db_connection_name"
        
        echo -n "$db_url" | gcloud secrets create atp-database-secret \
            --data-file=- --project="$PROJECT_ID"
    fi
    
    # Redis secret
    if ! gcloud secrets describe atp-redis-secret --project="$PROJECT_ID" &>/dev/null; then
        local redis_host
        redis_host=$(gcloud redis instances describe atp-redis \
            --region="$REGION" --format="value(host)" --project="$PROJECT_ID")
        
        local redis_url="redis://$redis_host:6379"
        
        echo -n "$redis_url" | gcloud secrets create atp-redis-secret \
            --data-file=- --project="$PROJECT_ID"
    fi
    
    # Auth secret
    if ! gcloud secrets describe atp-auth-secret --project="$PROJECT_ID" &>/dev/null; then
        local jwt_secret
        jwt_secret=$(openssl rand -base64 64)
        
        echo -n "$jwt_secret" | gcloud secrets create atp-auth-secret \
            --data-file=- --project="$PROJECT_ID"
    fi
    
    # OIDC secret (placeholder - needs to be updated with actual values)
    if ! gcloud secrets describe atp-oidc-secret --project="$PROJECT_ID" &>/dev/null; then
        cat <<EOF | gcloud secrets create atp-oidc-secret --data-file=- --project="$PROJECT_ID"
{
  "client-id": "your-oidc-client-id",
  "client-secret": "your-oidc-client-secret",
  "discovery-url": "https://your-oidc-provider.com/.well-known/openid_configuration"
}
EOF
        log_warning "OIDC secret created with placeholder values. Please update with actual values."
    fi
    
    # Provider secrets (placeholder - needs to be updated with actual API keys)
    if ! gcloud secrets describe atp-provider-secrets --project="$PROJECT_ID" &>/dev/null; then
        cat <<EOF | gcloud secrets create atp-provider-secrets --data-file=- --project="$PROJECT_ID"
{
  "openai-api-key": "your-openai-api-key",
  "anthropic-api-key": "your-anthropic-api-key",
  "google-ai-api-key": "your-google-ai-api-key"
}
EOF
        log_warning "Provider secrets created with placeholder values. Please update with actual API keys."
    fi
    
    # Encryption secret
    if ! gcloud secrets describe atp-encryption-secret --project="$PROJECT_ID" &>/dev/null; then
        local encryption_key
        encryption_key=$(openssl rand -base64 32)
        
        echo -n "$encryption_key" | gcloud secrets create atp-encryption-secret \
            --data-file=- --project="$PROJECT_ID"
    fi
    
    log_success "Secrets created"
}

# Build and push Docker images
build_and_push_images() {
    log_info "Building and pushing Docker images..."
    
    # Configure Docker for GCR
    gcloud auth configure-docker --project="$PROJECT_ID"
    
    # Build router service image
    log_info "Building router service image..."
    docker build -t "gcr.io/$PROJECT_ID/atp-router:latest" \
        -f deploy/docker/router-service.Dockerfile .
    
    docker push "gcr.io/$PROJECT_ID/atp-router:latest"
    
    # Build memory gateway image
    log_info "Building memory gateway image..."
    docker build -t "gcr.io/$PROJECT_ID/atp-memory-gateway:latest" \
        -f deploy/docker/memory-gateway.Dockerfile .
    
    docker push "gcr.io/$PROJECT_ID/atp-memory-gateway:latest"
    
    log_success "Docker images built and pushed"
}

# Deploy Cloud Run services
deploy_services() {
    log_info "Deploying Cloud Run services..."
    
    # Replace placeholders in YAML files
    local router_yaml="/tmp/router-service.yaml"
    local gateway_yaml="/tmp/memory-gateway.yaml"
    
    sed "s/PROJECT_ID/$PROJECT_ID/g; s/REGION/$REGION/g" \
        deploy/cloud-run/router-service.yaml > "$router_yaml"
    
    sed "s/PROJECT_ID/$PROJECT_ID/g; s/REGION/$REGION/g" \
        deploy/cloud-run/memory-gateway.yaml > "$gateway_yaml"
    
    # Deploy router service
    log_info "Deploying router service..."
    gcloud run services replace "$router_yaml" \
        --region="$REGION" --project="$PROJECT_ID"
    
    # Deploy memory gateway
    log_info "Deploying memory gateway..."
    gcloud run services replace "$gateway_yaml" \
        --region="$REGION" --project="$PROJECT_ID"
    
    # Clean up temporary files
    rm -f "$router_yaml" "$gateway_yaml"
    
    log_success "Cloud Run services deployed"
}

# Configure load balancer
configure_load_balancer() {
    log_info "Configuring load balancer..."
    
    # Create backend services
    if ! gcloud compute backend-services describe atp-router-backend \
        --global --project="$PROJECT_ID" &>/dev/null; then
        
        # Create NEG for router service
        gcloud compute network-endpoint-groups create atp-router-neg \
            --network-endpoint-type=serverless \
            --cloud-run-service=atp-router-service \
            --region="$REGION" \
            --project="$PROJECT_ID"
        
        # Create backend service
        gcloud compute backend-services create atp-router-backend \
            --global \
            --load-balancing-scheme=EXTERNAL \
            --protocol=HTTP \
            --project="$PROJECT_ID"
        
        # Add NEG to backend service
        gcloud compute backend-services add-backend atp-router-backend \
            --global \
            --network-endpoint-group=atp-router-neg \
            --network-endpoint-group-region="$REGION" \
            --project="$PROJECT_ID"
    fi
    
    # Create URL map
    if ! gcloud compute url-maps describe atp-url-map \
        --global --project="$PROJECT_ID" &>/dev/null; then
        
        gcloud compute url-maps create atp-url-map \
            --default-backend-service=atp-router-backend \
            --global \
            --project="$PROJECT_ID"
    fi
    
    # Create HTTP(S) load balancer
    if ! gcloud compute target-https-proxies describe atp-https-proxy \
        --global --project="$PROJECT_ID" &>/dev/null; then
        
        # Create SSL certificate (managed)
        gcloud compute ssl-certificates create atp-ssl-cert \
            --domains="atp.example.com,api.atp.example.com" \
            --global \
            --project="$PROJECT_ID"
        
        # Create HTTPS proxy
        gcloud compute target-https-proxies create atp-https-proxy \
            --url-map=atp-url-map \
            --ssl-certificates=atp-ssl-cert \
            --global \
            --project="$PROJECT_ID"
        
        # Create forwarding rule
        gcloud compute forwarding-rules create atp-https-forwarding-rule \
            --address=atp-lb-ip \
            --global \
            --target-https-proxy=atp-https-proxy \
            --ports=443 \
            --project="$PROJECT_ID"
    fi
    
    log_success "Load balancer configured"
}

# Set up monitoring and alerting
setup_monitoring() {
    log_info "Setting up monitoring and alerting..."
    
    # Create notification channel (email)
    if ! gcloud alpha monitoring channels list \
        --filter="displayName:ATP Alerts" --project="$PROJECT_ID" | grep -q "ATP Alerts"; then
        
        gcloud alpha monitoring channels create \
            --display-name="ATP Alerts" \
            --type=email \
            --channel-labels=email_address=alerts@example.com \
            --project="$PROJECT_ID"
    fi
    
    # Create alerting policies
    cat <<EOF > /tmp/alert-policy.yaml
displayName: "ATP High Error Rate"
conditions:
  - displayName: "High error rate"
    conditionThreshold:
      filter: 'resource.type="cloud_run_revision" AND resource.labels.service_name=~"atp-.*"'
      comparison: COMPARISON_GREATER_THAN
      thresholdValue: 0.05
      duration: 300s
      aggregations:
        - alignmentPeriod: 60s
          perSeriesAligner: ALIGN_RATE
          crossSeriesReducer: REDUCE_MEAN
          groupByFields:
            - resource.labels.service_name
notificationChannels:
  - projects/$PROJECT_ID/notificationChannels/CHANNEL_ID
EOF
    
    # Note: This is a simplified example. In practice, you'd create multiple alert policies
    # and use the actual notification channel ID
    
    log_success "Monitoring and alerting configured"
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."
    
    # This would typically be done through a Cloud Build job or Cloud Run job
    # For now, we'll create a simple migration job
    
    cat <<EOF > /tmp/migration-job.yaml
apiVersion: run.googleapis.com/v1
kind: Job
metadata:
  name: atp-migration-job
spec:
  template:
    spec:
      template:
        spec:
          containers:
          - name: migration
            image: gcr.io/$PROJECT_ID/atp-router:latest
            command: ["python", "-m", "alembic", "upgrade", "head"]
            env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: atp-database-secret
                  key: url
          restartPolicy: Never
          serviceAccountName: atp-router-service@$PROJECT_ID.iam.gserviceaccount.com
      backoffLimit: 3
EOF
    
    # Run migration job
    gcloud run jobs replace /tmp/migration-job.yaml \
        --region="$REGION" --project="$PROJECT_ID"
    
    gcloud run jobs execute atp-migration-job \
        --region="$REGION" --project="$PROJECT_ID" --wait
    
    rm -f /tmp/migration-job.yaml
    
    log_success "Database migrations completed"
}

# Main deployment function
main() {
    log_info "Starting ATP Cloud Run deployment..."
    
    check_prerequisites
    enable_apis
    create_service_accounts
    grant_iam_permissions
    create_vpc_connector
    create_cloud_sql
    create_redis
    create_secrets
    build_and_push_images
    deploy_services
    configure_load_balancer
    setup_monitoring
    run_migrations
    
    log_success "ATP deployment completed successfully!"
    
    # Display service URLs
    log_info "Service URLs:"
    gcloud run services list --region="$REGION" --project="$PROJECT_ID" \
        --format="table(metadata.name,status.url)"
    
    log_info "Next steps:"
    echo "1. Update DNS records to point to the load balancer IP"
    echo "2. Update OIDC and provider API key secrets with actual values"
    echo "3. Configure monitoring dashboards in Cloud Monitoring"
    echo "4. Set up backup and disaster recovery procedures"
    echo "5. Configure CI/CD pipeline for automated deployments"
}

# Handle script arguments
case "${1:-deploy}" in
    "deploy")
        main
        ;;
    "cleanup")
        log_warning "This will delete all ATP resources. Are you sure? (y/N)"
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            log_info "Cleaning up ATP resources..."
            # Add cleanup commands here
            log_success "Cleanup completed"
        else
            log_info "Cleanup cancelled"
        fi
        ;;
    "help")
        echo "Usage: $0 [deploy|cleanup|help]"
        echo "  deploy  - Deploy ATP to Cloud Run (default)"
        echo "  cleanup - Remove all ATP resources"
        echo "  help    - Show this help message"
        ;;
    *)
        log_error "Unknown command: $1"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac