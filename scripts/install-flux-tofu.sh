#!/bin/bash
set -e

echo "=== Installing Flux and Tofu Controller ==="

# Install Flux
echo "Installing Flux components..."
kubectl apply -f https://github.com/fluxcd/flux2/releases/latest/download/install.yaml

echo "Waiting for Flux to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/source-controller -n flux-system
kubectl wait --for=condition=available --timeout=300s deployment/notification-controller -n flux-system

# Install Tofu Controller via ArgoCD
echo "Installing Tofu Controller via ArgoCD..."
kubectl apply -f ../argocd/tofu-controller-application.yaml

echo "Waiting for Tofu Controller..."
sleep 10
kubectl get pods -n flux-system -l app.kubernetes.io/name=tf-controller

echo ""
echo "=== Installation Complete ==="
echo "Flux: kubectl get pods -n flux-system"
echo "Tofu: kubectl get pods -n flux-system -l app.kubernetes.io/name=tf-controller"
