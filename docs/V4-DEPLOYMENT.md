# V4 Deployment Guide - Full GitOps

## Prerequisites

1. ✅ EKS cluster "dev" with kubectl access
2. ✅ ArgoCD installed on the cluster
3. ✅ Tofu Controller installed (via argocd/tofu-controller-application.yaml)
4. ✅ Repository made public OR ArgoCD configured with private repo credentials
5. ✅ All changes committed and pushed to GitHub

## Step 1: Configure ArgoCD Health Check (One-Time Setup)

This tells ArgoCD to wait for Terraform to complete before deploying the agent.

```bash
# Edit ArgoCD ConfigMap
kubectl edit configmap argocd-cm -n argocd

# Add this under 'data:' section (copy from argocd/terraform-health-check.yaml):
data:
  resource.customizations.health.infra.contrib.fluxcd.io_Terraform: |
    hs = {}
    if obj.status ~= nil then
      if obj.status.plan ~= nil and obj.status.plan.pending ~= nil then
        hs.status = "Progressing"
        hs.message = "Terraform plan pending"
        return hs
      end
      if obj.status.conditions ~= nil then
        for i, condition in ipairs(obj.status.conditions) do
          if condition.type == "Ready" and condition.status == "True" then
            hs.status = "Healthy"
            hs.message = "Terraform applied successfully"
            return hs
          end
          if condition.type == "Ready" and condition.status == "False" then
            hs.status = "Degraded"
            hs.message = condition.message
            return hs
          end
        end
      end
    end
    hs.status = "Progressing"
    hs.message = "Waiting for Terraform to complete"
    return hs

# Save and exit
```

## Step 2: Deploy V4 Stack

```bash
# Deploy the ArgoCD Application
kubectl apply -f argocd/agent-core-v4-stack.yaml
```

## Step 3: Monitor Deployment

### Watch Terraform Progress (Wave 0)
```bash
# Watch Terraform resource
kubectl get terraform agent-core-components-v4 -n agent-core-infra -w

# Check Terraform logs
kubectl logs -n flux-system -l app.kubernetes.io/name=tf-controller -f

# Check ArgoCD Application status
kubectl get application agent-core-v4-stack -n argocd -o jsonpath='{.status.health.status}'
```

**Expected Timeline:** 15-20 minutes for AWS resources to provision

### Verify Secret Created
```bash
# Once Terraform completes, verify secret exists
kubectl get secret agent-core-outputs-v4 -n agent-core-infra

# Check secret contents
kubectl get secret agent-core-outputs-v4 -n agent-core-infra -o jsonpath='{.data}' | jq
```

### Watch Agent Deployment (Wave 1)
```bash
# Watch agent pod creation (starts automatically after Terraform completes)
kubectl get pods -n agent-core-infra -l app=strands-agent-v4 -w

# Check agent logs
kubectl logs -n agent-core-infra -l app=strands-agent-v4 -f
```

**Expected output:**
```
🔧 Enabled Capabilities:
  Browser: ✅
  Code Interpreter: ✅
  Memory: ✅
🚀 Strands Agent Running on EKS
Waiting for requests...
```

## Step 4: Verify V4 Resources

### Check AWS Resources
```bash
# List Agent Core resources
aws bedrock-agent list-agent-memories --region us-east-1 | grep ekspoc-v4
aws bedrock-agent list-agent-code-interpreters --region us-east-1 | grep ekspoc-v4

# Check S3 bucket
aws s3 ls | grep ekspoc-v4-weather-results

# Check IAM role
aws iam get-role --role-name ekspoc-v4-strands-agent-role
```

### Check Pod Identity Association
```bash
aws eks list-pod-identity-associations --cluster-name dev --region us-east-1
```

## Step 5: Test Agent

```bash
# Exec into agent pod
kubectl exec -it -n agent-core-infra deployment/strands-agent-v4 -- bash

# Run test query
python -c "
import asyncio
from agent import async_main
result = asyncio.run(async_main('What should I do this weekend in Richmond VA?'))
print(result)
"
```

## Step 6: Verify Results in S3

```bash
# List files in results bucket
aws s3 ls s3://ekspoc-v4-weather-results/

# Download and view results
aws s3 cp s3://ekspoc-v4-weather-results/richmond-va-weekend-activities.md -
```

## Troubleshooting

### Terraform Stuck in "Progressing"
```bash
# Check Terraform status
kubectl describe terraform agent-core-components-v4 -n agent-core-infra

# Check Tofu Controller logs
kubectl logs -n flux-system -l app.kubernetes.io/name=tf-controller --tail=100
```

### Agent Pod CrashLoopBackOff
```bash
# Check if secret exists
kubectl get secret agent-core-outputs-v4 -n agent-core-infra

# Check pod events
kubectl describe pod -n agent-core-infra -l app=strands-agent-v4

# Check agent logs
kubectl logs -n agent-core-infra -l app=strands-agent-v4
```

### ArgoCD Not Syncing
```bash
# Check Application status
kubectl describe application agent-core-v4-stack -n argocd

# Force sync
kubectl patch application agent-core-v4-stack -n argocd --type merge -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"revision":"HEAD"}}}'
```

## Cleanup V4 (Does NOT affect V3)

```bash
# Delete ArgoCD Application (will delete all resources)
kubectl delete -f argocd/agent-core-v4-stack.yaml

# Verify cleanup
kubectl get terraform -n agent-core-infra
kubectl get pods -n agent-core-infra
aws s3 ls | grep ekspoc-v4
```

## V3 vs V4 Isolation

| Resource | V3 (Existing) | V4 (New) |
|----------|---------------|----------|
| ArgoCD App | N/A (manual) | agent-core-v4-stack |
| Terraform CR | agent-core-components | agent-core-components-v4 |
| Secret | agent-core-outputs | agent-core-outputs-v4 |
| Deployment | strands-agent | strands-agent-v4 |
| ServiceAccount | strands-agent-sa | strands-agent-sa-v4 |
| Memory | ekspoc-v3-memory | ekspoc-v4-memory |
| Browser | ekspoc-v3-browser | ekspoc-v4-browser |
| Code Interpreter | ekspoc-v3-code-interpreter | ekspoc-v4-code-interpreter |
| IAM Role | ekspoc-v3-strands-agent-role | ekspoc-v4-strands-agent-role |
| S3 Bucket | ekspoc-v3-weather-results | ekspoc-v4-weather-results |

**V3 remains completely untouched!**
