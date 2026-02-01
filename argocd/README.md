# ArgoCD Deployment

This directory contains ArgoCD Application manifests for deploying FluxCD and Tofu Controller.

## Prerequisites

ArgoCD must be installed on your cluster:

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

## Applications

### 1. FluxCD (flux2 v2.12.4)
- Minimal installation with only source-controller and notification-controller
- Used for GitOps synchronization with Tofu Controller

### 2. Tofu Controller (v0.16.0-rc.4)
- Latest stable release candidate
- Includes AWS package for Terraform AWS provider
- Watches all namespaces
- Allows cross-namespace references

## Deployment

```bash
kubectl apply -k .
```

## Verify

```bash
# Check ArgoCD Applications
kubectl get applications -n argocd

# Check FluxCD pods
kubectl get pods -n flux-system

# Check Tofu Controller
kubectl get pods -n flux-system -l app.kubernetes.io/name=tf-controller
```

## Version Notes

- **Tofu Controller**: Using v0.16.0-rc.4 (latest as of deployment)
- **FluxCD**: Using v2.12.4 (stable release)

To check for newer versions:
- Tofu Controller: https://github.com/flux-iac/tofu-controller/releases
- FluxCD: https://github.com/fluxcd/flux2/releases
