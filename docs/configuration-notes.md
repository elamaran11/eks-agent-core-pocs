# Configuration Notes

## Required Customizations

Before deploying, you must customize the following files:

### 1. terraform/tofu-controller-crds/terraform-resource.yaml

```yaml
# Line 12-14: AWS Credentials
stringData:
  AWS_ACCESS_KEY_ID: "YOUR_AWS_ACCESS_KEY"        # Replace with your AWS access key
  AWS_SECRET_ACCESS_KEY: "YOUR_AWS_SECRET_KEY"    # Replace with your AWS secret key
  AWS_REGION: "us-west-2"                         # Change region if needed

# Line 24: EKS OIDC Provider
eks_oidc_provider = "oidc.eks.us-west-2.amazonaws.com/id/YOUR_CLUSTER_OIDC_ID"
# Get this value with:
# aws eks describe-cluster --name dev --query "cluster.identity.oidc.issuer" --output text | sed 's|https://||'

# Line 32: GitHub Repository
url: https://github.com/YOUR_USERNAME/agent-core-pocs
# Replace YOUR_USERNAME with your GitHub username
```

### 2. strands-agent/deployment/deployment.yaml

```yaml
# Line 6: IAM Role ARN
annotations:
  eks.amazonaws.com/role-arn: "arn:aws:iam::ACCOUNT_ID:role/agent-core-poc-strands-agent-role"
# Replace ACCOUNT_ID with your AWS account ID
# This value will be available after Terraform execution in the agent-core-outputs secret

# Line 21: Container Image
image: strands-agent:latest
# If using ECR, replace with:
# image: ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com/strands-agent:latest
```

### 3. flux/01-install-flux.sh

When running this script, you'll be prompted for:
- **GitHub username**: Your GitHub account username
- **GitHub repository**: Name of the repository (e.g., "agent-core-pocs")
- **GitHub token**: Personal access token with repo permissions

Create a GitHub token at: https://github.com/settings/tokens

Required scopes:
- `repo` (Full control of private repositories)

## AWS Permissions Required

The AWS credentials used must have permissions to create:

- **IAM**: Roles and policies
- **Lambda**: Functions and execution roles
- **Bedrock**: Knowledge bases and model access
- **OpenSearch Serverless**: Collections and access policies
- **EKS**: OIDC provider integration

Recommended: Use an IAM user with AdministratorAccess for POC purposes.

## EKS Cluster Requirements

Your EKS cluster must have:

1. **OIDC Provider**: Enabled for IRSA
   ```bash
   eksctl utils associate-iam-oidc-provider --cluster=dev --approve
   ```

2. **kubectl Access**: Current context set to "dev"
   ```bash
   kubectl config use-context dev
   ```

3. **Sufficient Resources**: At least 1 node with 1 CPU and 1GB memory available

## GitHub Repository Setup

1. Create a new repository on GitHub (public or private)
2. Initialize it with a README (optional)
3. Clone the repository locally or push this code to it
4. Ensure the repository structure matches:
   ```
   agent-core-pocs/
   ├── terraform/
   │   └── agent-core-components/
   ├── strands-agent/
   └── ...
   ```

## Secrets Management

### Option 1: Kubernetes Secrets (Current)

AWS credentials stored in Kubernetes Secret:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: aws-credentials
  namespace: agent-core-infra
type: Opaque
stringData:
  AWS_ACCESS_KEY_ID: "..."
  AWS_SECRET_ACCESS_KEY: "..."
```

### Option 2: AWS Secrets Manager (Recommended for Production)

Use External Secrets Operator to sync from AWS Secrets Manager:
```bash
helm install external-secrets external-secrets/external-secrets -n external-secrets-system --create-namespace
```

### Option 3: IRSA for Tofu Controller (Most Secure)

Configure Tofu Controller to use IRSA instead of static credentials.

## Environment-Specific Configurations

### Development
- Single replica for Strands Agent
- Smaller Lambda memory sizes
- Auto-approve Terraform plans

### Production
- Multiple replicas with HPA
- Larger Lambda memory and timeout
- Manual approval for Terraform plans
- Enable Terraform state locking with DynamoDB

## Monitoring and Logging

### CloudWatch Logs
Lambda functions automatically log to CloudWatch:
```bash
aws logs tail /aws/lambda/agent-core-poc-code-interpreter --follow
aws logs tail /aws/lambda/agent-core-poc-browser --follow
```

### Kubernetes Logs
```bash
# Strands Agent logs
kubectl logs -l app=strands-agent -f

# Tofu Controller logs
kubectl logs -n tofu-system -l app=tofu-controller -f

# FluxCD logs
kubectl logs -n flux-system -l app=source-controller -f
```

### Bedrock Metrics
Monitor Bedrock usage in CloudWatch:
- Model invocations
- Knowledge base queries
- Token usage

## Cost Considerations

Estimated monthly costs (us-west-2):

- **Lambda**: ~$5-10 (based on invocations)
- **OpenSearch Serverless**: ~$700 (minimum OCU charges)
- **Bedrock**: Variable (based on token usage)
- **EKS**: Existing cluster (no additional cost)

**Note**: OpenSearch Serverless has minimum OCU charges. For cost optimization, consider using Amazon OpenSearch Service with t3.small instances instead.

## Troubleshooting Common Issues

### Issue: Tofu Controller can't access Git repository
**Solution**: Ensure git-credentials secret is created with valid GitHub token

### Issue: Lambda functions fail with "File not found"
**Solution**: Ensure code_interpreter.zip and browser.zip are in terraform/agent-core-components/

### Issue: Agent pod can't assume IAM role
**Solution**: Verify OIDC provider is configured and role trust policy is correct

### Issue: Bedrock access denied
**Solution**: Ensure Bedrock model access is enabled in AWS Console → Bedrock → Model access

## Next Steps After Deployment

1. **Populate Memory**: Add documents to the Knowledge Base
2. **Enhance Lambda Functions**: Implement full code execution and browser automation
3. **Add Monitoring**: Set up CloudWatch dashboards and alarms
4. **Implement CI/CD**: Automate Docker image builds and deployments
5. **Security Hardening**: Implement network policies, pod security policies
