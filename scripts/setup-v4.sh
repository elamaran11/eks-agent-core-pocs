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
echo "1. Deploy namespace setup (one-time):"
echo "   kubectl apply -f argocd/agent-core-namespace-setup.yaml"
echo ""
echo "2. Deploy V4 stack:"
echo "   kubectl apply -f argocd/agent-core-v4-stack.yaml"
echo ""
echo "3. Wait for Terraform to complete (~3 minutes)"
echo "   kubectl get terraform agent-core-components-v4 -n agent-core-infra -w"
echo ""
echo "4. Create Pod Identity association:"
echo "   ./scripts/create-pod-identity-v4.sh"
echo ""
echo "5. Restart agent to pick up credentials:"
echo "   kubectl rollout restart deployment strands-agent-v4 -n agent-core-infra"
echo ""
