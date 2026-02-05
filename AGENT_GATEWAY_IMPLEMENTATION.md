# Agent Gateway Implementation Guide

## Overview

This guide provides step-by-step instructions to implement **Agent Gateway** for securing, connecting, and observing agent-to-agent and agent-to-tool communication in your EKS cluster.

**What You'll Achieve:**
- ✅ Secure agent-to-tool communication with JWT authentication and MCP authorization
- ✅ Enable agent-to-agent communication with A2A protocol
- ✅ Full observability with existing Prometheus, Grafana, and Jaeger
- ✅ Rate limiting, retries, and timeouts for resiliency
- ✅ Centralized policy enforcement

---

## Prerequisites

### Already Installed in Your Cluster:
- ✅ EKS Cluster (dev)
- ✅ KAgent with weather-agent-v6
- ✅ MCP Server (agent-core-mcp) with Agent Core capabilities
- ✅ Prometheus (for metrics)
- ✅ Grafana (for dashboards)
- ✅ Jaeger (for distributed tracing)

### What You Need:
- kubectl access to the cluster
- Helm 3.x installed
- Git access to this repository

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         EKS Cluster                             │
│                                                                 │
│  ┌──────────────┐         ┌──────────────┐                     │
│  │ Weather      │         │ Planning     │                     │
│  │ Agent        │◄────────┤ Agent        │                     │
│  │ (KAgent)     │  A2A    │ (KAgent)     │                     │
│  └──────┬───────┘         └──────┬───────┘                     │
│         │ MCP                    │ MCP                          │
│         │ JWT Token              │ JWT Token                    │
│         ↓                        ↓                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Agent Gateway                                │  │
│  │  • JWT Authentication (K8s ServiceAccount)                │  │
│  │  • MCP Authorization (RBAC)                               │  │
│  │  • Rate Limiting & Timeouts                               │  │
│  │  • OpenTelemetry Export                                   │  │
│  └──────┬───────────────────────────────────────────────────┘  │
│         │                                                       │
│         ↓                                                       │
│  ┌─────────────┐                                               │
│  │ MCP Server  │                                               │
│  │ (Agent Core)│                                               │
│  │ - Browser   │                                               │
│  │ - Code Int. │                                               │
│  │ - Memory    │                                               │
│  └─────────────┘                                               │
│         │                                                       │
│         ↓ (observability data)                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Prometheus  │  Grafana  │  Jaeger                         │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Step 1: Install Agent Gateway

### 1.1 Add Helm Repository

```bash
helm repo add agentgateway https://agentgateway.dev/charts
helm repo update
```

### 1.2 Create Namespace

```bash
kubectl create namespace agent-gateway
```

### 1.3 Install Agent Gateway with Observability

```bash
helm install agent-gateway agentgateway/agentgateway \
  --namespace agent-gateway \
  --set observability.enabled=true \
  --set observability.opentelemetry.enabled=true \
  --set observability.prometheus.enabled=true \
  --set observability.prometheus.port=9090 \
  --set security.jwt.enabled=true \
  --set security.mcp.enabled=true
```

### 1.4 Verify Installation

```bash
# Check pods
kubectl get pods -n agent-gateway

# Expected output:
# NAME                              READY   STATUS    RESTARTS   AGE
# agent-gateway-xxxxxxxxxx-xxxxx    1/1     Running   0          30s

# Check service
kubectl get svc -n agent-gateway

# Expected output:
# NAME            TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)             AGE
# agent-gateway   ClusterIP   10.100.x.x      <none>        8080/TCP,9090/TCP   30s
```

---

## Step 2: Configure RBAC for JWT Validation

Agent Gateway needs permission to validate Kubernetes ServiceAccount tokens.

### 2.1 Create ClusterRole

```bash
kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: agent-gateway-token-reviewer
rules:
- apiGroups: ["authentication.k8s.io"]
  resources: ["tokenreviews"]
  verbs: ["create"]
- apiGroups: [""]
  resources: ["serviceaccounts"]
  verbs: ["get", "list"]
EOF
```

### 2.2 Create ClusterRoleBinding

```bash
kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: agent-gateway-token-reviewer
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: agent-gateway-token-reviewer
subjects:
- kind: ServiceAccount
  name: agent-gateway
  namespace: agent-gateway
EOF
```

---

## Step 3: Configure Agent Gateway

### 3.1 Create Agent Gateway Configuration

Create `agent-gateway/config.yaml`:

```bash
mkdir -p agent-gateway
cat > agent-gateway/config.yaml <<'EOF'
# Agent Gateway Configuration
apiVersion: v1
kind: ConfigMap
metadata:
  name: agent-gateway-config
  namespace: agent-gateway
data:
  gateway.yaml: |
    # Binds define ports and listeners
    binds:
      - port: 8080
        listeners:
          # Agent-to-Tool (MCP) Routes
          - name: mcp-listener
            routes:
              - name: agent-to-mcp-tools
                match:
                  path:
                    prefix: /mcp
                policies:
                  # JWT Authentication
                  - type: jwt-authn
                    jwt:
                      issuer: https://kubernetes.default.svc
                      audiences:
                        - agent-gateway
                      jwksUri: https://kubernetes.default.svc/openid/v1/jwks
                      claimToHeaders:
                        - claim: sub
                          header: x-agent-identity
                  
                  # MCP Authorization
                  - type: mcp-authz
                    mcp:
                      rules:
                        # Weather agent can use specific tools
                        - principal: "system:serviceaccount:agent-core-infra:ekspoc-v6-kagent-agent-sa"
                          allowedTools:
                            - get_weather_data
                            - generate_analysis_code
                            - execute_code
                            - store_user_preferences
                            - get_activity_preferences
                            - store_activity_plan
                          rateLimit:
                            requestsPerMinute: 100
                  
                  # Rate Limiting
                  - type: rate-limit
                    rateLimit:
                      descriptors:
                        - key: tool-name
                          value: execute_code
                          rateLimit:
                            requestsPerMinute: 10
                  
                  # Timeouts (browser tasks need 300s)
                  - type: timeout
                    timeout:
                      request: 300s
                      idle: 60s
                  
                  # Retries
                  - type: retry
                    retry:
                      attempts: 3
                      perTryTimeout: 30s
                      retryOn:
                        - 5xx
                        - reset
                        - connect-failure
                      backoff:
                        baseInterval: 1s
                        maxInterval: 10s
                
                backends:
                  - name: agent-core-mcp-backend
                    type: mcp-http
                    address: http://agent-core-mcp-service.agent-core-infra.svc.cluster.local:8000
                    mcp:
                      endpoint: /mcp
                      protocol: http
                      timeout: 300s
          
          # Agent-to-Agent (A2A) Routes
          - name: a2a-listener
            routes:
              - name: agent-to-agent
                match:
                  path:
                    prefix: /agents
                policies:
                  # JWT Authentication
                  - type: jwt-authn
                    jwt:
                      issuer: https://kubernetes.default.svc
                      audiences:
                        - agent-gateway
                      jwksUri: https://kubernetes.default.svc/openid/v1/jwks
                  
                  # A2A Authorization
                  - type: a2a-authz
                    a2a:
                      rules:
                        # Planning agent can call weather agent
                        - source: "system:serviceaccount:agent-core-infra:planning-agent-sa"
                          target: weather-agent-v6
                          allowed: true
                        
                        # Orchestrator can call any agent
                        - source: "system:serviceaccount:agent-core-infra:orchestrator-agent-sa"
                          target: "*"
                          allowed: true
                  
                  # Timeout
                  - type: timeout
                    timeout:
                      request: 60s
                
                backends:
                  - name: weather-agent-backend
                    address: http://weather-agent-service.agent-core-infra.svc.cluster.local:8080
                  - name: planning-agent-backend
                    address: http://planning-agent-service.agent-core-infra.svc.cluster.local:8080
    
    # Observability Configuration
    observability:
      # OpenTelemetry for distributed tracing
      opentelemetry:
        enabled: true
        # Export to existing Jaeger
        endpoint: http://jaeger-collector.observability.svc.cluster.local:4317
        protocol: grpc
        tracing:
          enabled: true
          samplingRate: 1.0
          attributes:
            - key: agent.identity
              value: ${jwt.sub}
            - key: tool.name
              value: ${mcp.tool}
            - key: gateway.version
              value: "0.11"
      
      # Prometheus metrics
      prometheus:
        enabled: true
        port: 9090
        path: /metrics
        metrics:
          - agent_requests_total
          - agent_request_duration_seconds
          - tool_invocations_total
          - tool_invocation_duration_seconds
          - mcp_errors_total
          - a2a_calls_total
      
      # MCP-specific observability
      mcp:
        enabled: true
        metrics:
          - mcp_tool_calls_total
          - mcp_tool_call_duration
          - mcp_tool_errors
          - mcp_discovery_requests
EOF
```

### 3.2 Apply Configuration

```bash
kubectl apply -f agent-gateway/config.yaml
```

### 3.3 Restart Agent Gateway

```bash
kubectl rollout restart deployment agent-gateway -n agent-gateway
kubectl rollout status deployment agent-gateway -n agent-gateway
```

---

## Step 4: Configure Observability Integration

### 4.1 Configure Prometheus to Scrape Agent Gateway

```bash
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-agent-gateway-scrape
  namespace: observability
data:
  agent-gateway-scrape.yml: |
    - job_name: 'agent-gateway'
      kubernetes_sd_configs:
        - role: pod
          namespaces:
            names:
              - agent-gateway
      relabel_configs:
        - source_labels: [__meta_kubernetes_pod_label_app]
          action: keep
          regex: agent-gateway
        - source_labels: [__meta_kubernetes_pod_name]
          target_label: pod
        - source_labels: [__meta_kubernetes_namespace]
          target_label: namespace
      metrics_path: /metrics
      scrape_interval: 15s
EOF
```

### 4.2 Update Prometheus Configuration

```bash
# Add the scrape config to your existing Prometheus
kubectl edit configmap prometheus-server -n observability

# Add the content from agent-gateway-scrape.yml to the scrape_configs section
```

### 4.3 Verify Prometheus is Scraping

```bash
# Port forward Prometheus
kubectl port-forward -n observability svc/prometheus-server 9090:80

# Open browser: http://localhost:9090
# Go to Status > Targets
# Verify "agent-gateway" target is UP
```

### 4.4 Configure Grafana Dashboard

```bash
# Port forward Grafana
kubectl port-forward -n observability svc/grafana 3000:80

# Open browser: http://localhost:3000
# Login with your credentials

# Import Agent Gateway dashboard:
# 1. Click "+" > Import
# 2. Use dashboard ID: (create custom or use provided JSON)
# 3. Select Prometheus datasource
```

Create custom dashboard JSON:

```bash
cat > agent-gateway/grafana-dashboard.json <<'EOF'
{
  "dashboard": {
    "title": "Agent Gateway Metrics",
    "panels": [
      {
        "title": "Agent Requests Total",
        "targets": [
          {
            "expr": "rate(agent_requests_total[5m])",
            "legendFormat": "{{agent_identity}}"
          }
        ]
      },
      {
        "title": "Tool Invocations",
        "targets": [
          {
            "expr": "rate(tool_invocations_total[5m])",
            "legendFormat": "{{tool_name}}"
          }
        ]
      },
      {
        "title": "Request Duration",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(agent_request_duration_seconds_bucket[5m]))",
            "legendFormat": "p95"
          }
        ]
      },
      {
        "title": "MCP Errors",
        "targets": [
          {
            "expr": "rate(mcp_errors_total[5m])",
            "legendFormat": "{{error_type}}"
          }
        ]
      }
    ]
  }
}
EOF
```

### 4.5 Verify Jaeger Integration

```bash
# Port forward Jaeger
kubectl port-forward -n observability svc/jaeger-query 16686:16686

# Open browser: http://localhost:16686
# Select service: "agent-gateway"
# You should see traces for agent-to-tool and agent-to-agent calls
```

---

## Step 5: Update KAgent to Use Agent Gateway

### 5.1 Update Weather Agent Configuration

Edit `gitops/agent-core-stack/templates/kagent-agent.yaml`:

```yaml
{{- if .Values.kagent.enabled }}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ .Values.projectName }}-agent-sa
  namespace: {{ .Values.namespace }}
  annotations:
    argocd.argoproj.io/sync-wave: "3"
---
apiVersion: kagent.dev/v1alpha2
kind: Agent
metadata:
  name: weather-agent-{{ .Values.version }}
  namespace: {{ .Values.namespace }}
  annotations:
    argocd.argoproj.io/sync-wave: "3"
spec:
  type: Declarative
  description: "Weather-Based Activity Planning Assistant with memory"
  serviceAccountName: {{ .Values.projectName }}-agent-sa
  
  declarative:
    modelConfig: bedrock-anthropic-claude-3-5-sonnet
    stream: true
    
    systemMessage: |
      You are a Weather-Based Activity Planning Assistant with memory.
      
      When a user asks about activities for a location:
      1. Extract city from query
      2. Call get_activity_preferences() to check if user has stored preferences
      3. If user mentions preferences in their query (e.g., "I like hiking"), call store_user_preferences() to save them
      4. Call get_weather_data(city) to get weather forecast
      5. Call generate_analysis_code(weather_data) to create classification code
      6. Call execute_code(python_code) to classify weather days
      7. Generate personalized activity recommendations based on weather and preferences
      8. Call store_activity_plan(city, plan) to save the plan in memory for future reference
      
      Memory stores user preferences across sessions. Always check memory first and save new preferences/plans.
    
    tools:
      - type: McpServer
        mcpServer:
          apiGroup: kagent.dev
          kind: RemoteMCPServer
          name: agent-core-tools-{{ .Values.version }}
          # Route through Agent Gateway
          endpoint: http://agent-gateway.agent-gateway.svc.cluster.local:8080/mcp
          authentication:
            type: serviceAccount
          headers:
            - name: x-agent-framework
              value: kagent
{{- end }}
```

### 5.2 Commit and Push Changes

```bash
git add gitops/agent-core-stack/templates/kagent-agent.yaml
git commit -m "Route KAgent through Agent Gateway"
git push
```

### 5.3 Wait for ArgoCD Sync

```bash
# Monitor ArgoCD sync
kubectl get application agent-core-stack -n argocd -w

# Or force sync
kubectl patch application agent-core-stack -n argocd \
  --type merge -p '{"operation":{"sync":{"revision":"HEAD"}}}'
```

---

## Step 6: Test Agent-to-Tool Communication

### 6.1 Get ServiceAccount Token

```bash
TOKEN=$(kubectl create token ekspoc-v6-kagent-agent-sa -n agent-core-infra --duration=1h)
echo $TOKEN
```

### 6.2 Test Tool Call Through Gateway

```bash
kubectl run test-client --rm -it --image=curlimages/curl --restart=Never -- sh

# Inside the pod:
curl -X POST http://agent-gateway.agent-gateway.svc.cluster.local:8080/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "get_weather_data",
      "arguments": {"city": "Tampa, FL"}
    },
    "id": 1
  }'
```

### 6.3 Verify in Jaeger

```bash
# Open Jaeger UI
kubectl port-forward -n observability svc/jaeger-query 16686:16686

# Open: http://localhost:16686
# Service: agent-gateway
# Operation: POST /mcp
# You should see the full trace including MCP server call
```

### 6.4 Verify in Prometheus

```bash
# Open Prometheus UI
kubectl port-forward -n observability svc/prometheus-server 9090:80

# Query: agent_requests_total{agent_identity="system:serviceaccount:agent-core-infra:ekspoc-v6-kagent-agent-sa"}
# You should see request count incrementing
```

---

## Step 7: Implement Agent-to-Agent Communication (Example)

### 7.1 Create Planning Agent

Create `agent-gateway/planning-agent.yaml`:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: planning-agent-sa
  namespace: agent-core-infra
---
apiVersion: kagent.dev/v1alpha2
kind: Agent
metadata:
  name: planning-agent
  namespace: agent-core-infra
spec:
  type: Declarative
  description: "Trip Planning Orchestrator"
  serviceAccountName: planning-agent-sa
  
  declarative:
    modelConfig: bedrock-anthropic-claude-3-5-sonnet
    stream: true
    
    systemMessage: |
      You are a Trip Planning Orchestrator that coordinates with specialized agents.
      
      Available agents:
      - weather-agent: Get weather forecasts and activity recommendations
      - booking-agent: Book hotels and flights (not implemented yet)
      
      When a user asks about trip planning:
      1. Call weather-agent to get weather-based activity recommendations
      2. Call booking-agent to find accommodations
      3. Combine results into a comprehensive trip plan
    
    # Agent-to-agent calls via Agent Gateway
    agents:
      - name: weather-agent
        endpoint: http://agent-gateway.agent-gateway.svc.cluster.local:8080/agents/weather-agent-v6
        protocol: a2a
        authentication:
          type: serviceAccount
        capabilities:
          - weather_forecast
          - activity_planning
---
apiVersion: v1
kind: Service
metadata:
  name: planning-agent-service
  namespace: agent-core-infra
spec:
  selector:
    app: planning-agent
  ports:
    - port: 8080
      targetPort: 8080
```

### 7.2 Deploy Planning Agent

```bash
kubectl apply -f agent-gateway/planning-agent.yaml
```

### 7.3 Test Agent-to-Agent Communication

```bash
# Get planning agent token
PLANNING_TOKEN=$(kubectl create token planning-agent-sa -n agent-core-infra --duration=1h)

# Call planning agent which will call weather agent through gateway
kubectl run test-a2a --rm -it --image=curlimages/curl --restart=Never -- sh

# Inside pod:
curl -X POST http://agent-gateway.agent-gateway.svc.cluster.local:8080/agents/weather-agent-v6 \
  -H "Authorization: Bearer $PLANNING_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Get weather forecast for Tampa, FL this weekend"
  }'
```

### 7.4 Verify A2A in Jaeger

```bash
# Open Jaeger UI
# Service: agent-gateway
# Operation: POST /agents/weather-agent-v6
# You should see trace showing: planning-agent → gateway → weather-agent
```

---

## Step 8: Monitor and Verify

### 8.1 Check Agent Gateway Logs

```bash
kubectl logs -n agent-gateway -l app=agent-gateway --tail=100 -f
```

### 8.2 Check Metrics in Prometheus

```bash
# Port forward
kubectl port-forward -n observability svc/prometheus-server 9090:80

# Useful queries:
# 1. Total requests per agent
agent_requests_total

# 2. Tool invocation rate
rate(tool_invocations_total[5m])

# 3. Request duration p95
histogram_quantile(0.95, rate(agent_request_duration_seconds_bucket[5m]))

# 4. Error rate
rate(mcp_errors_total[5m])

# 5. A2A calls
rate(a2a_calls_total[5m])
```

### 8.3 View Traces in Jaeger

```bash
# Port forward
kubectl port-forward -n observability svc/jaeger-query 16686:16686

# Open: http://localhost:16686
# Service: agent-gateway
# Look for traces showing full workflow:
#   KAgent → Gateway → MCP Server → Bedrock Agent Core
```

### 8.4 Create Grafana Alerts

```bash
# Example alert for high error rate
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-alerts
  namespace: observability
data:
  alerts.yaml: |
    groups:
      - name: agent-gateway
        interval: 30s
        rules:
          - alert: HighErrorRate
            expr: rate(mcp_errors_total[5m]) > 0.1
            for: 5m
            labels:
              severity: warning
            annotations:
              summary: "High error rate in Agent Gateway"
              description: "Error rate is {{ $value }} errors/sec"
          
          - alert: HighLatency
            expr: histogram_quantile(0.95, rate(agent_request_duration_seconds_bucket[5m])) > 10
            for: 5m
            labels:
              severity: warning
            annotations:
              summary: "High latency in Agent Gateway"
              description: "P95 latency is {{ $value }} seconds"
EOF
```

---

## Step 9: Troubleshooting

### 9.1 Agent Gateway Not Starting

```bash
# Check logs
kubectl logs -n agent-gateway -l app=agent-gateway

# Check configuration
kubectl describe configmap agent-gateway-config -n agent-gateway

# Verify RBAC
kubectl auth can-i create tokenreviews --as=system:serviceaccount:agent-gateway:agent-gateway
```

### 9.2 JWT Authentication Failing

```bash
# Test token validation manually
TOKEN=$(kubectl create token ekspoc-v6-kagent-agent-sa -n agent-core-infra)

# Decode token
echo $TOKEN | cut -d'.' -f2 | base64 -d | jq

# Verify issuer and audience match gateway config
```

### 9.3 MCP Authorization Denied

```bash
# Check gateway logs for authorization errors
kubectl logs -n agent-gateway -l app=agent-gateway | grep "authz"

# Verify principal matches ServiceAccount format:
# system:serviceaccount:<namespace>:<serviceaccount-name>
```

### 9.4 Observability Data Not Appearing

```bash
# Check OpenTelemetry endpoint
kubectl get svc -n observability | grep jaeger

# Verify Prometheus scraping
kubectl logs -n observability -l app=prometheus

# Check gateway metrics endpoint
kubectl port-forward -n agent-gateway svc/agent-gateway 9090:9090
curl http://localhost:9090/metrics
```

---

## Step 10: Production Considerations

### 10.1 Enable mTLS

```yaml
# Add to gateway config
security:
  mtls:
    enabled: true
    mode: STRICT
    certificateAuthority: /etc/certs/ca.crt
    serverCert: /etc/certs/tls.crt
    serverKey: /etc/certs/tls.key
```

### 10.2 Configure Resource Limits

```bash
kubectl apply -f - <<EOF
apiVersion: v1
kind: ResourceQuota
metadata:
  name: agent-gateway-quota
  namespace: agent-gateway
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "8"
    limits.memory: 16Gi
EOF
```

### 10.3 Enable Horizontal Pod Autoscaling

```bash
kubectl autoscale deployment agent-gateway \
  -n agent-gateway \
  --cpu-percent=70 \
  --min=2 \
  --max=10
```

### 10.4 Configure Network Policies

```bash
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: agent-gateway-policy
  namespace: agent-gateway
spec:
  podSelector:
    matchLabels:
      app: agent-gateway
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: agent-core-infra
    ports:
    - protocol: TCP
      port: 8080
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: agent-core-infra
    ports:
    - protocol: TCP
      port: 8000
  - to:
    - namespaceSelector:
        matchLabels:
          name: observability
    ports:
    - protocol: TCP
      port: 4317
EOF
```

---

## Summary

You have successfully implemented Agent Gateway with:

✅ **Security**: JWT authentication and MCP authorization  
✅ **Connectivity**: Agent-to-tool (MCP) and agent-to-agent (A2A)  
✅ **Observability**: Prometheus metrics, Grafana dashboards, Jaeger traces  
✅ **Resiliency**: Rate limiting, retries, timeouts  
✅ **Governance**: Centralized policy enforcement

### Key Endpoints:
- **Agent Gateway**: `http://agent-gateway.agent-gateway.svc.cluster.local:8080`
- **MCP Tools**: `http://agent-gateway.agent-gateway.svc.cluster.local:8080/mcp`
- **A2A Agents**: `http://agent-gateway.agent-gateway.svc.cluster.local:8080/agents/<agent-name>`
- **Metrics**: `http://agent-gateway.agent-gateway.svc.cluster.local:9090/metrics`

### Next Steps:
1. Add more agents for multi-agent orchestration
2. Implement custom authorization policies
3. Set up alerting rules in Grafana
4. Enable mTLS for production
5. Configure backup and disaster recovery

---

## Support

For issues or questions:
- Agent Gateway Docs: https://agentgateway.dev/docs
- GitHub Issues: https://github.com/agentgateway/agentgateway/issues
- Discord: https://discord.gg/BdJpzaPjHv
