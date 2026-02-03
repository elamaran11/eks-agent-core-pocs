# Agent Core on EKS - Complete GitOps Deployment Guide

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [IAM Permissions](#iam-permissions)
5. [Deployment](#deployment)
6. [Deploying Different Versions](#deploying-different-versions)
7. [Verification](#verification)
8. [Testing](#testing)
9. [Troubleshooting](#troubleshooting)
10. [Cleanup](#cleanup)

---

## Overview

Deploy Agent Core capabilities (Memory, Browser, Code Interpreter) with Strands agents on EKS using **full GitOps automation**. Simply change `values.yaml` to deploy any version (v4, v5, v6, etc.) with different capability configurations.

**Key Features:**
- ✅ Single parameterized deployment for all versions
- ✅ Full GitOps via ArgoCD
- ✅ Terraform managed via Tofu Controller
- ✅ Sync waves ensure proper ordering
- ✅ Pod Identity for secure IAM authentication
- ✅ Toggle capabilities on/off per version

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    EKS Cluster (dev)                        │
│                                                             │
│  ┌──────────────┐      ┌─────────────────────────────┐      │
│  │   ArgoCD     │─────▶│   Tofu Controller           │      │
│  └──────────────┘      └─────────────────────────────┘      │
│         │                        │                          │
│         │ (reads values.yaml)    │                          │
│         ▼                        ▼                          │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Wave 0: Terraform CR                             │       │
│  │  - Provisions AWS resources                      │       │
│  │  - Creates IAM Role                              │       │
│  │  - Creates Pod Identity Association              │       │
│  │  - Writes outputs to Secret                      │       │
│  └──────────────────────────────────────────────────┘       │
│         │ (ArgoCD waits for Ready=True)                     │
│         ▼                                                   │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Wave 1: Agent Deployment                         │       │
│  │  - Reads Secret for capability IDs               │       │
│  │  - Uses Pod Identity for IAM credentials         │       │
│  └──────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────────┐
              │      AWS (us-east-1)       │
              │  ┌──────────────────────┐  │
              │  │ Agent Core Memory    │  │
              │  ├──────────────────────┤  │
              │  │ Agent Core Browser   │  │
              │  ├──────────────────────┤  │
              │  │ Code Interpreter     │  │
              │  ├──────────────────────┤  │
              │  │ IAM Role + Policy    │  │
              │  ├──────────────────────┤  │
              │  │ S3 Results Bucket    │  │
              │  └──────────────────────┘  │
              └────────────────────────────┘
```

---

## Prerequisites

### 1. EKS Cluster
- **Version**: 1.28 or higher
- **Name**: `dev` (or update in `values.yaml`)
- **kubectl**: Configured with cluster access

### 2. EKS Pod Identity Addon

```bash
# Install Pod Identity Agent
aws eks create-addon \
  --cluster-name dev \
  --addon-name eks-pod-identity-agent \
  --region us-east-1

# Verify
aws eks describe-addon \
  --cluster-name dev \
  --addon-name eks-pod-identity-agent \
  --region us-east-1 \
  --query 'addon.status'
```

Expected: `"ACTIVE"`

### 3. ArgoCD

```bash
# Install ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for ready
kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd
```

### 4. Tofu Controller

```bash
# Deploy via ArgoCD
kubectl apply -f argocd/tofu-controller-application.yaml

# Verify
kubectl get pods -n flux-system -l app.kubernetes.io/name=tf-controller
```

### 5. AWS Bedrock Access

Enable in AWS Console → Bedrock → Model access:
- Amazon Bedrock Agent Core
- Claude Sonnet models
- Inference profiles

---

## IAM Permissions

### Tofu Controller Role

Create `TofuControllerRole` with this policy:

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

**Apply:**
```bash
aws iam put-role-policy \
  --role-name TofuControllerRole \
  --policy-name TofuControllerPolicy \
  --policy-document file://tofu-controller-policy.json
```

### Agent IAM Role

**Automatically created by Terraform** with these permissions:
- `bedrock:InvokeModel` - Call foundation models
- `bedrock:InvokeModelWithResponseStream` - Stream responses
- `bedrock-agentcore:*` - Full Agent Core access
- `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` - S3 storage

---

## Deployment

### Step 1: Configure ArgoCD Health Check

```bash
bash scripts/setup-v4.sh
```

This configures ArgoCD to wait for Terraform completion.

### Step 2: Deploy Namespace Setup (One-Time)

```bash
kubectl apply -f argocd/agent-core-namespace-setup.yaml
```

Creates RBAC for Tofu Controller.

### Step 3: Configure Your Version

Edit `values.yaml`:

```yaml
version: v4
projectName: ekspoc-v4
awsRegion: us-east-1
eksClusterName: dev
networkMode: PUBLIC
capabilities:
  memory: true
  browser: true
  codeInterpreter: true
namespace: agent-core-infra
```

### Step 4: Deploy

```bash
# Commit values
git add values.yaml
git commit -m "Deploy v4"
git push

# Deploy ArgoCD Application
kubectl apply -f argocd/agent-core-stack.yaml
```

### Step 5: Monitor

```bash
# Watch Terraform (Wave 0)
kubectl get terraform agent-core-components-v4 -n agent-core-infra -w

# Watch Agent (Wave 1)
kubectl get pods -n agent-core-infra -l app=strands-agent-v4 -w
```

**Timeline:** ~3 minutes for Terraform, ~30 seconds for agent

---

## Deploying Different Versions

### Deploy v5 with Different Capabilities

1. Edit `values.yaml`:
```yaml
version: v5
projectName: ekspoc-v5
capabilities:
  memory: true
  browser: false  # Disable browser
  codeInterpreter: true
```

2. Commit and push:
```bash
git add values.yaml
git commit -m "Deploy v5 without browser"
git push
```

3. ArgoCD auto-syncs and deploys v5!

### Run Multiple Versions Simultaneously

Each version is completely isolated:

| Resource | v4 | v5 |
|----------|----|----|
| Terraform CR | agent-core-components-v4 | agent-core-components-v5 |
| Agent Pod | strands-agent-v4 | strands-agent-v5 |
| IAM Role | ekspoc-v4-strands-agent-role | ekspoc-v5-strands-agent-role |
| S3 Bucket | ekspoc-v4-weather-results | ekspoc-v5-weather-results |

---

## Verification

### 1. Check Terraform Status

```bash
kubectl get terraform agent-core-components-v4 -n agent-core-infra
```

Expected: `READY=True`, `STATUS=No drift`

### 2. Check Secret Created

```bash
kubectl get secret agent-core-outputs-v4 -n agent-core-infra -o jsonpath='{.data}' | jq 'keys'
```

Expected keys: `browser_id`, `code_interpreter_id`, `memory_id`, `results_bucket_name`, `service_account_name`, `strands_agent_role_arn`

### 3. Check Agent Credentials

```bash
kubectl exec -n agent-core-infra deployment/strands-agent-v4 -- python -c "
import boto3
sts = boto3.client('sts', region_name='us-east-1')
print('ARN:', sts.get_caller_identity()['Arn'])
"
```

Expected: `arn:aws:sts::ACCOUNT:assumed-role/ekspoc-v4-strands-agent-role/...`

### 4. Check AWS Resources

```bash
# Agent Core
aws bedrock-agent list-agent-memories --region us-east-1 | grep ekspoc-v4

# S3 Bucket
aws s3 ls | grep ekspoc-v4-weather-results

# Pod Identity
aws eks list-pod-identity-associations --cluster-name dev --region us-east-1
```

---

## Testing

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
1. Browser scrapes weather.gov
2. Generates Python classification code
3. Executes via Code Interpreter
4. Retrieves preferences from Memory
5. Saves results to S3

**Check results:**
```bash
aws s3 ls s3://ekspoc-v4-weather-results/
aws s3 cp s3://ekspoc-v4-weather-results/tampa-fl-weekend-activities.md -
```

---

## Troubleshooting

### Terraform Stuck

```bash
# Check logs
kubectl logs -n flux-system -l app.kubernetes.io/name=tf-controller --tail=100

# Check status
kubectl describe terraform agent-core-components-v4 -n agent-core-infra
```

### Agent Using Wrong IAM Role

```bash
# Verify Pod Identity exists
aws eks list-pod-identity-associations \
  --cluster-name dev \
  --namespace agent-core-infra \
  --service-account strands-agent-sa-ekspoc-v4 \
  --region us-east-1

# If missing, check Terraform logs
```

### ArgoCD Not Syncing

```bash
# Check Application
kubectl describe application agent-core-stack -n argocd

# Force sync
kubectl patch application agent-core-stack -n argocd \
  --type merge -p '{"operation":{"sync":{"revision":"HEAD"}}}'
```

---

## Cleanup

```bash
# Delete version
kubectl delete application agent-core-stack -n argocd

# Terraform automatically deletes all AWS resources
```

---

## Quick Reference

### File Structure
```
├── values.yaml                    # Configuration (edit this!)
├── argocd/
│   ├── agent-core-stack.yaml      # ArgoCD Application
│   └── agent-core-namespace-setup.yaml
├── gitops/agent-core-stack/       # Helm-templated manifests
│   ├── terraform-resource.yaml
│   ├── deployment.yaml
│   └── kustomization.yaml
├── terraform/agent-core-components/  # Terraform modules
└── scripts/setup-v4.sh            # One-time ArgoCD setup
```

### Key Commands

```bash
# Deploy
kubectl apply -f argocd/agent-core-stack.yaml

# Monitor
kubectl get terraform agent-core-components-v4 -n agent-core-infra -w

# Test
kubectl exec -it -n agent-core-infra deployment/strands-agent-v4 -- python -c "..."

# Cleanup
kubectl delete application agent-core-stack -n argocd
```

### Configuration Values

| Parameter | Description | Example |
|-----------|-------------|---------|
| `version` | Version identifier | `v4`, `v5`, `v6` |
| `projectName` | AWS resource prefix | `ekspoc-v4` |
| `awsRegion` | AWS region | `us-east-1` |
| `eksClusterName` | EKS cluster name | `dev` |
| `networkMode` | Agent Core network | `PUBLIC`, `VPC`, `SANDBOX` |
| `capabilities.memory` | Enable Memory | `true`/`false` |
| `capabilities.browser` | Enable Browser | `true`/`false` |
| `capabilities.codeInterpreter` | Enable Code Interpreter | `true`/`false` |

---

## Support

**Logs:**
- Terraform: `kubectl logs -n flux-system -l app.kubernetes.io/name=tf-controller`
- Agent: `kubectl logs -n agent-core-infra -l app=strands-agent-v4`
- ArgoCD: Check ArgoCD UI

**Documentation:**
- AWS Bedrock Agent Core: https://docs.aws.amazon.com/bedrock/
- ArgoCD: https://argo-cd.readthedocs.io/
- Tofu Controller: https://flux-iac.github.io/tofu-controller/
