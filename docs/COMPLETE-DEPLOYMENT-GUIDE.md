# Agent Core V4 - Complete GitOps Deployment Guide

## Overview

This guide provides complete instructions for deploying Agent Core capabilities (Memory, Browser, Code Interpreter) with a Strands agent on EKS using full GitOps automation via ArgoCD.

## Architecture

```
ArgoCD Application
  ↓
Wave 0: Terraform (provisions AWS resources)
  - Agent Core Memory
  - Agent Core Browser  
  - Agent Core Code Interpreter
  - IAM Role with Bedrock/S3 permissions
  - Pod Identity Association
  - S3 Bucket for results
  ↓
ArgoCD Health Check (waits for Terraform Ready=True)
  ↓
Wave 1: Agent Deployment (uses Terraform outputs)
  - Strands Agent Pod
  - Reads capabilities from secret
```

## Prerequisites

### 1. EKS Cluster Requirements
- EKS cluster version 1.28 or higher
- Cluster name: `dev` (or update in configs)
- kubectl configured with cluster access

### 2. Required EKS Addons
```bash
# Pod Identity Agent (required for IAM authentication)
aws eks create-addon \
  --cluster-name dev \
  --addon-name eks-pod-identity-agent \
  --region us-east-1

# Verify addon is active
aws eks describe-addon \
  --cluster-name dev \
  --addon-name eks-pod-identity-agent \
  --region us-east-1
```

### 3. ArgoCD Installation
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for ArgoCD to be ready
kubectl wait --for=condition=available --timeout=300s \
  deployment/argocd-server -n argocd
```

### 4. Tofu Controller Installation
```bash
# Deploy via ArgoCD
kubectl apply -f argocd/tofu-controller-application.yaml

# Verify installation
kubectl get pods -n flux-system -l app.kubernetes.io/name=tf-controller
```

### 5. AWS Bedrock Access
Ensure your AWS account has access to:
- Amazon Bedrock Agent Core (Memory, Browser, Code Interpreter)
- Bedrock foundation models (Claude Sonnet)
- Bedrock inference profiles

Request access in AWS Console → Bedrock → Model access

## IAM Permissions

### Tofu Controller Role

The Tofu Controller needs permissions to provision AWS resources. Create/update the `TofuControllerRole`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:*",
        "bedrock-agentcore:*",
        "s3:*",
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:GetRole",
        "iam:PassRole",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:GetRolePolicy",
        "iam:ListAttachedRolePolicies",
        "iam:ListRolePolicies",
        "iam:UpdateAssumeRolePolicy",
        "aoss:*",
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeSecurityGroups",
        "eks:DescribeCluster",
        "eks:CreatePodIdentityAssociation",
        "eks:DeletePodIdentityAssociation",
        "eks:DescribePodIdentityAssociation",
        "eks:ListPodIdentityAssociations"
      ],
      "Resource": "*"
    }
  ]
}
```

**Apply the policy:**
```bash
aws iam put-role-policy \
  --role-name TofuControllerRole \
  --policy-name TofuControllerPolicy \
  --policy-document file://tofu-controller-policy.json
```

### Agent IAM Role

Terraform automatically creates the agent IAM role (`ekspoc-v4-strands-agent-role`) with these permissions:
- `bedrock:InvokeModel` - Call Bedrock foundation models
- `bedrock:InvokeModelWithResponseStream` - Stream responses from Bedrock
- `bedrock:InvokeAgentCoreTool` - Use Agent Core capabilities
- `bedrock-agentcore:*` - Full Agent Core access
- `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` - S3 results storage

## Deployment Steps

### Step 1: Configure ArgoCD Health Check

This tells ArgoCD to wait for Terraform to complete before deploying the agent.

```bash
# Run the setup script
bash scripts/setup-v4.sh
```

This configures ArgoCD to recognize when Terraform resources are healthy.

### Step 2: Deploy Namespace Setup (One-Time)

Creates RBAC resources for Tofu Controller to run Terraform in the namespace.

```bash
kubectl apply -f argocd/agent-core-namespace-setup.yaml
```

**Verify:**
```bash
kubectl get serviceaccount tf-runner -n agent-core-infra
kubectl get role tf-runner -n agent-core-infra
```

### Step 3: Deploy V4 Stack

This single command deploys everything via GitOps:

```bash
kubectl apply -f argocd/agent-core-v4-stack.yaml
```

**What happens:**
1. ArgoCD creates Terraform CR
2. Tofu Controller provisions AWS resources (~3 minutes)
3. Terraform creates secret with capability IDs
4. ArgoCD waits for Terraform "Ready=True"
5. ArgoCD deploys agent automatically
6. Agent pod starts with correct IAM role via Pod Identity

### Step 4: Monitor Deployment

**Watch Terraform progress:**
```bash
kubectl get terraform agent-core-components-v4 -n agent-core-infra -w
```

Expected status progression:
- `Initializing` → `Terraform Planning` → `Applying` → `Ready`

**Watch agent deployment:**
```bash
kubectl get pods -n agent-core-infra -l app=strands-agent-v4 -w
```

**Check ArgoCD Application:**
```bash
kubectl get application agent-core-v4-stack -n argocd
```

## Verification

### 1. Verify AWS Resources Created

```bash
# Agent Core resources
aws bedrock-agent list-agent-memories --region us-east-1 | grep ekspoc-v4
aws bedrock-agent list-agent-code-interpreters --region us-east-1 | grep ekspoc-v4

# S3 bucket
aws s3 ls | grep ekspoc-v4-weather-results

# IAM role
aws iam get-role --role-name ekspoc-v4-strands-agent-role

# Pod Identity association
aws eks list-pod-identity-associations \
  --cluster-name dev \
  --namespace agent-core-infra \
  --region us-east-1
```

### 2. Verify Secret Created

```bash
kubectl get secret agent-core-outputs-v4 -n agent-core-infra

# Check contents
kubectl get secret agent-core-outputs-v4 -n agent-core-infra \
  -o jsonpath='{.data}' | jq 'keys'
```

Expected keys: `browser_arn`, `browser_id`, `code_interpreter_arn`, `code_interpreter_id`, `memory_id`, `namespace`, `results_bucket_name`, `service_account_name`, `strands_agent_role_arn`

### 3. Verify Agent Has Correct Credentials

```bash
# Check IAM identity
kubectl exec -n agent-core-infra deployment/strands-agent-v4 -- \
  python -c "
import boto3
sts = boto3.client('sts', region_name='us-east-1')
identity = sts.get_caller_identity()
print('ARN:', identity['Arn'])
"
```

Expected: `arn:aws:sts::ACCOUNT:assumed-role/ekspoc-v4-strands-agent-role/...`

### 4. Verify Capabilities Enabled

```bash
kubectl exec -n agent-core-infra deployment/strands-agent-v4 -- \
  env | grep -E "(BROWSER_ID|CODE_INTERPRETER_ID|MEMORY_ID)"
```

All three should have values.

## Testing the Agent

```bash
kubectl exec -it -n agent-core-infra deployment/strands-agent-v4 -- python -c "
import asyncio
from agent import async_main

result = asyncio.run(async_main('What should I do this weekend in Tampa, FL?'))
print('\n=== RESULT ===')
print(result)
"
```

**Expected workflow:**
1. Browser scrapes weather.gov for Tampa
2. Generates Python code to classify weather
3. Executes code via Code Interpreter
4. Retrieves preferences from Memory
5. Generates activity recommendations
6. Saves results to S3

**Verify results in S3:**
```bash
aws s3 ls s3://ekspoc-v4-weather-results/
aws s3 cp s3://ekspoc-v4-weather-results/tampa-fl-weekend-activities.md -
```

## Capability Toggles

To enable/disable capabilities, edit `terraform/tofu-controller-crds-v4/terraform-resource.yaml`:

```yaml
vars:
  - name: enable_memory
    value: false  # Disable Memory
  - name: enable_browser
    value: true   # Keep Browser
  - name: enable_code_interpreter
    value: true   # Keep Code Interpreter
```

Commit and push. ArgoCD will auto-sync and Terraform will update resources.

## Troubleshooting

### Terraform Stuck in "Applying"

```bash
# Check Terraform logs
kubectl logs -n flux-system -l app.kubernetes.io/name=tf-controller --tail=100

# Check Terraform status
kubectl describe terraform agent-core-components-v4 -n agent-core-infra
```

### Agent Pod Using Wrong IAM Role

```bash
# Verify Pod Identity association exists
aws eks list-pod-identity-associations \
  --cluster-name dev \
  --namespace agent-core-infra \
  --service-account strands-agent-sa-ekspoc-v4 \
  --region us-east-1

# If missing, Terraform didn't create it - check Terraform logs
```

### Agent Can't Access Bedrock

```bash
# Check IAM role permissions
aws iam get-role-policy \
  --role-name ekspoc-v4-strands-agent-role \
  --policy-name terraform-20260203165604516000000004

# Verify Bedrock model access in AWS Console
```

### ArgoCD Not Syncing

```bash
# Check Application status
kubectl describe application agent-core-v4-stack -n argocd

# Force sync
kubectl patch application agent-core-v4-stack -n argocd \
  --type merge -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"revision":"HEAD"}}}'
```

## Cleanup

To remove V4 completely:

```bash
# Delete ArgoCD Application (will delete all resources)
kubectl delete application agent-core-v4-stack -n argocd

# Verify cleanup
kubectl get terraform -n agent-core-infra
kubectl get pods -n agent-core-infra
aws s3 ls | grep ekspoc-v4
```

**Note:** Terraform will automatically delete AWS resources when the Terraform CR is deleted (due to `destroyResourcesOnDeletion: true`).

## Production Considerations

1. **Repository Access**: Ensure ArgoCD has access to your Git repository (SSH keys or tokens)
2. **Secrets Management**: Consider using AWS Secrets Manager or External Secrets Operator for sensitive data
3. **Monitoring**: Set up CloudWatch alarms for Agent Core usage and costs
4. **Backup**: Enable S3 versioning (already configured) and consider cross-region replication
5. **High Availability**: Increase agent replicas in production
6. **Resource Limits**: Add CPU/memory limits to agent deployment
7. **Network Policies**: Restrict pod-to-pod communication
8. **Pod Security**: Use Pod Security Standards (restricted profile)

## Support

For issues or questions:
1. Check Terraform logs: `kubectl logs -n flux-system -l app.kubernetes.io/name=tf-controller`
2. Check agent logs: `kubectl logs -n agent-core-infra -l app=strands-agent-v4`
3. Review ArgoCD UI for sync status
4. Consult AWS Bedrock Agent Core documentation
