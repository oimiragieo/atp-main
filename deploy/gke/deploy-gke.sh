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

# ATP GKE Deployment Script
# This script deploys the ATP platform to Google Kubernetes Engine

set -euo pipefail

# Configuration
PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-us-central1}"
CLUSTER_NAME="${CLUSTER_NAME:-atp-production-cluster}"
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
    
    # Check if kubectl is installed
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed. Please install it first."
        exit 1
    fi
    
    # Check if helm is installed
    if ! command -v helm &> /dev/null; then
        log_error "Helm is not installed. Please install it first."
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
        "container.googleapis.com"
        "compute.googleapis.com"
        "cloudbuild.googleapis.com"
        "containerregistry.googleapis.com"
        "sqladmin.googleapis.com"
        "redis.googleapis.com"
        "secretmanager.googleapis.com"
        "cloudtrace.googleapis.com"
        "monitoring.googleapis.com"
        "logging.googleapis.com"
        "servicenetworking.googleapis.com"
        "cloudkms.googleapis.com"
        "binaryauthorization.googleapis.com"
        "meshconfig.googleapis.com"
        "anthos.googleapis.com"
    )
    
    for api in "${apis[@]}"; do
        log_info "Enabling $api..."
        gcloud services enable "$api" --project="$PROJECT_ID"
    done
    
    log_success "APIs enabled successfully"
}

# Create VPC network
create_vpc_network() {
    log_info "Creating VPC network..."
    
    # Create VPC network
    if ! gcloud compute networks describe atp-vpc --project="$PROJECT_ID" &>/dev/null; then
        gcloud compute networks create atp-vpc \
            --subnet-mode=custom \
            --bgp-routing-mode=regional \
            --project="$PROJECT_ID"
    fi
    
    # Create subnet
    if ! gcloud compute networks subnets describe atp-subnet \
        --region="$REGION" --project="$PROJECT_ID" &>/dev/null; then
        
        gcloud compute networks subnets create atp-subnet \
            --network=atp-vpc \
            --range=10.0.0.0/16 \
            --region="$REGION" \
            --secondary-range=atp-pods=10.1.0.0/16,atp-services=10.2.0.0/16 \
            --enable-private-ip-google-access \
            --project="$PROJECT_ID"
    fi
    
    # Create firewall rules
    if ! gcloud compute firewall-rules describe atp-allow-internal \
        --project="$PROJECT_ID" &>/dev/null; then
        
        gcloud compute firewall-rules create atp-allow-internal \
            --network=atp-vpc \
            --allow=tcp,udp,icmp \
            --source-ranges=10.0.0.0/8 \
            --project="$PROJECT_ID"
    fi
    
    if ! gcloud compute firewall-rules describe atp-allow-ssh \
        --project="$PROJECT_ID" &>/dev/null; then
        
        gcloud compute firewall-rules create atp-allow-ssh \
            --network=atp-vpc \
            --allow=tcp:22 \
            --source-ranges=0.0.0.0/0 \
            --project="$PROJECT_ID"
    fi
    
    log_success "VPC network created"
}

# Create service accounts
create_service_accounts() {
    log_info "Creating service accounts..."
    
    # GKE node service account
    if ! gcloud iam service-accounts describe "atp-gke-nodes@$PROJECT_ID.iam.gserviceaccount.com" &>/dev/null; then
        gcloud iam service-accounts create atp-gke-nodes \
            --display-name="ATP GKE Nodes" \
            --description="Service account for ATP GKE cluster nodes" \
            --project="$PROJECT_ID"
    fi
    
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
    
    # GKE node service account permissions
    local node_sa="atp-gke-nodes@$PROJECT_ID.iam.gserviceaccount.com"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$node_sa" \
        --role="roles/logging.logWriter"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$node_sa" \
        --role="roles/monitoring.metricWriter"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$node_sa" \
        --role="roles/monitoring.viewer"
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$node_sa" \
        --role="roles/stackdriver.resourceMetadata.writer"
    
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
    
    # Enable workload identity binding
    gcloud iam service-accounts add-iam-policy-binding \
        --role roles/iam.workloadIdentityUser \
        --member "serviceAccount:$PROJECT_ID.svc.id.goog[atp-system/atp-router-service]" \
        "$router_sa" \
        --project="$PROJECT_ID"
    
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
    
    # Enable workload identity binding
    gcloud iam service-accounts add-iam-policy-binding \
        --role roles/iam.workloadIdentityUser \
        --member "serviceAccount:$PROJECT_ID.svc.id.goog[atp-system/atp-memory-gateway]" \
        "$gateway_sa" \
        --project="$PROJECT_ID"
    
    log_success "IAM permissions granted"
}

# Create KMS key for etcd encryption
create_kms_key() {
    log_info "Creating KMS key for etcd encryption..."
    
    # Create key ring
    if ! gcloud kms keyrings describe atp-cluster \
        --location="$REGION" --project="$PROJECT_ID" &>/dev/null; then
        
        gcloud kms keyrings create atp-cluster \
            --location="$REGION" \
            --project="$PROJECT_ID"
    fi
    
    # Create key
    if ! gcloud kms keys describe etcd-encryption \
        --keyring=atp-cluster \
        --location="$REGION" \
        --project="$PROJECT_ID" &>/dev/null; then
        
        gcloud kms keys create etcd-encryption \
            --keyring=atp-cluster \
            --location="$REGION" \
            --purpose=encryption \
            --project="$PROJECT_ID"
    fi
    
    log_success "KMS key created"
}

# Create GKE cluster
create_gke_cluster() {
    log_info "Creating GKE cluster..."
    
    # Check if cluster already exists
    if gcloud container clusters describe "$CLUSTER_NAME" \
        --region="$REGION" --project="$PROJECT_ID" &>/dev/null; then
        log_info "GKE cluster already exists"
        return
    fi
    
    # Replace placeholders in cluster config
    local cluster_yaml="/tmp/cluster.yaml"
    sed "s/PROJECT_ID/$PROJECT_ID/g; s/REGION/$REGION/g" \
        deploy/gke/cluster.yaml > "$cluster_yaml"
    
    # Create cluster using gcloud (YAML config not directly supported, so use CLI)
    gcloud container clusters create "$CLUSTER_NAME" \
        --region="$REGION" \
        --network=atp-vpc \
        --subnetwork=atp-subnet \
        --cluster-secondary-range-name=atp-pods \
        --services-secondary-range-name=atp-services \
        --enable-ip-alias \
        --enable-private-nodes \
        --master-ipv4-cidr=172.16.0.0/28 \
        --enable-master-global-access \
        --enable-master-authorized-networks \
        --master-authorized-networks=203.0.113.0/24,198.51.100.0/24 \
        --enable-network-policy \
        --enable-autorepair \
        --enable-autoupgrade \
        --enable-autoscaling \
        --min-nodes=1 \
        --max-nodes=10 \
        --num-nodes=3 \
        --node-locations="$REGION-a,$REGION-b,$REGION-c" \
        --machine-type=e2-standard-4 \
        --disk-type=pd-ssd \
        --disk-size=100GB \
        --image-type=COS_CONTAINERD \
        --enable-shielded-nodes \
        --enable-workload-identity \
        --workload-pool="$PROJECT_ID.svc.id.goog" \
        --database-encryption-key="projects/$PROJECT_ID/locations/$REGION/keyRings/atp-cluster/cryptoKeys/etcd-encryption" \
        --enable-binary-authorization \
        --logging=SYSTEM,WORKLOAD,API_SERVER \
        --monitoring=SYSTEM,WORKLOAD,API_SERVER \
        --maintenance-window-start=2023-01-01T02:00:00Z \
        --maintenance-window-end=2023-01-01T06:00:00Z \
        --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU" \
        --release-channel=regular \
        --service-account="atp-gke-nodes@$PROJECT_ID.iam.gserviceaccount.com" \
        --project="$PROJECT_ID"
    
    # Remove default node pool
    gcloud container node-pools delete default-pool \
        --cluster="$CLUSTER_NAME" \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --quiet
    
    # Clean up temporary file
    rm -f "$cluster_yaml"
    
    log_success "GKE cluster created"
}

# Create node pools
create_node_pools() {
    log_info "Creating node pools..."
    
    # System node pool
    if ! gcloud container node-pools describe system-pool \
        --cluster="$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" &>/dev/null; then
        
        gcloud container node-pools create system-pool \
            --cluster="$CLUSTER_NAME" \
            --region="$REGION" \
            --machine-type=e2-standard-2 \
            --disk-type=pd-standard \
            --disk-size=50GB \
            --num-nodes=2 \
            --enable-autoscaling \
            --min-nodes=2 \
            --max-nodes=10 \
            --node-taints=node-type=system:NoSchedule \
            --node-labels=node-type=system,environment=production \
            --enable-autorepair \
            --enable-autoupgrade \
            --service-account="atp-gke-nodes@$PROJECT_ID.iam.gserviceaccount.com" \
            --project="$PROJECT_ID"
    fi
    
    # Application node pool
    if ! gcloud container node-pools describe app-pool \
        --cluster="$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" &>/dev/null; then
        
        gcloud container node-pools create app-pool \
            --cluster="$CLUSTER_NAME" \
            --region="$REGION" \
            --machine-type=e2-standard-4 \
            --disk-type=pd-ssd \
            --disk-size=100GB \
            --num-nodes=3 \
            --enable-autoscaling \
            --min-nodes=3 \
            --max-nodes=50 \
            --node-labels=node-type=application,environment=production \
            --enable-autorepair \
            --enable-autoupgrade \
            --service-account="atp-gke-nodes@$PROJECT_ID.iam.gserviceaccount.com" \
            --project="$PROJECT_ID"
    fi
    
    # Compute node pool (spot instances for cost optimization)
    if ! gcloud container node-pools describe compute-pool \
        --cluster="$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" &>/dev/null; then
        
        gcloud container node-pools create compute-pool \
            --cluster="$CLUSTER_NAME" \
            --region="$REGION" \
            --machine-type=c2-standard-8 \
            --disk-type=pd-ssd \
            --disk-size=200GB \
            --num-nodes=0 \
            --enable-autoscaling \
            --min-nodes=0 \
            --max-nodes=20 \
            --spot \
            --node-taints=node-type=compute:NoSchedule \
            --node-labels=node-type=compute,workload-type=cpu-intensive \
            --local-ssd-count=1 \
            --enable-autorepair \
            --enable-autoupgrade \
            --service-account="atp-gke-nodes@$PROJECT_ID.iam.gserviceaccount.com" \
            --project="$PROJECT_ID"
    fi
    
    log_success "Node pools created"
}

# Configure kubectl
configure_kubectl() {
    log_info "Configuring kubectl..."
    
    gcloud container clusters get-credentials "$CLUSTER_NAME" \
        --region="$REGION" \
        --project="$PROJECT_ID"
    
    # Verify connection
    kubectl cluster-info
    
    log_success "kubectl configured"
}

# Install Istio
install_istio() {
    log_info "Installing Istio..."
    
    # Check if Istio is already installed
    if kubectl get namespace istio-system &>/dev/null; then
        log_info "Istio already installed"
        return
    fi
    
    # Download and install Istio
    curl -L https://istio.io/downloadIstio | sh -
    export PATH="$PWD/istio-*/bin:$PATH"
    
    # Install Istio
    istioctl install --set values.defaultRevision=default -y
    
    # Enable Istio injection for atp-system namespace
    kubectl label namespace atp-system istio-injection=enabled --overwrite
    
    log_success "Istio installed"
}

# Create namespaces
create_namespaces() {
    log_info "Creating namespaces..."
    
    # Create atp-system namespace
    kubectl create namespace atp-system --dry-run=client -o yaml | kubectl apply -f -
    
    # Label namespace for Istio injection
    kubectl label namespace atp-system istio-injection=enabled --overwrite
    
    # Create monitoring namespace
    kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
    
    log_success "Namespaces created"
}

# Create secrets
create_secrets() {
    log_info "Creating Kubernetes secrets..."
    
    # Database secret
    if ! kubectl get secret atp-database-secret -n atp-system &>/dev/null; then
        # Get Cloud SQL connection string
        local db_connection_name
        db_connection_name=$(gcloud sql instances describe atp-postgres \
            --format="value(connectionName)" --project="$PROJECT_ID")
        
        local db_url="postgresql://atp-user:PASSWORD@/atp?host=/cloudsql/$db_connection_name"
        
        kubectl create secret generic atp-database-secret \
            --from-literal=url="$db_url" \
            -n atp-system
    fi
    
    # Redis secret
    if ! kubectl get secret atp-redis-secret -n atp-system &>/dev/null; then
        local redis_host
        redis_host=$(gcloud redis instances describe atp-redis \
            --region="$REGION" --format="value(host)" --project="$PROJECT_ID")
        
        local redis_url="redis://$redis_host:6379"
        
        kubectl create secret generic atp-redis-secret \
            --from-literal=url="$redis_url" \
            -n atp-system
    fi
    
    # Auth secret
    if ! kubectl get secret atp-auth-secret -n atp-system &>/dev/null; then
        local jwt_secret
        jwt_secret=$(openssl rand -base64 64)
        
        kubectl create secret generic atp-auth-secret \
            --from-literal=jwt-secret="$jwt_secret" \
            -n atp-system
    fi
    
    # Provider secrets (placeholder)
    if ! kubectl get secret atp-provider-secrets -n atp-system &>/dev/null; then
        kubectl create secret generic atp-provider-secrets \
            --from-literal=openai-api-key="your-openai-api-key" \
            --from-literal=anthropic-api-key="your-anthropic-api-key" \
            --from-literal=google-ai-api-key="your-google-ai-api-key" \
            -n atp-system
        
        log_warning "Provider secrets created with placeholder values. Please update with actual API keys."
    fi
    
    # TLS secret for Istio gateway
    if ! kubectl get secret atp-tls-secret -n atp-system &>/dev/null; then
        # Create self-signed certificate (replace with real certificate in production)
        openssl req -x509 -newkey rsa:4096 -keyout tls.key -out tls.crt -days 365 -nodes \
            -subj "/CN=atp.example.com/O=ATP Platform"
        
        kubectl create secret tls atp-tls-secret \
            --cert=tls.crt \
            --key=tls.key \
            -n atp-system
        
        rm -f tls.key tls.crt
        
        log_warning "TLS secret created with self-signed certificate. Please update with real certificate."
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

# Deploy Helm charts
deploy_helm_charts() {
    log_info "Deploying Helm charts..."
    
    # Add Helm repositories
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
    helm repo add grafana https://grafana.github.io/helm-charts
    helm repo add jaeger https://jaegertracing.github.io/helm-charts
    helm repo update
    
    # Install Prometheus
    if ! helm list -n monitoring | grep -q prometheus; then
        helm install prometheus prometheus-community/kube-prometheus-stack \
            --namespace monitoring \
            --create-namespace \
            --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
            --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false
    fi
    
    # Install Jaeger
    if ! helm list -n monitoring | grep -q jaeger; then
        helm install jaeger jaeger/jaeger \
            --namespace monitoring \
            --set provisionDataStore.cassandra=false \
            --set provisionDataStore.elasticsearch=true \
            --set storage.type=elasticsearch
    fi
    
    # Deploy ATP services using Helm
    helm upgrade --install atp-platform deploy/helm/atp-platform \
        --namespace atp-system \
        --set image.repository="gcr.io/$PROJECT_ID" \
        --set image.tag=latest \
        --set project.id="$PROJECT_ID" \
        --set cluster.region="$REGION"
    
    log_success "Helm charts deployed"
}

# Apply Istio configuration
apply_istio_config() {
    log_info "Applying Istio configuration..."
    
    # Replace placeholders in Istio config
    local istio_yaml="/tmp/istio-config.yaml"
    sed "s/PROJECT_ID/$PROJECT_ID/g" \
        deploy/gke/istio-config.yaml > "$istio_yaml"
    
    # Apply Istio configuration
    kubectl apply -f "$istio_yaml"
    
    # Clean up temporary file
    rm -f "$istio_yaml"
    
    log_success "Istio configuration applied"
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."
    
    # Create migration job
    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: atp-migration-job
  namespace: atp-system
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
      serviceAccountName: atp-router-service
  backoffLimit: 3
EOF
    
    # Wait for migration to complete
    kubectl wait --for=condition=complete job/atp-migration-job -n atp-system --timeout=300s
    
    log_success "Database migrations completed"
}

# Verify deployment
verify_deployment() {
    log_info "Verifying deployment..."
    
    # Check pod status
    kubectl get pods -n atp-system
    
    # Check service status
    kubectl get services -n atp-system
    
    # Check Istio gateway
    kubectl get gateway -n atp-system
    
    # Get external IP
    local external_ip
    external_ip=$(kubectl get service istio-ingressgateway -n istio-system \
        -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
    
    if [[ -n "$external_ip" ]]; then
        log_success "Deployment verified. External IP: $external_ip"
        log_info "Update your DNS records to point to this IP address"
    else
        log_warning "External IP not yet assigned. Check again in a few minutes."
    fi
    
    # Test health endpoints
    log_info "Testing health endpoints..."
    kubectl port-forward -n atp-system svc/atp-router-service 8080:8080 &
    local port_forward_pid=$!
    
    sleep 5
    
    if curl -f http://localhost:8080/health; then
        log_success "Health endpoint responding"
    else
        log_warning "Health endpoint not responding"
    fi
    
    kill $port_forward_pid 2>/dev/null || true
}

# Main deployment function
main() {
    log_info "Starting ATP GKE deployment..."
    
    check_prerequisites
    enable_apis
    create_vpc_network
    create_service_accounts
    grant_iam_permissions
    create_kms_key
    create_gke_cluster
    create_node_pools
    configure_kubectl
    install_istio
    create_namespaces
    create_secrets
    build_and_push_images
    deploy_helm_charts
    apply_istio_config
    run_migrations
    verify_deployment
    
    log_success "ATP GKE deployment completed successfully!"
    
    log_info "Next steps:"
    echo "1. Update DNS records to point to the external IP"
    echo "2. Update provider API key secrets with actual values"
    echo "3. Configure monitoring dashboards"
    echo "4. Set up backup and disaster recovery procedures"
    echo "5. Configure CI/CD pipeline for automated deployments"
    echo "6. Review and adjust resource limits based on usage"
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
            
            # Delete cluster
            gcloud container clusters delete "$CLUSTER_NAME" \
                --region="$REGION" \
                --project="$PROJECT_ID" \
                --quiet
            
            # Delete VPC network
            gcloud compute networks delete atp-vpc \
                --project="$PROJECT_ID" \
                --quiet
            
            log_success "Cleanup completed"
        else
            log_info "Cleanup cancelled"
        fi
        ;;
    "help")
        echo "Usage: $0 [deploy|cleanup|help]"
        echo "  deploy  - Deploy ATP to GKE (default)"
        echo "  cleanup - Remove all ATP resources"
        echo "  help    - Show this help message"
        ;;
    *)
        log_error "Unknown command: $1"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac