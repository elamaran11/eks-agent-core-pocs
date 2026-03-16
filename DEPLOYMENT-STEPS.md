# KAgent MCP Integration - Deployment Steps

## Prerequisites

### 1. EKS Cluster
- Cluster name: `machine-learning`
- Region: `us-west-2`
- Kubernetes version: 1.28+

### 2. AWS CLI & kubectl
```bash
aws --version
kubectl version --client
```

### 3. Cluster Access
```bash
aws eks update-kubeconfig --name machine-learning --region us-west-2
kubectl config current-context
```

---

## Step 1: Setup IAM Role for Tofu Controller

### 1.1 Get OIDC Provider for Your Cluster
```bash
aws eks describe-cluster --name machine-learning --region us-west-2 \
  --query 'cluster.identity.oidc.issuer' --output text
```

Output: `https://oidc.eks.us-west-2.amazonaws.com/id/92E9637022D961068D146A6AC478949E`

### 1.2 Create Trust Policy

Create `tofu-trust-policy-multi-cluster.json`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::940019131157:oidc-provider/oidc.eks.us-west-2.amazonaws.com/id/92E9637022D961068D146A6AC478949E"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "oidc.eks.us-west-2.amazonaws.com/id/92E9637022D961068D146A6AC478949E:aud": "sts.amazonaws.com",
          "oidc.eks.us-west-2.amazonaws.com/id/92E9637022D961068D146A6AC478949E:sub": "system:serviceaccount:agent-core-infra:tf-runner"
        }
      }
    }
  ]
}
```

**Note**: Replace OIDC ID with your cluster's OIDC provider ID.

### 1.3 Create IAM Role (if doesn't exist)
```bash
aws iam create-role \
  --role-name TofuControllerRole \
  --assume-role-policy-document file://tofu-trust-policy-multi-cluster.json \
  --description "Tofu Controller role for EKS clusters"
```

**OR** Update existing role:
```bash
aws iam update-assume-role-policy \
  --role-name TofuControllerRole \
  --policy-document file://tofu-trust-policy-multi-cluster.json
```

### 1.4 Create Permissions Policy

Create `tofu-controller-policy.json`:
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

### 1.5 Attach Policy to Role
```bash
aws iam put-role-policy \
  --role-name TofuControllerRole \
  --policy-name TofuControllerPolicy \
  --policy-document file://tofu-controller-policy.json
```

### 1.6 Verify Role
```bash
aws iam get-role --role-name TofuControllerRole --query 'Role.Arn'
```

Expected: `arn:aws:iam::940019131157:role/TofuControllerRole`

---

## Step 2: Build and Push MCP Server Image

### 2.1 Create ECR Repository
```bash
aws ecr create-repository \
  --repository-name agent-core-mcp \
  --region us-west-2
```

### 2.2 Build Docker Image
```bash
cd mcp-server
podman build --platform linux/amd64 -t agent-core-mcp:v1.0.0 .
```

### 2.3 Tag and Push
```bash
aws ecr get-login-password --region us-west-2 | \
  podman login --username AWS --password-stdin 940019131157.dkr.ecr.us-west-2.amazonaws.com

podman tag agent-core-mcp:v1.0.0 \
  940019131157.dkr.ecr.us-west-2.amazonaws.com/agent-core-mcp:v1.0.0

podman push 940019131157.dkr.ecr.us-west-2.amazonaws.com/agent-core-mcp:v1.0.0
```

### 2.4 Verify Image
```bash
aws ecr describe-images \
  --repository-name agent-core-mcp \
  --region us-west-2 \
  --image-ids imageTag=v1.0.0
```

---

## Step 3: Install ArgoCD, Flux, and Tofu Controller

### 3.1 Run Installation Script
```bash
cd flux
bash 01-install-flux.sh
```

This installs:
- ArgoCD (with server-side apply)
- Flux (source-controller, notification-controller)
- Tofu Controller (via ArgoCD Application)

### 3.2 Verify Installation
```bash
# ArgoCD
kubectl get pods -n argocd

# Flux
kubectl get pods -n flux-system

# Tofu Controller
kubectl get pods -n flux-system -l app.kubernetes.io/name=tf-controller
```

---

## Step 4: Configure ArgoCD and Deploy Prerequisites

### 4.1 Apply ArgoCD Health Check
```bash
kubectl apply -f argocd/argocd-cm-patch.yaml
```

This configures ArgoCD to understand Terraform resource health status.

### 4.2 Deploy Namespace Setup
```bash
kubectl apply -f argocd/agent-core-namespace-setup.yaml
```

This creates:
- `agent-core-infra` namespace
- `tf-runner` ServiceAccount with IAM role annotation
- RBAC for Tofu Controller

### 4.3 Verify Namespace Setup
```bash
kubectl get application agent-core-namespace-setup -n argocd
kubectl get sa,role,rolebinding -n agent-core-infra
```

---

## Step 5: Deploy Agent Core Stack

### 5.1 Configure values.yaml
```yaml
version: v6-kagent
projectName: ekspoc-v6-kagent
awsRegion: us-west-2
eksClusterName: machine-learning
networkMode: PUBLIC

capabilities:
  memory: true
  browser: true
  codeInterpreter: true

namespace: agent-core-infra

mcpServer:
  image:
    repository: 940019131157.dkr.ecr.us-west-2.amazonaws.com/agent-core-mcp
    tag: v1.0.0
    pullPolicy: Always

kagent:
  enabled: true
```

### 5.2 Commit and Push
```bash
git add values.yaml
git commit -m "Configure v6-kagent deployment"
git push origin feature/kagent-mcp-integration
```

### 5.3 Deploy Stack
```bash
kubectl apply -f argocd/agent-core-stack.yaml
```

### 5.4 Monitor Deployment

**Wave 0: Terraform (Infrastructure)**
```bash
kubectl get terraform -n agent-core-infra -w
```

Expected progression:
- `Terraform Planning` → `Applying` → `Ready: True`

**Wave 1: MCP Server**
```bash
kubectl get pods -n agent-core-infra -l app=agent-core-mcp-v6-kagent -w
```

**Wave 2: RemoteMCPServer**
```bash
kubectl get remotemcpserver -n agent-core-infra
```

**Wave 3: KAgent Agent**
```bash
kubectl get agent -n agent-core-infra
```

**Overall Status**
```bash
kubectl get application agent-core-stack -n argocd
```

---

## Step 6: Verify Deployment

### 6.1 Check Terraform Outputs
```bash
kubectl get secret agent-core-outputs-v6-kagent -n agent-core-infra \
  -o jsonpath='{.data}' | jq 'keys'
```

Expected keys:
- `browser_id`
- `code_interpreter_id`
- `memory_id`
- `results_bucket_name`
- `service_account_name`
- `strands_agent_role_arn`

### 6.2 Check AWS Resources
```bash
# Agent Core capabilities
aws bedrock-agent list-agent-memories --region us-west-2 | grep ekspoc-v6-kagent

# S3 Bucket
aws s3 ls | grep ekspoc-v6-kagent

# Pod Identity Associations
aws eks list-pod-identity-associations \
  --cluster-name machine-learning \
  --region us-west-2
```

### 6.3 Check MCP Server
```bash
kubectl logs -n agent-core-infra -l app=agent-core-mcp-v6-kagent
```

### 6.4 Check KAgent Agent
```bash
kubectl get agent weather-agent-v6-kagent -n agent-core-infra -o yaml
```

---

## Troubleshooting

### Terraform Stuck in Planning
```bash
# Check Terraform logs
kubectl logs -n flux-system -l app.kubernetes.io/name=tf-controller --tail=100

# Check Terraform status
kubectl describe terraform agent-core-components-v6-kagent -n agent-core-infra
```

### Pod Identity Issues
```bash
# Verify ServiceAccount annotation
kubectl get sa tf-runner -n agent-core-infra -o yaml

# Check trust policy
aws iam get-role --role-name TofuControllerRole \
  --query 'Role.AssumeRolePolicyDocument'

# Verify OIDC provider matches
aws eks describe-cluster --name machine-learning --region us-west-2 \
  --query 'cluster.identity.oidc.issuer'
```

### ArgoCD Not Syncing
```bash
# Check Application status
kubectl describe application agent-core-stack -n argocd

# Force refresh
kubectl patch application agent-core-stack -n argocd \
  --type merge -p '{"operation":{"sync":{"revision":"HEAD"}}}'
```

### API Group Mismatch
If you see errors about `kagent.amazon.com` vs `kagent.dev`:
```bash
# Check installed CRDs
kubectl get crd | grep kagent

# Verify API version in manifests matches cluster
```

---

## Cleanup

```bash
# Delete ArgoCD Application (triggers Terraform destroy)
kubectl delete application agent-core-stack -n argocd

# Wait for Terraform to delete AWS resources
kubectl get terraform -n agent-core-infra -w

# Delete namespace setup
kubectl delete application agent-core-namespace-setup -n argocd
```

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `values.yaml` | Central configuration |
| `tofu-trust-policy-multi-cluster.json` | IAM trust policy |
| `tofu-controller-policy.json` | IAM permissions policy |
| `flux/01-install-flux.sh` | Install ArgoCD, Flux, Tofu |
| `argocd/argocd-cm-patch.yaml` | Terraform health check |
| `argocd/agent-core-namespace-setup.yaml` | Namespace and RBAC |
| `argocd/agent-core-stack.yaml` | Main deployment |
| `gitops/agent-core-stack/templates/` | Helm templates (4 waves) |

---

## Timeline

- **Step 1-2**: 10 minutes (IAM setup, image build)
- **Step 3**: 5 minutes (ArgoCD, Flux, Tofu install)
- **Step 4**: 2 minutes (Prerequisites)
- **Step 5**: 3-5 minutes (Terraform apply)
- **Total**: ~20-25 minutes
