#!/bin/bash
set -e

# Load values from values.yaml
VERSION=$(yq eval '.version' values.yaml)
PROJECT_NAME=$(yq eval '.projectName' values.yaml)
AWS_REGION=$(yq eval '.awsRegion' values.yaml)
EKS_CLUSTER=$(yq eval '.eksClusterName' values.yaml)
NETWORK_MODE=$(yq eval '.networkMode' values.yaml)
ENABLE_MEMORY=$(yq eval '.capabilities.memory' values.yaml)
ENABLE_BROWSER=$(yq eval '.capabilities.browser' values.yaml)
ENABLE_CODE_INTERPRETER=$(yq eval '.capabilities.codeInterpreter' values.yaml)
NAMESPACE=$(yq eval '.namespace' values.yaml)

echo "=========================================="
echo "Generating manifests for version: $VERSION"
echo "Project name: $PROJECT_NAME"
echo "=========================================="
echo ""

# Create version-specific directories
mkdir -p "terraform/tofu-controller-crds-${VERSION}"
mkdir -p "strands-agent/deployment-${VERSION}"
mkdir -p "gitops/agent-core-${VERSION}-stack"
mkdir -p "argocd"

# Generate Terraform Resource
cat > "terraform/tofu-controller-crds-${VERSION}/terraform-resource.yaml" <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: ${NAMESPACE}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: agent-core-terraform-${VERSION}
  namespace: ${NAMESPACE}
spec:
  interval: 1m
  url: https://github.com/elamaran11/eks-agent-core-pocs
  ref:
    branch: main
---
apiVersion: infra.contrib.fluxcd.io/v1alpha2
kind: Terraform
metadata:
  name: agent-core-components-${VERSION}
  namespace: ${NAMESPACE}
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  interval: 1m
  path: ./terraform/agent-core-components
  sourceRef:
    kind: GitRepository
    name: agent-core-terraform-${VERSION}
  vars:
    - name: aws_region
      value: ${AWS_REGION}
    - name: project_name
      value: ${PROJECT_NAME}
    - name: eks_cluster_name
      value: ${EKS_CLUSTER}
    - name: network_mode
      value: ${NETWORK_MODE}
    - name: enable_memory
      value: ${ENABLE_MEMORY}
    - name: enable_browser
      value: ${ENABLE_BROWSER}
    - name: enable_code_interpreter
      value: ${ENABLE_CODE_INTERPRETER}
  writeOutputsToSecret:
    name: agent-core-outputs-${VERSION}
  destroyResourcesOnDeletion: true
  approvePlan: auto
EOF

cat > "terraform/tofu-controller-crds-${VERSION}/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
- terraform-resource.yaml
EOF

# Generate Agent Deployment
cat > "strands-agent/deployment-${VERSION}/deployment.yaml" <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: strands-agent-${VERSION}
  namespace: ${NAMESPACE}
  annotations:
    argocd.argoproj.io/sync-wave: "1"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: strands-agent-${VERSION}
  template:
    metadata:
      labels:
        app: strands-agent-${VERSION}
    spec:
      serviceAccountName: strands-agent-sa-${PROJECT_NAME}
      containers:
      - name: strands-agent
        image: 940019131157.dkr.ecr.us-east-1.amazonaws.com/strands-agent:latest
        imagePullPolicy: Always
        env:
        - name: AWS_REGION
          value: "${AWS_REGION}"
        - name: BROWSER_ID
          valueFrom:
            secretKeyRef:
              name: agent-core-outputs-${VERSION}
              key: browser_id
              optional: true
        - name: CODE_INTERPRETER_ID
          valueFrom:
            secretKeyRef:
              name: agent-core-outputs-${VERSION}
              key: code_interpreter_id
              optional: true
        - name: MEMORY_ID
          valueFrom:
            secretKeyRef:
              name: agent-core-outputs-${VERSION}
              key: memory_id
              optional: true
        - name: RESULTS_BUCKET
          valueFrom:
            secretKeyRef:
              name: agent-core-outputs-${VERSION}
              key: results_bucket_name
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: strands-agent-sa-${PROJECT_NAME}
  namespace: ${NAMESPACE}
EOF

cat > "strands-agent/deployment-${VERSION}/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
- deployment.yaml
EOF

# Generate GitOps consolidated manifests
cp "terraform/tofu-controller-crds-${VERSION}/terraform-resource.yaml" "gitops/agent-core-${VERSION}-stack/"
cp "strands-agent/deployment-${VERSION}/deployment.yaml" "gitops/agent-core-${VERSION}-stack/"

cat > "gitops/agent-core-${VERSION}-stack/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: ${NAMESPACE}

resources:
- terraform-resource.yaml
- deployment.yaml
EOF

# Generate ArgoCD Application
cat > "argocd/agent-core-${VERSION}-stack.yaml" <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: agent-core-${VERSION}-stack
  namespace: argocd
spec:
  project: default
  
  source:
    repoURL: https://github.com/elamaran11/eks-agent-core-pocs
    targetRevision: main
    path: gitops/agent-core-${VERSION}-stack
  
  destination:
    server: https://kubernetes.default.svc
    namespace: ${NAMESPACE}
  
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
    
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
EOF

echo ""
echo "✅ Generated manifests for ${VERSION}:"
echo "  - terraform/tofu-controller-crds-${VERSION}/"
echo "  - strands-agent/deployment-${VERSION}/"
echo "  - gitops/agent-core-${VERSION}-stack/"
echo "  - argocd/agent-core-${VERSION}-stack.yaml"
echo ""
echo "Next steps:"
echo "1. Review generated files"
echo "2. Commit and push to Git"
echo "3. Deploy: kubectl apply -f argocd/agent-core-${VERSION}-stack.yaml"
echo ""
