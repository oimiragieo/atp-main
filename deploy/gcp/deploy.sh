#!/bin/bash
# GCP Deployment Script for ATP Enterprise AI Platform

set -e

# Configuration
PROJECT_ID=${PROJECT_ID:-"your-project-id"}
REGION=${REGION:-"us-central1"}
ENVIRONMENT=${ENVIRONMENT:-"prod"}
IMAGE_TAG=${IMAGE_TAG:-"latest"}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if gcloud is installed
    if ! command -v gcloud &> /dev/null; then
        error "gcloud CLI is not installed. Please install it first."
    fi
    
    # Check if terraform is installed
    if ! command -v terraform &> /dev/null; then
        error "Terraform is not installed. Please install it first."
    fi
    
    # Check if docker is installed
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed. Please install it first."
    fi
    
    # Check if logged in to gcloud
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
        error "Not logged in to gcloud. Please run 'gcloud auth login' first."
    fi
    
    log "Prerequisites check passed"
}

# Set up GCP project
setup_project() {
    log "Setting up GCP project..."
    
    gcloud config set project $PROJECT_ID
    gcloud config set compute/region $REGION
    
    log "Project setup complete"
}

# Build and push Docker images
build_and_push_images() {
    log "Building and pushing Docker images..."
    
    # Configure Docker for GCR
    gcloud auth configure-docker
    
    # Build the production image
    docker build -f deploy/docker/Dockerfile.prod -t gcr.io/$PROJECT_ID/atp-router:$IMAGE_TAG .
    docker build -f deploy/docker/Dockerfile.prod -t gcr.io/$PROJECT_ID/atp-auth:$IMAGE_TAG .
    docker build -f deploy/docker/Dockerfile.prod -t gcr.io/$PROJECT_ID/atp-policy:$IMAGE_TAG .
    docker build -f deploy/docker/Dockerfile.prod -t gcr.io/$PROJECT_ID/atp-cost-optimizer:$IMAGE_TAG .
    docker build -f deploy/docker/Dockerfile.prod -t gcr.io/$PROJECT_ID/atp-memory-gateway:$IMAGE_TAG .
    
    # Push images
    docker push gcr.io/$PROJECT_ID/atp-router:$IMAGE_TAG
    docker push gcr.io/$PROJECT_ID/atp-auth:$IMAGE_TAG
    docker push gcr.io/$PROJECT_ID/atp-policy:$IMAGE_TAG
    docker push gcr.io/$PROJECT_ID/atp-cost-optimizer:$IMAGE_TAG
    docker push gcr.io/$PROJECT_ID/atp-memory-gateway:$IMAGE_TAG
    
    log "Docker images built and pushed"
}

# Deploy infrastructure with Terraform
deploy_infrastructure() {
    log "Deploying infrastructure with Terraform..."
    
    cd deploy/gcp/terraform
    
    # Initialize Terraform
    terraform init
    
    # Plan deployment
    terraform plan -var="project_id=$PROJECT_ID" -var="region=$REGION" -var="environment=$ENVIRONMENT"
    
    # Apply deployment
    terraform apply -var="project_id=$PROJECT_ID" -var="region=$REGION" -var="environment=$ENVIRONMENT" -auto-approve
    
    cd ../../..
    
    log "Infrastructure deployment complete"
}

# Deploy Cloud Run services
deploy_cloud_run() {
    log "Deploying Cloud Run services..."
    
    # Replace PROJECT_ID in the YAML files
    sed -i "s/PROJECT_ID/$PROJECT_ID/g" deploy/gcp/cloud-run.yaml
    
    # Deploy services
    gcloud run services replace deploy/gcp/cloud-run.yaml --region=$REGION
    
    log "Cloud Run services deployed"
}

# Set up monitoring and logging
setup_monitoring() {
    log "Setting up monitoring and logging..."
    
    # Create log-based metrics
    gcloud logging metrics create atp_error_rate \
        --description="ATP error rate metric" \
        --log-filter='resource.type="cloud_run_revision" AND severity>=ERROR' \
        --value-extractor='EXTRACT(jsonPayload.error_count)'
    
    # Create alerting policies
    gcloud alpha monitoring policies create --policy-from-file=deploy/gcp/alerting-policy.yaml
    
    log "Monitoring and logging setup complete"
}

# Run health checks
run_health_checks() {
    log "Running health checks..."
    
    # Get the service URLs
    ROUTER_URL=$(gcloud run services describe atp-router --region=$REGION --format='value(status.url)')
    
    # Check if services are healthy
    if curl -f "$ROUTER_URL/health" > /dev/null 2>&1; then
        log "Router service is healthy"
    else
        warn "Router service health check failed"
    fi
    
    log "Health checks complete"
}

# Main deployment function
main() {
    log "Starting ATP deployment to GCP..."
    
    check_prerequisites
    setup_project
    build_and_push_images
    deploy_infrastructure
    deploy_cloud_run
    setup_monitoring
    run_health_checks
    
    log "ATP deployment to GCP completed successfully!"
    log "Router service URL: $(gcloud run services describe atp-router --region=$REGION --format='value(status.url)')"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --project-id)
            PROJECT_ID="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        --environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        --image-tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --project-id     GCP Project ID"
            echo "  --region         GCP Region (default: us-central1)"
            echo "  --environment    Environment (default: prod)"
            echo "  --image-tag      Docker image tag (default: latest)"
            echo "  --help           Show this help message"
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

# Run main function
main