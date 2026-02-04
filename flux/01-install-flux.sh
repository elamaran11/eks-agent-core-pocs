#!/bin/bash
set -e

echo "=== Installing ArgoCD, Flux and Tofu Controller ==="

# Install ArgoCD
echo "Installing ArgoCD..."
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml --server-side --force-conflicts

echo "Waiting for ArgoCD to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd

# Install Flux via ArgoCD
echo "Installing Flux via ArgoCD..."
kubectl apply -f ../argocd/fluxcd-application.yaml

echo "Waiting for flux-system namespace..."
until kubectl get namespace flux-system &> /dev/null; do
  echo "Waiting for ArgoCD to create flux-system namespace..."
  sleep 5
done

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
echo "ArgoCD: kubectl get pods -n argocd"
echo "Flux: kubectl get pods -n flux-system"
echo "Tofu: kubectl get pods -n flux-system -l app.kubernetes.io/name=tf-controller"
