# Complete Setup Guide - EKS Agent Core POC

## Prerequisites

- EKS cluster (v1.28+) with Pod Identity addon installed
- kubectl configured for your cluster
- AWS CLI configured
- Terraform/OpenTofu
- FluxCD or ArgoCD for GitOps

## IAM Policies Required

### 1. TofuControllerRole Policy

This role is used by the Tofu Controller to provision AWS resources via Terraform.

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
        "ec2:DescribeSecurityGroups"
      ],
      "Resource": "*"
    }
  ]
}
```

**Apply with:**
```bash
aws iam put-role-policy \
  --role-name TofuControllerRole \
  --policy-name TofuControllerPolicy \
  --policy-document file://tofu-controller-policy.json
```

### 2. Strands Agent Role (Created by Terraform)

This role is automatically created by Terraform with Pod Identity trust policy:

**Trust Policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Service": "pods.eks.amazonaws.com"
    },
    "Action": [
      "sts:AssumeRole",
      "sts:TagSession"
    ]
  }]
}
```

**Permissions Policy (auto-created by Terraform):**
- `bedrock:InvokeAgentCoreTool`
- `bedrock-agentcore:*` (all Agent Core operations)
- `bedrock:InvokeModel` (all regions)
- `bedrock:InvokeModelWithResponseStream` (all regions)
- `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` (results bucket)

## Setup Steps

### Step 1: Install EKS Pod Identity Addon

```bash
aws eks create-addon \
  --cluster-name <your-cluster> \
  --addon-name eks-pod-identity-agent \
  --region us-east-1
```

### Step 2: Create TofuControllerRole

```bash
# Create trust policy
cat > trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::<account-id>:oidc-provider/<oidc-provider>"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "<oidc-provider>:sub": "system:serviceaccount:flux-system:tf-controller",
        "<oidc-provider>:aud": "sts.amazonaws.com"
      }
    }
  }]
}
EOF

# Create role
aws iam create-role \
  --role-name TofuControllerRole \
  --assume-role-policy-document file://trust-policy.json

# Attach policy
aws iam put-role-policy \
  --role-name TofuControllerRole \
  --policy-name TofuControllerPolicy \
  --policy-document file://tofu-controller-policy.json
```

### Step 3: Update OIDC Provider Thumbprint

**IMPORTANT:** Update the OIDC provider thumbprint to the latest root CA:

```bash
aws iam update-open-id-connect-provider-thumbprint \
  --open-id-connect-provider-arn arn:aws:iam::<account-id>:oidc-provider/<oidc-issuer> \
  --thumbprint-list 9e99a48a9960b14926bb7f3b02e22da2b0ab7280
```

### Step 4: Deploy Infrastructure

```bash
# Apply Terraform CRDs
kubectl apply -k terraform/tofu-controller-crds/

# Wait for Terraform to complete
kubectl get terraform agent-core-components -n agent-core-infra -w
```

### Step 5: Create Pod Identity Association

```bash
aws eks create-pod-identity-association \
  --cluster-name <your-cluster> \
  --region us-east-1 \
  --namespace agent-core-infra \
  --service-account strands-agent-sa \
  --role-arn arn:aws:iam::<account-id>:role/ekspoc-v3-strands-agent-role
```

### Step 6: Build and Push Container Image

```bash
cd strands-agent

# Build for x86_64 (EKS nodes)
podman build --platform linux/amd64 \
  -t <account-id>.dkr.ecr.us-east-1.amazonaws.com/strands-agent:latest .

# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  podman login --username AWS --password-stdin \
  <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Push
podman push <account-id>.dkr.ecr.us-east-1.amazonaws.com/strands-agent:latest
```

### Step 7: Deploy Strands Agent

```bash
kubectl apply -f strands-agent/deployment/deployment.yaml
```

## Testing

```bash
kubectl exec -it -n agent-core-infra deployment/strands-agent -- python -c "
import asyncio
from agent import async_main

result = asyncio.run(async_main('What should I do this weekend in Richmond VA?'))
print(result)
"
```

## Troubleshooting

### IRSA Issues
If you see `AssumeRoleWithWebIdentity` errors, update the OIDC thumbprint (Step 3).

### Pod Identity Issues
Ensure:
1. Pod Identity addon is installed
2. Pod Identity association exists
3. IAM role has correct trust policy (`pods.eks.amazonaws.com`)

### Permission Errors
Check that all required permissions are in the IAM policies above.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    EKS Cluster (dev)                        │
│                                                             │
│  ┌──────────────┐      ┌─────────────────────────────┐      │
│  │   FluxCD     │─────▶│   Tofu Controller           │      │
│  └──────────────┘      └─────────────────────────────┘      │
│         │                        │                          │
│         │                        ▼                          │
│         │              ┌──────────────────┐                 │
│         │              │ Terraform CRDs   │                 │
│         │              │ (provisions AWS) │                 │
│         │              └──────────────────┘                 │
│         │                        │                          │
│         ▼                        │                          │
│  ┌──────────────────────────────┼─────────────────────┐     │
│  │         Strands Agent Pod     │                    │     │
│  │  (Pod Identity: ekspoc-v3-strands-agent-role)     │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────────┐
              │      AWS us-east-1         │
              │  ┌──────────────────────┐  │
              │  │ Agent Core Memory    │  │
              │  ├──────────────────────┤  │
              │  │ Agent Core Browser   │  │
              │  ├──────────────────────┤  │
              │  │ Code Interpreter     │  │
              │  ├──────────────────────┤  │
              │  │ S3 Results Bucket    │  │
              │  └──────────────────────┘  │
              └────────────────────────────┘
```

## Resources Created

- **Agent Core Memory**: `ekspoc_v3_memory-*`
- **Agent Core Browser**: `ekspoc_v3_browser-*`
- **Agent Core Code Interpreter**: `ekspoc_v3_code_interpreter-*`
- **IAM Role**: `ekspoc-v3-strands-agent-role`
- **S3 Bucket**: `ekspoc-v3-weather-results`
- **Pod Identity Association**: Links service account to IAM role

## Security Notes

- Uses **EKS Pod Identity** (not IRSA) for secure credential management
- No hardcoded credentials in containers
- IAM policies follow least-privilege principle
- S3 bucket has versioning enabled
- All Agent Core tools use secure WebSocket connections
