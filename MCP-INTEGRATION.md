# Agent Core MCP Integration

Deploy Agent Core capabilities (Memory, Browser, Code Interpreter) as MCP Tools for KAgent.

## Architecture

```
Wave 0: Terraform → Provisions Agent Core resources
Wave 1: MCP Server → Exposes 6 tools via FastMCP
Wave 2: RemoteMCPServer CRD → Registers tools with KAgent
Wave 3: Agent CRD → Declarative agent with auto-discovered tools
```

## The 6 MCP Tools

1. **get_weather_data(city)** - Browser automation for weather.gov
2. **generate_analysis_code(weather_data)** - Generate Python classification code
3. **execute_code(python_code)** - Execute code via Code Interpreter
4. **store_user_preferences(preferences)** - Store preferences in Memory
5. **get_activity_preferences()** - Retrieve preferences from Memory
6. **store_activity_plan(city, plan)** - Store plan in Memory

## Prerequisites

1. **EKS Cluster**: machine-learning (us-west-2)
2. **KAgent Operator**: Installed
3. **ArgoCD**: For GitOps
4. **Flux + Tofu Controller**: For Terraform automation
5. **Pod Identity Addon**: For IAM authentication

## Deployment

### 1. Build MCP Server Image

```bash
cd mcp-server
podman build -t agent-core-mcp:latest .
podman tag agent-core-mcp:latest 940019131157.dkr.ecr.us-east-1.amazonaws.com/agent-core-mcp:latest

aws ecr create-repository --repository-name agent-core-mcp --region us-east-1
aws ecr get-login-password --region us-east-1 | podman login --username AWS --password-stdin 940019131157.dkr.ecr.us-east-1.amazonaws.com

podman push 940019131157.dkr.ecr.us-east-1.amazonaws.com/agent-core-mcp:latest
```

### 2. Configure

Edit `values.yaml`:

```yaml
version: v6-kagent
projectName: ekspoc-v6-kagent
awsRegion: us-west-2
eksClusterName: machine-learning

capabilities:
  memory: true
  browser: true
  codeInterpreter: true

mcpServer:
  image:
    repository: 940019131157.dkr.ecr.us-east-1.amazonaws.com/agent-core-mcp
    tag: latest

kagent:
  enabled: true
```

### 3. Deploy via ArgoCD

```bash
git add .
git commit -m "Deploy MCP integration"
git push

kubectl apply -f argocd/agent-core-stack.yaml
```

### 4. Monitor

```bash
# Wave 0: Terraform (~3 min)
kubectl get terraform agent-core-components-v6-kagent -n agent-core-infra -w

# Wave 1: MCP Server (~30 sec)
kubectl get pods -n agent-core-infra -l app=agent-core-mcp-v6-kagent -w

# Wave 2: RemoteMCPServer
kubectl get remotemcpserver agent-core-tools-v6-kagent -n agent-core-infra

# Wave 3: Agent
kubectl get agent weather-agent-v6-kagent -n agent-core-infra
```

## Agent Configuration

```yaml
apiVersion: kagent.amazon.com/v1alpha2
kind: Agent
spec:
  type: Declarative
  declarative:
    modelConfig: bedrock-anthropic-claude-3-5-sonnet
    systemMessage: |
      You are a Weather-Based Activity Planning Assistant.
      [Workflow instructions]
    tools:
      - type: McpServer
        mcpServer:
          kind: RemoteMCPServer
          name: agent-core-tools-v6-kagent
          toolNames: []  # Auto-discover all tools
```

## Testing

```bash
kubectl exec -it -n agent-core-infra deployment/weather-agent-v6-kagent -- python -c "
from kagent import invoke_agent
result = invoke_agent(
    agent_name='weather-agent-v6-kagent',
    input='What should I do this weekend in Tampa, FL?'
)
print(result)
"
```

## Verification

```bash
# Check Terraform
kubectl get terraform agent-core-components-v6-kagent -n agent-core-infra
# Expected: READY=True

# Check MCP Server
kubectl get pods -n agent-core-infra -l app=agent-core-mcp-v6-kagent
# Expected: Running

# Check RemoteMCPServer
kubectl get remotemcpserver agent-core-tools-v6-kagent -n agent-core-infra -o yaml

# Check Agent
kubectl get agent weather-agent-v6-kagent -n agent-core-infra -o yaml
```

## Files

```
agent-core-pocs/
├── mcp-server/
│   ├── server.py              # FastMCP server with 6 tools
│   ├── Dockerfile
│   └── requirements.txt
├── gitops/agent-core-stack/templates/
│   ├── terraform-resource.yaml    # Wave 0
│   ├── mcp-server.yaml            # Wave 1
│   ├── remote-mcp-server.yaml     # Wave 2
│   └── kagent-agent.yaml          # Wave 3
├── examples/
│   ├── agent.yaml             # Standalone agent example
│   └── README.md
├── values.yaml                # Configuration
└── MCP-INTEGRATION.md         # This file
```

## Key Features

- **Auto-discovery**: `toolNames: []` loads all tools automatically
- **Declarative**: Zero Python code needed for agent
- **GitOps**: Full ArgoCD automation
- **4-wave deployment**: Proper ordering with sync waves
- **Pod Identity**: Secure IAM authentication

## Troubleshooting

### MCP Server Not Starting
```bash
kubectl logs -n agent-core-infra -l app=agent-core-mcp-v6-kagent
kubectl get secret agent-core-outputs-v6-kagent -n agent-core-infra
```

### Agent Not Finding Tools
```bash
kubectl get remotemcpserver agent-core-tools-v6-kagent -n agent-core-infra -o yaml
kubectl logs -n kagent-system -l app=kagent-operator
```

### Terraform Issues
```bash
kubectl logs -n flux-system -l app.kubernetes.io/name=tf-controller
kubectl describe terraform agent-core-components-v6-kagent -n agent-core-infra
```

## Cleanup

```bash
kubectl delete application agent-core-stack -n argocd
# Terraform automatically deletes all AWS resources
```
