# Setup IRSA for Tofu Controller

## Step 1: Create IAM Policy for Tofu Controller

```bash
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

## Step 2: Create IAM Role with IRSA

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

## Step 3: Annotate Tofu Controller ServiceAccount

```bash
kubectl annotate serviceaccount tf-controller \
  -n flux-system \
  eks.amazonaws.com/role-arn=arn:aws:iam::${ACCOUNT_ID}:role/TofuControllerRole
```

## Step 4: Restart Tofu Controller

```bash
kubectl rollout restart deployment tf-controller -n flux-system
```

## Step 5: Verify IRSA

```bash
kubectl exec -n flux-system deployment/tf-controller -- aws sts get-caller-identity
```

You should see the TofuControllerRole ARN.

## Step 6: Remove AWS Credentials Secret

Now you can remove the static credentials from your Terraform CRD!
