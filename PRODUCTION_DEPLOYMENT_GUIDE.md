# ATP Enterprise AI Platform - Production Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the ATP Enterprise AI Platform to production environments, with a focus on Google Cloud Platform and local Docker deployments.

## Prerequisites

### System Requirements
- **Docker** 20.10+ with Docker Compose
- **Google Cloud SDK** (gcloud) for GCP deployments
- **Kubernetes** 1.24+ (for GKE deployments)
- **Terraform** 1.0+ (for infrastructure as code)
- **Helm** 3.8+ (for Kubernetes package management)

### Access Requirements
- GCP Project with billing enabled
- Appropriate IAM permissions for resource creation
- Domain name for SSL certificates (recommended)

## Quick Start - Local Docker Deployment

### 1. Clone and Setup
```bash
git clone <repository-url>
cd atp-main
cp configs/examples/.env.example .env
```

### 2. Configure Environment
Edit `.env` file with your settings:
```bash
# Required: Set your API keys
OPENAI_API_KEY=your-openai-api-key-here
ANTHROPIC_API_KEY=your-anthropic-api-key-here
GOOGLE_API_KEY=your-google-api-key-here

# Security: Change default secrets
JWT_SECRET=your-secure-jwt-secret-here
ENCRYPTION_KEY=your-32-byte-encryption-key-here
```

### 3. Deploy with Docker Compose
```bash
docker-compose -f deploy/docker/docker-compose.prod.yml up -d
```

### 4. Verify Deployment
```bash
curl http://localhost:8080/health
```

## Production Deployment - Google Cloud Platform

### Option 1: Cloud Run (Serverless)

#### 1. Set Environment Variables
```bash
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1
export ENVIRONMENT=production
```

#### 2. Deploy Infrastructure
```bash
cd deploy/gcp/terraform
terraform init
terraform plan -var="project_id=$PROJECT_ID"
terraform apply -var="project_id=$PROJECT_ID"
```

#### 3. Deploy Services
```bash
cd ../..
./deploy/gcp/deploy.sh --project-id $PROJECT_ID --region $REGION
```

### Option 2: Google Kubernetes Engine (GKE)

#### 1. Create GKE Cluster
```bash
gcloud container clusters create atp-cluster \
  --project=$PROJECT_ID \
  --zone=us-central1-a \
  --num-nodes=3 \
  --enable-autoscaling \
  --min-nodes=1 \
  --max-nodes=10
```

#### 2. Deploy with Helm
```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Install dependencies
helm install postgresql bitnami/postgresql
helm install redis bitnami/redis

# Install ATP
helm install atp deploy/helm/atp/ \
  --set image.repository=gcr.io/$PROJECT_ID/atp \
  --set postgresql.auth.password=your-secure-password \
  --set redis.auth.password=your-secure-password
```

## Configuration Management

### Environment-Specific Configurations

#### Development
```yaml
# configs/examples/app.yaml
app:
  environment: development
  debug: true
logging:
  level: DEBUG
```

#### Production
```yaml
# configs/production/app.yaml
app:
  environment: production
  debug: false
logging:
  level: INFO
```

### Secret Management

#### Local Development
Use `.env` file for local secrets:
```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/atp
REDIS_URL=redis://localhost:6379
```

#### Production (GCP)
Use Google Secret Manager:
```bash
# Create secrets
gcloud secrets create database-url --data-file=database-url.txt
gcloud secrets create redis-url --data-file=redis-url.txt

# Grant access to service account
gcloud secrets add-iam-policy-binding database-url \
  --member="serviceAccount:atp-service@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## Security Configuration

### 1. SSL/TLS Setup
```bash
# For GCP Load Balancer
gcloud compute ssl-certificates create atp-ssl \
  --domains=atp.yourdomain.com
```

### 2. Firewall Rules
```bash
# Allow HTTPS traffic
gcloud compute firewall-rules create allow-atp-https \
  --allow tcp:443 \
  --source-ranges 0.0.0.0/0 \
  --description "Allow HTTPS to ATP"
```

### 3. Identity and Access Management
```bash
# Create service account
gcloud iam service-accounts create atp-service \
  --display-name="ATP Service Account"

# Grant necessary roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:atp-service@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"
```

## Monitoring and Observability

### 1. Prometheus Metrics
Access metrics at: `http://your-domain:9090/metrics`

Key metrics to monitor:
- `atp_requests_total` - Total requests
- `atp_request_duration_seconds` - Request latency
- `atp_active_connections` - Active connections
- `atp_cost_total` - Total costs

### 2. Grafana Dashboards
Access dashboards at: `http://your-domain:3000`

Default login: `admin/admin` (change immediately)

### 3. Log Aggregation
Logs are automatically sent to Google Cloud Logging in GCP deployments.

For local deployments, logs are available via:
```bash
docker-compose logs -f atp-router
```

## Scaling and Performance

### Horizontal Scaling
```bash
# Scale Cloud Run
gcloud run services update atp-router \
  --max-instances=100 \
  --min-instances=1

# Scale GKE deployment
kubectl scale deployment atp-router --replicas=5
```

### Vertical Scaling
```bash
# Update resource limits
kubectl patch deployment atp-router -p '{"spec":{"template":{"spec":{"containers":[{"name":"router","resources":{"limits":{"cpu":"2","memory":"4Gi"}}}]}}}}'
```

### Auto-scaling
Auto-scaling is configured by default:
- **Cloud Run**: Scales based on request volume
- **GKE**: HPA scales based on CPU/memory usage

## Backup and Disaster Recovery

### Database Backups
```bash
# Automated backups are enabled by default
# Manual backup
gcloud sql backups create --instance=atp-postgres
```

### Configuration Backups
```bash
# Backup Kubernetes configurations
kubectl get all -n atp-system -o yaml > atp-backup.yaml

# Backup secrets
kubectl get secrets -n atp-system -o yaml > atp-secrets-backup.yaml
```

### Disaster Recovery Testing
```bash
# Test failover procedures
./scripts/test-disaster-recovery.sh
```

## Troubleshooting

### Common Issues

#### 1. Service Not Starting
```bash
# Check logs
kubectl logs deployment/atp-router
docker-compose logs atp-router

# Check configuration
kubectl describe deployment atp-router
```

#### 2. Database Connection Issues
```bash
# Test database connectivity
kubectl exec -it deployment/atp-router -- psql $DATABASE_URL -c "SELECT 1"
```

#### 3. High Memory Usage
```bash
# Check memory usage
kubectl top pods
docker stats
```

### Health Checks
```bash
# Service health
curl https://your-domain/health

# Database health
curl https://your-domain/health/database

# Redis health
curl https://your-domain/health/redis
```

## Maintenance

### Regular Tasks
1. **Update dependencies** monthly
2. **Rotate secrets** quarterly
3. **Review logs** weekly
4. **Performance testing** monthly
5. **Security scanning** weekly

### Updates and Patches
```bash
# Update Docker images
docker-compose pull
docker-compose up -d

# Update Helm chart
helm upgrade atp deploy/helm/atp/
```

## Cost Optimization

### Resource Right-Sizing
- Monitor resource usage with Grafana
- Adjust CPU/memory limits based on actual usage
- Use preemptible instances for non-critical workloads

### Cost Monitoring
- Set up billing alerts in GCP
- Monitor costs with the built-in cost tracking
- Review monthly cost reports

## Support and Documentation

### Additional Resources
- [API Documentation](docs/api/)
- [Architecture Guide](docs/architecture/)
- [Security Guide](SECURITY_CLEANUP_SUMMARY.md)
- [Troubleshooting Guide](docs/troubleshooting/)

### Getting Help
- GitHub Issues: [Repository Issues](https://github.com/your-org/atp/issues)
- Documentation: [Full Documentation](docs/)
- Community: [Discord/Slack Channel]

## Checklist for Production Deployment

### Pre-Deployment
- [ ] All secrets configured in secret management system
- [ ] SSL certificates obtained and configured
- [ ] Monitoring and alerting set up
- [ ] Backup procedures tested
- [ ] Security scan completed
- [ ] Performance testing completed

### Post-Deployment
- [ ] Health checks passing
- [ ] Monitoring dashboards accessible
- [ ] Log aggregation working
- [ ] Backup procedures verified
- [ ] Security alerts configured
- [ ] Documentation updated

### Ongoing Maintenance
- [ ] Regular security updates
- [ ] Performance monitoring
- [ ] Cost optimization reviews
- [ ] Disaster recovery testing
- [ ] Compliance audits