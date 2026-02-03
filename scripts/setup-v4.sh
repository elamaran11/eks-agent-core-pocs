#!/bin/bash
set -e

echo "=========================================="
echo "V4 Stack Setup Script"
echo "=========================================="
echo ""

# Check prerequisites
echo "Checking prerequisites..."

if ! kubectl get namespace argocd &> /dev/null; then
    echo "❌ ArgoCD namespace not found. Please install ArgoCD first."
    exit 1
fi

if ! kubectl get namespace flux-system &> /dev/null; then
    echo "❌ Flux-system namespace not found. Please install Tofu Controller first."
    exit 1
fi

echo "✅ Prerequisites met"
echo ""

# Configure ArgoCD health check
echo "Configuring ArgoCD health check for Terraform resources..."

# Check if argocd-cm exists
if kubectl get configmap argocd-cm -n argocd &> /dev/null; then
    echo "Found existing argocd-cm ConfigMap"
    
    # Check if health check already exists
    if kubectl get configmap argocd-cm -n argocd -o yaml | grep -q "resource.customizations.health.infra.contrib.fluxcd.io_Terraform"; then
        echo "⚠️  Terraform health check already configured, skipping..."
    else
        echo "Adding Terraform health check..."
        kubectl patch configmap argocd-cm -n argocd --type merge --patch-file argocd/argocd-cm-patch.yaml
        echo "✅ Health check configured"
        
        # Restart ArgoCD application controller to pick up changes
        echo "Restarting ArgoCD application controller..."
        kubectl rollout restart deployment argocd-application-controller -n argocd
        echo "Waiting for controller to be ready..."
        kubectl rollout status deployment argocd-application-controller -n argocd --timeout=120s
    fi
else
    echo "Creating argocd-cm ConfigMap..."
    kubectl apply -f argocd/argocd-cm-patch.yaml
    echo "✅ ConfigMap created"
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Deploy V4 stack:"
echo "   kubectl apply -f argocd/agent-core-v4-stack.yaml"
echo ""
echo "2. Monitor deployment:"
echo "   kubectl get application agent-core-v4-stack -n argocd -w"
echo ""
echo "3. Watch Terraform progress:"
echo "   kubectl get terraform agent-core-components-v4 -n agent-core-infra -w"
echo ""
