# Agent Core MCP Server

FastMCP server exposing Agent Core capabilities (Memory, Browser, Code Interpreter) as 6 MCP tools.

## Tools

1. **store_memory** - Store information in Agent Core Memory
2. **retrieve_memory** - Retrieve information from Agent Core Memory
3. **browse_web** - Browse web and extract data using Agent Core Browser
4. **extract_data** - Extract specific data from a webpage
5. **execute_python** - Execute Python code using Agent Core Code Interpreter
6. **execute_code** - Execute code in specified language

## Build Image

```bash
# Build
podman build -t agent-core-mcp:latest .

# Tag for ECR
podman tag agent-core-mcp:latest 940019131157.dkr.ecr.us-east-1.amazonaws.com/agent-core-mcp:latest

# Login to ECR
aws ecr get-login-password --region us-east-1 | podman login --username AWS --password-stdin 940019131157.dkr.ecr.us-east-1.amazonaws.com

# Create ECR repository (first time only)
aws ecr create-repository --repository-name agent-core-mcp --region us-east-1

# Push
podman push 940019131157.dkr.ecr.us-east-1.amazonaws.com/agent-core-mcp:latest
```

## Environment Variables

- `MEMORY_ID` - Agent Core Memory ID (from Terraform)
- `BROWSER_ID` - Agent Core Browser ID (from Terraform)
- `CODE_INTERPRETER_ID` - Code Interpreter ID (from Terraform)
- `AWS_REGION` - AWS region (default: us-west-2)

## Local Testing

```bash
# Set environment variables
export MEMORY_ID=your-memory-id
export BROWSER_ID=your-browser-id
export CODE_INTERPRETER_ID=your-code-interpreter-id
export AWS_REGION=us-west-2

# Run server
python -m fastmcp run server:mcp --host 0.0.0.0 --port 8080

# Test tool
curl -X POST http://localhost:8080/mcp/tools/store_memory \
  -H "Content-Type: application/json" \
  -d '{"content": "User prefers outdoor activities", "actor_id": "user", "session_id": "test"}'
```

## Deployment

Deployed automatically via ArgoCD as Wave 1 after Terraform (Wave 0) completes.

```bash
# Check deployment
kubectl get pods -n agent-core-infra -l app=agent-core-mcp-v6-kagent

# Check logs
kubectl logs -n agent-core-infra -l app=agent-core-mcp-v6-kagent

# Test from within cluster
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl -X POST http://agent-core-mcp-v6-kagent:8080/mcp/tools/store_memory \
  -H "Content-Type: application/json" \
  -d '{"content": "Test memory"}'
```
