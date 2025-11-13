# On-Premises ATP Deployment Guide

This guide covers deploying ATP in air-gapped environments and on-premises infrastructure.

## Overview

ATP supports deployment in environments with limited or no internet connectivity through:

- **Kustomize overlays** for air-gapped configuration
- **Image registry synchronization** for offline deployments
- **Local model caching** for reduced external dependencies
- **Offline installation simulation** for validation

## Prerequisites

### Infrastructure Requirements

- Kubernetes cluster (v1.24+)
- Internal container registry
- Persistent storage for model cache
- Network policies for security isolation

### Tools Required

- `kubectl` configured for your cluster
- `kustomize` (v4.0+)
- `docker` or `podman` for image operations
- Python 3.8+ for sync scripts

## Air-Gapped Deployment

### Step 1: Prepare Internal Registry

```bash
# Login to your internal registry
docker login registry.internal.company.com

# Create namespace for ATP
kubectl create namespace atp-system
```

### Step 2: Sync Images to Internal Registry

Use the provided image sync script to pull images from external registries and push to your internal registry:

```bash
# Dry run first
python tools/sync_images.py \
  --source-registry docker.io \
  --target-registry registry.internal.company.com \
  --dry-run

# Perform actual sync
python tools/sync_images.py \
  --source-registry docker.io \
  --target-registry registry.internal.company.com \
  --concurrency 3
```

Or use the configuration file:

```bash
python tools/sync_images.py --config deploy/kustomize/sync-config.yaml
```

### Step 3: Deploy with Kustomize

```bash
# Deploy base configuration
kubectl apply -k deploy/kustomize/base

# Deploy air-gapped overlay
kubectl apply -k deploy/kustomize/overlays/air-gapped
```

### Step 4: Verify Deployment

```bash
# Check pod status
kubectl get pods -n atp-system

# Check service endpoints
kubectl get svc -n atp-system

# Verify image pull secrets
kubectl get secrets -n atp-system
```

## Configuration

### Base Configuration

The base Kustomize configuration includes:

- **Deployment**: ATP router with anti-affinity and topology spread
- **Service**: ClusterIP service for internal communication
- **ServiceMonitor**: Prometheus metrics collection
- **NetworkPolicy**: Security isolation
- **HPA**: Horizontal pod autoscaling
- **PDB**: Pod disruption budget
- **PVC**: Persistent volume for model cache

### Air-Gapped Overlay

The air-gapped overlay adds:

- **Internal registry images**: All images redirected to internal registry
- **Offline mode**: Environment variables for air-gapped operation
- **Local model cache**: Persistent volume for cached models
- **Registry certificates**: Secrets for internal registry authentication
- **Network restrictions**: Enhanced network policies

## Environment Variables

### Air-Gapped Mode

```yaml
env:
  - name: ATP_AIR_GAPPED
    value: "true"
  - name: ATP_DISABLE_TELEMETRY
    value: "true"
  - name: ATP_OFFLINE_MODE
    value: "true"
  - name: ATP_DISABLE_EXTERNAL_APIS
    value: "true"
  - name: ATP_LOCAL_MODEL_CACHE
    value: "/app/models"
```

### Database Configuration

```yaml
env:
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: atp-secrets
        key: database-url
  - name: REDIS_URL
    valueFrom:
      secretKeyRef:
        name: atp-secrets
        key: redis-url
```

## Storage Configuration

### Model Cache PVC

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: atp-model-cache
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 50Gi
  storageClassName: local-storage
```

### Registry Certificates

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: registry-certs
type: Opaque
data:
  ca.crt: <base64-encoded-ca-cert>
  registry.crt: <base64-encoded-registry-cert>
```

## Network Security

### Network Policies

The deployment includes network policies that:

- Allow traffic only from authorized namespaces
- Block external internet access in air-gapped mode
- Enable communication with required services (PostgreSQL, Redis, Prometheus)

### Service Mesh Integration

For advanced networking:

```yaml
# Example Istio integration
apiVersion: networking.istio.io/v1beta1
kind: Gateway
metadata:
  name: atp-gateway
spec:
  selector:
    istio: ingressgateway
  servers:
  - port:
      number: 443
      name: https
      protocol: HTTPS
    tls:
      mode: SIMPLE
      credentialName: atp-tls
    hosts:
    - atp.internal.company.com
```

## Monitoring and Observability

### Metrics

The on-prem deployment exposes these metrics:

- `onprem_deploys_total`: Total deployment attempts
- `onprem_deploy_success_total`: Successful deployments
- `onprem_deploy_failed_total`: Failed deployments
- `onprem_image_sync_duration_seconds`: Image sync duration histogram

### Logging

Configure centralized logging:

```yaml
# Example Fluent Bit configuration
apiVersion: v1
kind: ConfigMap
metadata:
  name: fluent-bit-config
data:
  fluent-bit.conf: |
    [INPUT]
        Name              tail
        Path              /var/log/containers/*atp*.log
        Parser            docker
        Tag               atp.*
        Refresh_Interval  5

    [OUTPUT]
        Name  elasticsearch
        Host  elasticsearch.internal
        Port  9200
        Index atp-logs
```

## Troubleshooting

### Common Issues

#### Image Pull Errors

```bash
# Check image exists in registry
docker pull registry.internal.company.com/atp/router:latest

# Verify registry credentials
kubectl get secrets -n atp-system

# Check network policies
kubectl get networkpolicies -n atp-system
```

#### Pod Startup Failures

```bash
# Check pod events
kubectl describe pod <pod-name> -n atp-system

# Check logs
kubectl logs <pod-name> -n atp-system

# Verify PVC binding
kubectl get pvc -n atp-system
```

#### Service Connectivity

```bash
# Test service DNS resolution
kubectl run test --image=busybox --rm -it -- nslookup atp-router.atp-system.svc.cluster.local

# Check service endpoints
kubectl get endpoints -n atp-system
```

### Health Checks

```bash
# Check ATP health endpoint
curl -k https://atp-router.atp-system.svc.cluster.local/healthz

# Verify metrics endpoint
curl -k https://atp-router.atp-system.svc.cluster.local/metrics
```

## Backup and Recovery

### Configuration Backup

```bash
# Backup Kustomize configurations
tar -czf atp-config-backup.tar.gz deploy/kustomize/

# Backup Helm values
cp deploy/helm/atp/values.yaml values-backup.yaml
```

### Data Backup

```bash
# Backup PostgreSQL
kubectl exec -n atp-system postgres-0 -- pg_dump -U atp atp > atp-db-backup.sql

# Backup Redis (if using persistence)
kubectl exec -n atp-system redis-0 -- redis-cli save
```

### Disaster Recovery

1. Restore configurations from backup
2. Re-sync images to internal registry
3. Restore database from backup
4. Redeploy using Kustomize
5. Verify service functionality

## Performance Tuning

### Resource Limits

```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "1Gi"
    cpu: "1000m"
```

### HPA Configuration

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: atp-router-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: atp-router
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

## Security Considerations

### Certificate Management

- Use internal CA for all certificates
- Rotate certificates regularly
- Store certificates in Kubernetes secrets

### Access Control

- Implement RBAC for Kubernetes resources
- Use network policies for traffic isolation
- Enable audit logging

### Compliance

- Ensure FIPS compliance if required
- Implement data encryption at rest
- Configure security contexts for pods

## Support and Maintenance

### Update Process

1. Sync new images to internal registry
2. Update Kustomize configurations
3. Perform rolling update
4. Verify functionality
5. Rollback if issues detected

### Monitoring Alerts

Configure alerts for:
- Pod restarts
- High resource usage
- Failed deployments
- Certificate expiration
- Storage capacity warnings

This guide provides a comprehensive foundation for deploying ATP in on-premises and air-gapped environments. Adjust configurations based on your specific infrastructure and security requirements.
