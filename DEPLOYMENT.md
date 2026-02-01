# Final Deployment Steps

## Prerequisites
- EKS cluster "dev" with kubectl access
- AWS CLI configured
- Docker installed
- GitHub account

## Step 1: Setup IRSA for Tofu Controller

### 1.1: Get EKS OIDC Provider
```bash
aws eks describe-cluster --name dev --query "cluster.identity.oidc.issuer" --output text | sed 's|https://||'
```
**Save this output** - Example: `oidc.eks.us-east-1.amazonaws.com/id/652A47046A6D0FA5C9071665DDF5C723`

### 1.2: Create IAM Policy
```bash
cd ~/WorkDocsDownloads/AWS_Internal/Containers/Kiro-Projects/agent-core-pocs

cat > tofu-controller-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:*",
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
        "aoss:*",
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeSecurityGroups"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam create-policy \
  --policy-name TofuControllerPolicy \
  --policy-document file://tofu-controller-policy.json
```

### 1.3: Create IAM Role with IRSA Trust Policy
```bash
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export OIDC_PROVIDER="oidc.eks.us-east-1.amazonaws.com/id/652A47046A6D0FA5C9071665DDF5C723"

cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::${ACCOUNT_ID}:oidc-provider/${OIDC_PROVIDER}"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "${OIDC_PROVIDER}:sub": "system:serviceaccount:flux-system:tf-controller",
          "${OIDC_PROVIDER}:aud": "sts.amazonaws.com"
        }
      }
    }
  ]
}
EOF

aws iam create-role \
  --role-name TofuControllerRole \
  --assume-role-policy-document file://trust-policy.json

aws iam attach-role-policy \
  --role-name TofuControllerRole \
  --policy-arn arn:aws:iam::${ACCOUNT_ID}:policy/TofuControllerPolicy
```

### 1.4: Update Tofu Controller Application YAML
Edit `argocd/tofu-controller-application.yaml` and update the IAM role ARN (line 24):
```yaml
serviceAccount:
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::940019131157:role/TofuControllerRole
```

## Step 2: Install ArgoCD (if not installed)
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

## Step 3: Update Configuration Files

### 3.1: Update Terraform CRD
Edit `terraform/tofu-controller-crds/terraform-resource.yaml`:

**Line 10:** Update GitHub repository URL
```yaml
url: https://github.com/YOUR_USERNAME/agent-core-pocs
```

**Line 19-21:** Update OIDC provider (if different from above)
```yaml
- name: eks_oidc_provider
  value: oidc.eks.us-east-1.amazonaws.com/id/652A47046A6D0FA5C9071665DDF5C723
```

## Step 4: Push Code to GitHub
```bash
cd ~/WorkDocsDownloads/AWS_Internal/Containers/Kiro-Projects/agent-core-pocs
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/agent-core-pocs.git
git push -u origin main
```

## Step 5: Create Kubernetes Secrets
```bash
# Create namespace
kubectl create namespace agent-core-infra

# Create Git credentials secret
kubectl create secret generic git-credentials \
  --from-literal=username=YOUR_GITHUB_USERNAME \
  --from-literal=password=YOUR_GITHUB_TOKEN \
  -n agent-core-infra
```

## Step 6: Deploy FluxCD and Tofu Controller
```bash
cd ~/WorkDocsDownloads/AWS_Internal/Containers/Kiro-Projects/agent-core-pocs/argocd
kubectl apply -k .
```

Wait for pods:
```bash
kubectl get pods -n flux-system -w
```
Wait until all pods are Running.

## Step 7: Deploy Terraform Infrastructure
```bash
cd ../terraform/tofu-controller-crds
kubectl apply -k .
```

Monitor Terraform execution:
```bash
kubectl get terraform -n agent-core-infra -w
```
Wait for status: **Ready** (takes 5-10 minutes).

## Step 8: Verify Terraform Outputs
```bash
kubectl get secret agent-core-outputs -n agent-core-infra -o jsonpath='{.data}' | jq -r 'to_entries[] | "\(.key): \(.value | @base64d)"'
```

You should see:
- agent_memory_kb_id
- code_interpreter_id
- browser_id
- strands_agent_role_arn

## Step 9: Build and Push Agent Image
```bash
cd ../../strands-agent

# Create ECR repository
aws ecr create-repository --repository-name strands-agent --region us-east-1 || true

# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 940019131157.dkr.ecr.us-east-1.amazonaws.com

# Build and push
docker build -t strands-agent:latest .
docker tag strands-agent:latest 940019131157.dkr.ecr.us-east-1.amazonaws.com/strands-agent:latest
docker push 940019131157.dkr.ecr.us-east-1.amazonaws.com/strands-agent:latest
```

## Step 10: Update Agent Deployment
Edit `strands-agent/deployment/deployment.yaml`:

**Line 6:** Get IAM role ARN:
```bash
kubectl get secret agent-core-outputs -n agent-core-infra -o jsonpath='{.data.strands_agent_role_arn}' | base64 -d
```
Update the annotation:
```yaml
annotations:
  eks.amazonaws.com/role-arn: "arn:aws:iam::940019131157:role/agent-core-poc-strands-agent-role"
```

**Line 21:** Update image:
```yaml
image: 940019131157.dkr.ecr.us-east-1.amazonaws.com/strands-agent:latest
```

## Step 11: Deploy Strands Agent
```bash
cd deployment
kubectl apply -k .
```

## Step 12: Verify Deployment
```bash
# Check pod status
kubectl get pods -l app=strands-agent

# View logs
kubectl logs -l app=strands-agent -f
```

You should see the weather agent example running!

## Troubleshooting

**Check Tofu Controller:**
```bash
kubectl logs -n flux-system -l app.kubernetes.io/name=tf-controller -f
```

**Check Terraform status:**
```bash
kubectl describe terraform agent-core-components -n agent-core-infra
```

**Check Agent pod:**
```bash
kubectl describe pod -l app=strands-agent
kubectl logs -l app=strands-agent
```

**Verify IRSA:**
```bash
kubectl exec -n flux-system deployment/tf-controller -- aws sts get-caller-identity
kubectl exec -it deployment/strands-agent -- aws sts get-caller-identity
```

## Summary
✅ ArgoCD installed  
✅ FluxCD + Tofu Controller deployed with IRSA  
✅ Terraform creates Agent Core components (Memory, Browser, Code Interpreter)  
✅ Strands Agent deployed on EKS with IRSA  
✅ Agent invokes Agent Core components via Bedrock APIs  

No static AWS credentials needed anywhere! 🎉
