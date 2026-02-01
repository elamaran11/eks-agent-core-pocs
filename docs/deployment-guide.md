# Agent Core POC Deployment Guide

## Prerequisites

1. **EKS Cluster**: Running cluster named "dev" with kubectl access
2. **AWS CLI**: Configured with appropriate credentials
3. **Docker**: For building container images
4. **GitHub Account**: For FluxCD GitOps
5. **Permissions**: IAM permissions to create Lambda, Bedrock, OpenSearch resources

## Step-by-Step Deployment

### Phase 1: Install FluxCD and Tofu Controller

#### 1.1 Install FluxCD

```bash
cd flux
chmod +x 01-install-flux.sh
./01-install-flux.sh
```

When prompted, provide:
- GitHub username
- Repository name (create a new repo or use existing)
- Personal access token (with repo permissions)

Verify FluxCD installation:
```bash
kubectl get pods -n flux-system
```

#### 1.2 Install Tofu Controller

```bash
kubectl apply -f 02-install-tofu-controller.yaml
```

Wait for Tofu Controller to be ready:
```bash
kubectl wait --for=condition=ready pod -l app=tofu-controller -n tofu-system --timeout=300s
```

### Phase 2: Prepare Lambda Function Code

The Terraform configuration references Lambda function zip files. Create placeholder functions:

#### 2.1 Create Code Interpreter Lambda

```bash
mkdir -p /tmp/code-interpreter
cat > /tmp/code-interpreter/index.py << 'EOF'
import json

def handler(event, context):
    code = event.get('code', '')
    try:
        exec_globals = {}
        exec(code, exec_globals)
        return {'statusCode': 200, 'body': json.dumps({'result': 'success'})}
    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}
EOF

cd /tmp/code-interpreter
zip -r code_interpreter.zip index.py
cp code_interpreter.zip ~/WorkDocsDownloads/AWS_Internal/Containers/Kiro-Projects/agent-core-pocs/terraform/agent-core-components/
```

#### 2.2 Create Browser Lambda

```bash
mkdir -p /tmp/browser
cat > /tmp/browser/index.py << 'EOF'
import json
import urllib.request

def handler(event, context):
    url = event.get('url', '')
    try:
        with urllib.request.urlopen(url) as response:
            content = response.read().decode('utf-8')
        return {'statusCode': 200, 'body': json.dumps({'content': content[:1000]})}
    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}
EOF

cd /tmp/browser
zip -r browser.zip index.py
cp browser.zip ~/WorkDocsDownloads/AWS_Internal/Containers/Kiro-Projects/agent-core-pocs/terraform/agent-core-components/
```

### Phase 3: Configure and Deploy Infrastructure

#### 3.1 Get EKS OIDC Provider

```bash
aws eks describe-cluster --name dev --query "cluster.identity.oidc.issuer" --output text | sed 's|https://||'
```

Copy the output (format: `oidc.eks.REGION.amazonaws.com/id/XXXXX`)

#### 3.2 Update Terraform Variables

Edit `terraform/tofu-controller-crds/terraform-resource.yaml`:

1. Replace `YOUR_AWS_ACCESS_KEY` and `YOUR_AWS_SECRET_KEY` with your AWS credentials
2. Replace `YOUR_CLUSTER_OIDC_ID` with the OIDC ID from step 3.1
3. Replace `YOUR_USERNAME` with your GitHub username

#### 3.3 Create Git Credentials Secret

```bash
kubectl create namespace agent-core-infra

kubectl create secret generic git-credentials \
  --from-literal=username=YOUR_GITHUB_USERNAME \
  --from-literal=password=YOUR_GITHUB_TOKEN \
  -n agent-core-infra
```

#### 3.4 Commit and Push Code

```bash
cd ~/WorkDocsDownloads/AWS_Internal/Containers/Kiro-Projects/agent-core-pocs
git init
git add .
git commit -m "Initial commit: Agent Core POC"
git remote add origin https://github.com/YOUR_USERNAME/agent-core-pocs.git
git push -u origin main
```

#### 3.5 Deploy Terraform via Tofu Controller

```bash
cd terraform/tofu-controller-crds
kubectl apply -k .
```

Monitor the Terraform execution:
```bash
kubectl get terraform -n agent-core-infra -w
kubectl logs -n agent-core-infra -l app=tofu-controller -f
```

Wait for the Terraform resource to show "Ready":
```bash
kubectl wait --for=condition=ready terraform/agent-core-components -n agent-core-infra --timeout=600s
```

#### 3.6 Verify Outputs

```bash
kubectl get secret agent-core-outputs -n agent-core-infra -o yaml
```

### Phase 4: Build and Deploy Strands Agent

#### 4.1 Build Docker Image

```bash
cd strands-agent
docker build -t strands-agent:latest .
```

For EKS, push to ECR:
```bash
aws ecr create-repository --repository-name strands-agent --region us-west-2
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com
docker tag strands-agent:latest ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com/strands-agent:latest
docker push ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com/strands-agent:latest
```

Update `deployment/deployment.yaml` with the ECR image URI.

#### 4.2 Update IAM Role ARN

Get the Strands Agent IAM Role ARN:
```bash
kubectl get secret agent-core-outputs -n agent-core-infra -o jsonpath='{.data.strands_agent_role_arn}' | base64 -d
```

Update `deployment/deployment.yaml` with the role ARN in the ServiceAccount annotation.

#### 4.3 Deploy Agent

```bash
cd deployment
kubectl apply -k .
```

Verify deployment:
```bash
kubectl get pods -l app=strands-agent
kubectl logs -l app=strands-agent -f
```

### Phase 5: Test the Agent

#### 5.1 Check Agent Logs

```bash
kubectl logs -l app=strands-agent --tail=100
```

You should see the weather example execution with:
1. Code execution results
2. Memory retrieval
3. Web browsing
4. LLM response generation

#### 5.2 Manual Test

Execute the agent manually:
```bash
kubectl exec -it deployment/strands-agent -- python agent.py
```

## Troubleshooting

### Tofu Controller Issues

```bash
# Check Tofu Controller logs
kubectl logs -n tofu-system -l app=tofu-controller

# Check Terraform resource status
kubectl describe terraform agent-core-components -n agent-core-infra
```

### Agent Pod Issues

```bash
# Check pod events
kubectl describe pod -l app=strands-agent

# Check IAM role assumption
kubectl exec -it deployment/strands-agent -- aws sts get-caller-identity
```

### Lambda Invocation Issues

```bash
# Test Lambda directly
aws lambda invoke --function-name agent-core-poc-code-interpreter --payload '{"code":"print(1+1)"}' /tmp/output.json
```

## Architecture Validation

Verify the complete flow:

1. **FluxCD** monitors Git repository
2. **Tofu Controller** executes Terraform to create AWS resources
3. **Agent Core Components** (Memory, Browser, Code Interpreter) are provisioned in AWS
4. **Strands Agent** runs on EKS and invokes Agent Core components
5. **IRSA** (IAM Roles for Service Accounts) provides AWS credentials to the pod

## Cleanup

To destroy all resources:

```bash
# Delete Strands Agent
kubectl delete -k strands-agent/deployment/

# Delete Terraform resources (this will destroy AWS resources)
kubectl delete -k terraform/tofu-controller-crds/

# Uninstall Tofu Controller
kubectl delete -f flux/02-install-tofu-controller.yaml

# Uninstall FluxCD
flux uninstall
```

## Next Steps

1. Enhance Lambda functions with actual code execution and browser automation
2. Populate Agent Core Memory with relevant knowledge
3. Implement more complex agent workflows
4. Add monitoring and observability
5. Implement CI/CD pipeline for agent updates
