#!/bin/bash
set -e

echo "Deploying FluxCD and Tofu Controller via ArgoCD..."

# Check if ArgoCD is installed
if ! kubectl get namespace argocd &> /dev/null; then
    echo "Error: ArgoCD namespace not found. Please install ArgoCD first."
    echo "Install with: kubectl create namespace argocd && kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml"
    exit 1
fi

# Deploy FluxCD and Tofu Controller as ArgoCD Applications
echo "Deploying ArgoCD Applications..."
kubectl apply -k ../argocd/

echo "Waiting for applications to sync..."
sleep 5

echo "Checking ArgoCD Applications status..."
kubectl get applications -n argocd

echo "\nVerifying FluxCD installation..."
kubectl get pods -n flux-system

echo "\nDeployment complete!"
echo "Monitor with: kubectl get applications -n argocd -w"
