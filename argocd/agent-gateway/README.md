# Agent Gateway ArgoCD Applications

This folder contains all ArgoCD Applications for deploying Agent Gateway with observability.

## Installation Order (via sync-wave)

The applications are deployed in the following order using ArgoCD sync waves:

1. **gateway-api-crds** (wave: -2) - Kubernetes Gateway API CRDs
2. **agent-gateway-crds** (wave: -1) - Agent Gateway CRDs
3. **agent-gateway** (wave: 0) - Agent Gateway control plane
4. **agent-gateway-observability** (wave: 1) - OpenTelemetry tracing to Jaeger

## Quick Start

Deploy all Agent Gateway components:

```bash
# Deploy in order
kubectl apply -f argocd/agent-gateway/01-gateway-api-crds.yaml
kubectl apply -f argocd/agent-gateway/02-agent-gateway-crds.yaml
kubectl apply -f argocd/agent-gateway/03-agent-gateway.yaml
kubectl apply -f argocd/agent-gateway/04-agent-gateway-observability.yaml
```

Or deploy all at once (ArgoCD will handle ordering):

```bash
kubectl apply -f argocd/agent-gateway/
```

## Verify Installation

```bash
# Check all applications
kubectl get applications -n argocd | grep gateway

# Check Agent Gateway pods
kubectl get pods -n agentgateway-system

# Check CRDs
kubectl get crd | grep gateway
```

## Components

### 01-gateway-api-crds.yaml
- **Purpose**: Installs Kubernetes Gateway API standard CRDs
- **Source**: https://github.com/kubernetes-sigs/gateway-api (v1.2.1)
- **Resources**: GatewayClass, Gateway, HTTPRoute, GRPCRoute, ReferenceGrant

### 02-agent-gateway-crds.yaml
- **Purpose**: Installs Agent Gateway specific CRDs
- **Source**: oci://ghcr.io/kgateway-dev/charts/agentgateway-crds (v2.2.0-main)
- **Resources**: AgentgatewayBackend, AgentgatewayPolicy, AgentgatewayParameters

### 03-agent-gateway.yaml
- **Purpose**: Deploys Agent Gateway control plane
- **Source**: oci://ghcr.io/kgateway-dev/charts/agentgateway (v2.2.0-main)
- **Namespace**: agentgateway-system
- **Replicas**: 2 (HA)
- **Resources**: 
  - Requests: 500m CPU, 1Gi memory
  - Limits: 2000m CPU, 4Gi memory

### 04-agent-gateway-observability.yaml
- **Purpose**: Configures OpenTelemetry tracing to Jaeger
- **Source**: gitops/agent-gateway-observability/
- **Resources**: AgentgatewayBackend (Jaeger), AgentgatewayPolicy (tracing)

## Configuration

### Jaeger Integration
- **Endpoint**: jaeger.jaeger.svc.cluster.local:4317
- **Protocol**: gRPC (OTLP)
- **Namespace**: jaeger

### Prometheus Metrics
- **Port**: 9092
- **Path**: /metrics
- **Scrape**: Enabled via pod annotation

## Troubleshooting

### Agent Gateway pod not ready
```bash
# Check logs
kubectl logs -n agentgateway-system -l app.kubernetes.io/name=agentgateway

# Check if CRDs are installed
kubectl get crd | grep gateway
```

### ArgoCD sync issues
```bash
# Check application status
kubectl describe application agent-gateway -n argocd

# Force sync
kubectl patch application agent-gateway -n argocd --type merge -p '{"operation":{"sync":{"revision":"HEAD"}}}'
```

### Observability not working
```bash
# Check if Jaeger is running
kubectl get pods -n jaeger

# Test connectivity
kubectl run test-jaeger --rm -it --image=busybox -- nc -zv jaeger.jaeger.svc.cluster.local 4317
```

## References

- [Agent Gateway Docs](https://agentgateway.dev/docs/kubernetes/latest/)
- [Gateway API Docs](https://gateway-api.sigs.k8s.io/)
- [OpenTelemetry Tracing](https://agentgateway.dev/docs/kubernetes/latest/observability/tracing/)
