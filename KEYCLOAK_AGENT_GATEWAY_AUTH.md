# Keycloak Authentication with Agent Gateway

## Overview
Integrate Keycloak as the identity provider for Agent Gateway to enable JWT-based authentication and authorization for agent-to-tool communication.

---

## Prerequisites

- EKS cluster with Agent Gateway installed
- kubectl access
- Helm 3.x

---

## Step 1: Deploy Keycloak

```bash
# Add Bitnami Helm repo
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Create namespace
kubectl create namespace keycloak

# Install Keycloak
helm install keycloak bitnami/keycloak \
  --namespace keycloak \
  --set auth.adminUser=admin \
  --set auth.adminPassword=admin \
  --set service.type=LoadBalancer \
  --set postgresql.enabled=true

# Wait for ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=keycloak -n keycloak --timeout=300s

# Get Keycloak URL
export KEYCLOAK_URL=$(kubectl get svc keycloak -n keycloak -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "Keycloak URL: http://$KEYCLOAK_URL"
```

---

## Step 2: Configure Keycloak Realm and Client

### Access Keycloak Admin Console
```bash
# Port-forward if LoadBalancer not available
kubectl port-forward svc/keycloak -n keycloak 8080:80

# Open: http://localhost:8080
# Login: admin / admin
```

### Create Realm
1. Click **Master** dropdown → **Create Realm**
2. Name: `agent-gateway`
3. Click **Create**

### Create Client
1. Go to **Clients** → **Create client**
2. **Client ID**: `agent-gateway-client`
3. **Client authentication**: ON
4. **Authorization**: ON
5. **Valid redirect URIs**: `*`
6. **Web origins**: `*`
7. Click **Save**

### Get Client Secret
1. Go to **Clients** → `agent-gateway-client` → **Credentials** tab
2. Copy **Client Secret**

### Create Service Account User
1. Go to **Clients** → `agent-gateway-client` → **Service account roles** tab
2. Verify service account is enabled

### Get JWKS Endpoint
```bash
# Format: http://<KEYCLOAK_URL>/realms/agent-gateway/protocol/openid-connect/certs
echo "JWKS URL: http://$KEYCLOAK_URL/realms/agent-gateway/protocol/openid-connect/certs"
```

---

## Step 3: Create Keycloak Backend in Agent Gateway

```yaml
# gitops/agent-gateway-config/keycloak-backend.yaml
apiVersion: agentgateway.kgateway.dev/v1alpha1
kind: AgentgatewayBackend
metadata:
  name: keycloak-backend
  namespace: agentgateway-system
spec:
  static:
    host: keycloak.keycloak.svc.cluster.local
    port: 80
```

---

## Step 4: Create JWT Authentication Policy

```yaml
# gitops/agent-gateway-config/keycloak-jwt-auth-policy.yaml
apiVersion: agentgateway.kgateway.dev/v1alpha1
kind: AgentgatewayPolicy
metadata:
  name: keycloak-jwt-auth
  namespace: agentgateway-system
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: agent-gateway-proxy
  traffic:
    jwtAuthentication:
      providers:
        - name: keycloak
          issuer: "http://keycloak.keycloak.svc.cluster.local/realms/agent-gateway"
          jwks:
            remote:
              url: "http://keycloak.keycloak.svc.cluster.local/realms/agent-gateway/protocol/openid-connect/certs"
              backend:
                name: keycloak-backend
          claimsToHeaders:
            - claim: sub
              header: X-User-Id
            - claim: preferred_username
              header: X-Username
```

---

## Step 5: Update RemoteMCPServer to Use JWT Token

```yaml
# gitops/agent-core-stack/templates/remote-mcp-server.yaml
apiVersion: kagent.dev/v1alpha2
kind: RemoteMCPServer
metadata:
  name: agent-core-tools-{{ .Values.version }}
  namespace: {{ .Values.namespace }}
spec:
  url: http://agent-gateway-proxy.agentgateway-system.svc.cluster.local:8080/mcp
  description: "Agent Core capabilities: Memory, Browser, Code Interpreter"
  protocol: STREAMABLE_HTTP
  timeout: 30s
  headersFrom:
    - name: Authorization
      value: "Bearer "
      valueFrom:
        type: Secret
        name: keycloak-token
        key: token
```

---

## Step 6: Create Keycloak Token Secret

### Get Token from Keycloak
```bash
# Get access token using client credentials
export KEYCLOAK_URL=$(kubectl get svc keycloak -n keycloak -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

TOKEN=$(curl -X POST "http://$KEYCLOAK_URL/realms/agent-gateway/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=agent-gateway-client" \
  -d "client_secret=<YOUR_CLIENT_SECRET>" \
  | jq -r '.access_token')

echo $TOKEN
```

### Create Secret
```bash
kubectl create secret generic keycloak-token \
  -n agent-core-infra \
  --from-literal=token="$TOKEN"
```

**Note**: Tokens expire. For production, use a token refresh mechanism or service account with long-lived tokens.

---

## Step 7: Update KAgent Agent

```yaml
# gitops/agent-core-stack/templates/kagent-agent.yaml
spec:
  declarative:
    tools:
      - type: McpServer
        mcpServer:
          apiGroup: kagent.dev
          kind: RemoteMCPServer
          name: agent-core-tools-{{ .Values.version }}
          toolNames: []
          allowedHeaders:
            - Authorization
            - X-User-Id
            - X-Username
```

---

## Step 8: Deploy Configuration

```bash
# Add resources to kustomization
cat >> gitops/agent-gateway-config/kustomization.yaml <<EOF
  - keycloak-backend.yaml
  - keycloak-jwt-auth-policy.yaml
EOF

# Commit and push
git add gitops/agent-gateway-config/
git commit -m "Add Keycloak JWT authentication"
git push

# Sync ArgoCD
kubectl patch application agent-gateway-config -n argocd \
  --type merge -p '{"operation":{"sync":{"revision":"HEAD"}}}'
```

---

## Step 9: Verify

### Check Policy Status
```bash
kubectl get agentgatewaypolicy keycloak-jwt-auth -n agentgateway-system
```

Expected: `ACCEPTED=True`

### Check RemoteMCPServer
```bash
kubectl get remotemcpserver -n agent-core-infra
```

Expected: `ACCEPTED=True`

### Test with Invalid Token
```bash
kubectl run test-curl --rm -i --restart=Never --image=curlimages/curl:latest -- \
  -X POST http://agent-gateway-proxy.agentgateway-system.svc.cluster.local:8080/mcp \
  -H "Authorization: Bearer invalid-token" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

Expected: `401 Unauthorized`

### Test with Valid Token
```bash
kubectl run test-curl --rm -i --restart=Never --image=curlimages/curl:latest -- \
  -X POST http://agent-gateway-proxy.agentgateway-system.svc.cluster.local:8080/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

Expected: `200 OK` with tools list

---

## Token Refresh Strategy (Production)

### Option 1: Init Container with Token Refresh
```yaml
apiVersion: v1
kind: Pod
spec:
  initContainers:
    - name: token-fetcher
      image: curlimages/curl:latest
      command:
        - sh
        - -c
        - |
          TOKEN=$(curl -X POST "http://keycloak.keycloak.svc.cluster.local/realms/agent-gateway/protocol/openid-connect/token" \
            -H "Content-Type: application/x-www-form-urlencoded" \
            -d "grant_type=client_credentials" \
            -d "client_id=agent-gateway-client" \
            -d "client_secret=$CLIENT_SECRET" \
            | jq -r '.access_token')
          echo -n "$TOKEN" > /shared/token
      volumeMounts:
        - name: shared-token
          mountPath: /shared
      env:
        - name: CLIENT_SECRET
          valueFrom:
            secretKeyRef:
              name: keycloak-client-secret
              key: secret
  volumes:
    - name: shared-token
      emptyDir: {}
```

### Option 2: External Token Manager
Deploy a sidecar or separate service that:
1. Fetches tokens from Keycloak
2. Refreshes before expiry
3. Updates Kubernetes Secret
4. KAgent watches Secret for changes

---

## Authorization (Optional)

### Add Role-Based Access Control
```yaml
spec:
  traffic:
    jwtAuthentication:
      providers:
        - name: keycloak
          issuer: "http://keycloak.keycloak.svc.cluster.local/realms/agent-gateway"
          jwks:
            remote:
              url: "http://keycloak.keycloak.svc.cluster.local/realms/agent-gateway/protocol/openid-connect/certs"
              backend:
                name: keycloak-backend
          authorization:
            rules:
              - claim: realm_access.roles
                values:
                  - agent-user
                  - admin
```

### Create Roles in Keycloak
1. Go to **Realm roles** → **Create role**
2. Name: `agent-user`
3. Assign to service account: **Clients** → `agent-gateway-client` → **Service account roles** → **Assign role**

---

## Troubleshooting

### Policy Not Accepted
```bash
kubectl describe agentgatewaypolicy keycloak-jwt-auth -n agentgateway-system
```

### Check Agent Gateway Logs
```bash
kubectl logs -n agentgateway-system -l app.kubernetes.io/name=agentgateway --tail=100
```

### Verify JWKS Endpoint
```bash
curl http://keycloak.keycloak.svc.cluster.local/realms/agent-gateway/protocol/openid-connect/certs
```

### Token Validation Issues
- Ensure issuer matches exactly (including http/https)
- Verify JWKS URL is accessible from Agent Gateway
- Check token hasn't expired: `jwt decode $TOKEN`

---

## Key Differences from Kubernetes API Approach

| Aspect | Kubernetes API | Keycloak |
|--------|---------------|----------|
| **TLS** | Self-signed cert issue | Standard HTTP/HTTPS |
| **JWKS** | Certificate validation fails | Works with backend reference |
| **Token Lifetime** | Short-lived (1h) | Configurable (hours/days) |
| **Token Refresh** | Automatic via SA | Manual or sidecar |
| **Setup Complexity** | Lower | Higher |
| **Production Ready** | No (TLS issue) | Yes |

---

## Summary

**Steps:**
1. Deploy Keycloak (Helm)
2. Create realm + client in Keycloak
3. Create AgentgatewayBackend for Keycloak
4. Create JWT auth policy with JWKS
5. Get token from Keycloak
6. Store token in Secret
7. Update RemoteMCPServer to use token
8. Update KAgent to allow Authorization header
9. Deploy and verify

**Production Considerations:**
- Implement token refresh mechanism
- Use HTTPS for Keycloak (Ingress + cert-manager)
- Add authorization rules based on roles/claims
- Monitor token expiry and renewal
