# ATP Cloud Run Deployment

This directory contains the configuration and deployment scripts for running the ATP platform on Google Cloud Run.

## Overview

The ATP platform is deployed as a serverless application on Google Cloud Run, providing:

- **Auto-scaling**: Scales from 0 to 1000+ instances based on demand
- **Pay-per-use**: Only pay for actual request processing time
- **Managed infrastructure**: No server management required
- **Global availability**: Deploy across multiple regions
- **Built-in security**: Integrated with Google Cloud IAM and security services

## Architecture

```
Internet → Load Balancer → Cloud Run Services
                         ├── ATP Router Service
                         └── ATP Memory Gateway
                              ↓
                         Cloud SQL (PostgreSQL)
                         Redis (Memorystore)
                         Secret Manager
```

## Services

### ATP Router Service
- **Image**: `gcr.io/PROJECT_ID/atp-router:latest`
- **Port**: 8080
- **Resources**: 2 CPU, 4GB RAM
- **Scaling**: 1-1000 instances
- **Concurrency**: 1000 requests per instance

### ATP Memory Gateway
- **Image**: `gcr.io/PROJECT_ID/atp-memory-gateway:latest`
- **Port**: 8000
- **Resources**: 1 CPU, 2GB RAM
- **Scaling**: 1-500 instances
- **Concurrency**: 500 requests per instance

## Prerequisites

1. **Google Cloud Project** with billing enabled
2. **gcloud CLI** installed and authenticated
3. **Docker** installed for building images
4. **Required APIs** enabled (done automatically by deployment script)

## Quick Start

1. **Set environment variables**:
   ```bash
   export PROJECT_ID="your-gcp-project-id"
   export REGION="us-central1"
   ```

2. **Run deployment script**:
   ```bash
   ./deploy/cloud-run/deploy.sh
   ```

3. **Update secrets** with actual values:
   ```bash
   # Update OIDC configuration
   gcloud secrets versions add atp-oidc-secret --data-file=oidc-config.json
   
   # Update provider API keys
   gcloud secrets versions add atp-provider-secrets --data-file=provider-keys.json
   ```

## Manual Deployment

If you prefer to deploy manually or customize the deployment:

### 1. Enable APIs
```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  containerregistry.googleapis.com sqladmin.googleapis.com \
  redis.googleapis.com secretmanager.googleapis.com
```

### 2. Create Infrastructure
```bash
# Create Cloud SQL instance
gcloud sql instances create atp-postgres \
  --database-version=POSTGRES_14 \
  --tier=db-custom-2-4096 \
  --region=$REGION

# Create Redis instance
gcloud redis instances create atp-redis \
  --size=1 --region=$REGION
```

### 3. Build and Push Images
```bash
# Build router service
docker build -t gcr.io/$PROJECT_ID/atp-router:latest \
  -f deploy/docker/router-service.Dockerfile .
docker push gcr.io/$PROJECT_ID/atp-router:latest

# Build memory gateway
docker build -t gcr.io/$PROJECT_ID/atp-memory-gateway:latest \
  -f deploy/docker/memory-gateway.Dockerfile .
docker push gcr.io/$PROJECT_ID/atp-memory-gateway:latest
```

### 4. Deploy Services
```bash
# Deploy router service
gcloud run services replace deploy/cloud-run/router-service.yaml \
  --region=$REGION

# Deploy memory gateway
gcloud run services replace deploy/cloud-run/memory-gateway.yaml \
  --region=$REGION
```

## Configuration

### Environment Variables

#### Router Service
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `JWT_SECRET_KEY`: JWT signing key
- `OIDC_CLIENT_ID`: OIDC client ID
- `OIDC_CLIENT_SECRET`: OIDC client secret
- `OPENAI_API_KEY`: OpenAI API key
- `ANTHROPIC_API_KEY`: Anthropic API key
- `GOOGLE_AI_API_KEY`: Google AI API key

#### Memory Gateway
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `ENCRYPTION_KEY`: Data encryption key
- `PII_DETECTION_ENABLED`: Enable PII detection
- `AUDIT_LOG_ENABLED`: Enable audit logging

### Secrets Management

All sensitive configuration is stored in Google Secret Manager:

```bash
# Database connection
gcloud secrets create atp-database-secret --data-file=-

# Redis connection
gcloud secrets create atp-redis-secret --data-file=-

# Authentication
gcloud secrets create atp-auth-secret --data-file=-

# OIDC configuration
gcloud secrets create atp-oidc-secret --data-file=-

# Provider API keys
gcloud secrets create atp-provider-secrets --data-file=-

# Encryption keys
gcloud secrets create atp-encryption-secret --data-file=-
```

## Scaling Configuration

### Auto-scaling Settings
- **Minimum instances**: 1 (to avoid cold starts)
- **Maximum instances**: 1000 (router), 500 (gateway)
- **Target concurrency**: 80% of max concurrency
- **CPU throttling**: Disabled for consistent performance

### Resource Limits
- **Router Service**: 2 CPU, 4GB RAM
- **Memory Gateway**: 1 CPU, 2GB RAM
- **Request timeout**: 300 seconds
- **Container concurrency**: 1000 (router), 500 (gateway)

## Security

### Network Security
- **VPC Connector**: Private network access to Cloud SQL and Redis
- **Egress**: Private ranges only
- **Ingress**: All (protected by load balancer)

### Identity and Access
- **Service Accounts**: Dedicated service accounts with minimal permissions
- **IAM Roles**: Principle of least privilege
- **Secret Access**: Secrets accessible only to authorized services

### Application Security
- **Non-root containers**: Run as user ID 1000
- **Read-only filesystem**: Prevents runtime modifications
- **Security context**: Drops all capabilities

## Monitoring and Observability

### Health Checks
- **Liveness probe**: `/health` endpoint
- **Readiness probe**: `/ready` endpoint
- **Startup probe**: Extended timeout for initialization

### Logging
- **Structured logging**: JSON format for better parsing
- **Log levels**: Configurable (DEBUG, INFO, WARNING, ERROR)
- **Audit logs**: Separate audit trail for compliance

### Metrics
- **Built-in metrics**: Request count, latency, error rate
- **Custom metrics**: Business metrics via Prometheus
- **Tracing**: Distributed tracing with Cloud Trace

### Alerting
- **Error rate**: Alert on >5% error rate
- **Latency**: Alert on p95 > 2 seconds
- **Availability**: Alert on service downtime
- **Cost**: Alert on budget overruns

## Load Balancing

### Global Load Balancer
- **Type**: HTTP(S) Load Balancer
- **SSL**: Managed SSL certificates
- **CDN**: Cloud CDN for static content
- **WAF**: Cloud Armor for DDoS protection

### Backend Configuration
- **Health checks**: HTTP health checks
- **Session affinity**: None (stateless services)
- **Timeout**: 30 seconds
- **Retry**: Automatic retry on failures

## Disaster Recovery

### Backup Strategy
- **Database**: Automated daily backups with point-in-time recovery
- **Redis**: Automated snapshots
- **Secrets**: Versioned in Secret Manager
- **Configuration**: Version controlled in Git

### Multi-Region Deployment
```bash
# Deploy to multiple regions
for region in us-central1 europe-west1 asia-southeast1; do
  gcloud run services replace router-service.yaml --region=$region
  gcloud run services replace memory-gateway.yaml --region=$region
done
```

### Failover Process
1. **Detection**: Health checks detect service failure
2. **Traffic shift**: Load balancer routes traffic to healthy regions
3. **Recovery**: Failed region automatically recovers when healthy
4. **Monitoring**: Alerts notify operations team

## Cost Optimization

### Pricing Model
- **CPU**: $0.00002400 per vCPU-second
- **Memory**: $0.00000250 per GB-second
- **Requests**: $0.40 per million requests
- **Networking**: Standard egress charges

### Cost Optimization Tips
1. **Right-size resources**: Monitor and adjust CPU/memory allocation
2. **Optimize concurrency**: Higher concurrency = fewer instances
3. **Use minimum instances**: Avoid cold start costs
4. **Monitor usage**: Use Cloud Monitoring to track costs
5. **Set budgets**: Configure budget alerts

### Estimated Monthly Costs
- **Small deployment** (1K requests/day): ~$10-20/month
- **Medium deployment** (100K requests/day): ~$100-200/month
- **Large deployment** (1M requests/day): ~$500-1000/month

## Troubleshooting

### Common Issues

#### Cold Starts
- **Symptom**: High latency on first request
- **Solution**: Set minimum instances to 1

#### Memory Issues
- **Symptom**: Container restarts, OOM errors
- **Solution**: Increase memory allocation

#### Database Connection Issues
- **Symptom**: Connection timeouts, pool exhaustion
- **Solution**: Check VPC connector, connection pooling

#### Secret Access Issues
- **Symptom**: Authentication failures
- **Solution**: Verify service account permissions

### Debugging Commands

```bash
# View service logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=atp-router-service" --limit=50

# Check service status
gcloud run services describe atp-router-service --region=$REGION

# View metrics
gcloud monitoring metrics list --filter="resource.type=cloud_run_revision"

# Test health endpoint
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  https://atp-router-service-xxx-uc.a.run.app/health
```

### Performance Tuning

#### Optimize Container Startup
- Use multi-stage Docker builds
- Minimize image size
- Pre-compile Python bytecode
- Use startup probes for slow initialization

#### Optimize Request Handling
- Use async/await for I/O operations
- Implement connection pooling
- Cache frequently accessed data
- Use streaming for large responses

#### Optimize Resource Usage
- Monitor CPU and memory usage
- Adjust concurrency settings
- Use appropriate instance sizes
- Implement graceful shutdown

## CI/CD Integration

### Cloud Build Configuration
```yaml
steps:
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '-t', 'gcr.io/$PROJECT_ID/atp-router:$COMMIT_SHA', '-f', 'deploy/docker/router-service.Dockerfile', '.']
- name: 'gcr.io/cloud-builders/docker'
  args: ['push', 'gcr.io/$PROJECT_ID/atp-router:$COMMIT_SHA']
- name: 'gcr.io/cloud-builders/gcloud'
  args: ['run', 'deploy', 'atp-router-service', '--image', 'gcr.io/$PROJECT_ID/atp-router:$COMMIT_SHA', '--region', 'us-central1']
```

### GitHub Actions
```yaml
name: Deploy to Cloud Run
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - uses: google-github-actions/setup-gcloud@v0
      with:
        service_account_key: ${{ secrets.GCP_SA_KEY }}
        project_id: ${{ secrets.GCP_PROJECT_ID }}
    - run: ./deploy/cloud-run/deploy.sh
```

## Support

For issues and questions:
1. Check the [troubleshooting section](#troubleshooting)
2. Review Cloud Run logs and metrics
3. Consult the [ATP documentation](../../README.md)
4. Open an issue in the project repository

## Next Steps

After successful deployment:
1. **Configure DNS**: Point your domain to the load balancer IP
2. **Update secrets**: Replace placeholder values with actual credentials
3. **Set up monitoring**: Configure dashboards and alerts
4. **Test thoroughly**: Run end-to-end tests
5. **Plan scaling**: Monitor usage and adjust resources as needed