# Agent Core POC on EKS with FluxCD and Tofu Controller

## Architecture Overview

This POC demonstrates using EKS as an Agent Runtime platform with Agent Core components:

```
┌─────────────────────────────────────────────────────────────┐
│                    EKS Dev Cluster                          │
│                                                             │
│  ┌──────────────┐      ┌─────────────────────────────┐   │
│  │   FluxCD     │─────▶│   Tofu Controller           │   │
│  └──────────────┘      └─────────────────────────────┘   │
│         │                        │                         │
│         │                        ▼                         │
│         │              ┌──────────────────┐               │
│         │              │ Terraform CRDs   │               │
│         │              │ (provisions AWS) │               │
│         │              └──────────────────┘               │
│         │                        │                         │
│         ▼                        │                         │
│  ┌──────────────────────────────┼─────────────────────┐  │
│  │         Strands Agent Pod     │                     │  │
│  │  ┌────────────────────────────▼──────────────────┐ │  │
│  │  │  Environment Variables:                       │ │  │
│  │  │  - AGENT_MEMORY_ARN                          │ │  │
│  │  │  - CODE_INTERPRETER_ARN                      │ │  │
│  │  │  - BROWSER_ARN                               │ │  │
│  │  └───────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────────┐
              │      AWS us-west-2         │
              │  ┌──────────────────────┐  │
              │  │ Agent Core Memory    │  │
              │  ├──────────────────────┤  │
              │  │ Agent Core Browser   │  │
              │  ├──────────────────────┤  │
              │  │ Code Interpreter     │  │
              │  └──────────────────────┘  │
              └────────────────────────────┘
```

## Components

1. **FluxCD**: GitOps operator for continuous delivery
2. **Tofu Controller**: Manages Terraform resources via Kubernetes CRDs
3. **Agent Core Infrastructure**: Terraform code for Memory, Browser, Code Interpreter
4. **Strands Agent**: Containerized agent running on EKS

## Directory Structure

```
.
├── README.md
├── argocd/
│   ├── README.md
│   ├── fluxcd-application.yaml
│   ├── tofu-controller-application.yaml
│   └── kustomization.yaml
├── flux/
│   └── 01-install-flux.sh (deprecated - use ArgoCD)
├── terraform/
│   ├── agent-core-components/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── versions.tf
│   └── tofu-controller-crds/
│       ├── terraform-resource.yaml
│       └── kustomization.yaml
├── strands-agent/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── agent.py
│   └── deployment/
│       ├── deployment.yaml
│       ├── configmap.yaml
│       └── kustomization.yaml
└── docs/
    └── deployment-guide.md
```

## Quick Start

### Prerequisites
- EKS cluster named "dev" with kubectl access
- ArgoCD installed on the cluster
- AWS credentials configured
- GitHub repository for GitOps

### Step 1: Install FluxCD and Tofu Controller via ArgoCD
```bash
cd argocd
kubectl apply -k .
```

### Step 2: Deploy Agent Core Infrastructure
```bash
cd terraform/tofu-controller-crds
kubectl apply -k .
```

### Step 3: Build and Deploy Strands Agent
```bash
cd strands-agent
docker build -t strands-agent:latest .
kubectl apply -k deployment/
```

## Next Steps
See [docs/deployment-guide.md](docs/deployment-guide.md) for detailed instructions.
