# Parameterized Agent Core Deployment

This directory contains configurations for deploying Agent Core capabilities with flexible on/off toggles.

## Quick Start

### Option 1: Using ArgoCD Application (Recommended)

Edit `argocd/agent-core-stack-application.yaml` and modify the parameters:

```yaml
helm:
  parameters:
  - name: enable_memory
    value: "true"    # Set to "false" to disable
  - name: enable_browser
    value: "true"    # Set to "false" to disable
  - name: enable_code_interpreter
    value: "true"    # Set to "false" to disable
```

Then apply:
```bash
kubectl apply -f argocd/agent-core-stack-application.yaml
```

### Option 2: Using Kustomize Overlays

Choose a pre-configured overlay:

**Full Stack (all capabilities):**
```bash
kubectl apply -k terraform/tofu-controller-crds/overlays/full-stack/
```

**Browser Only:**
```bash
kubectl apply -k terraform/tofu-controller-crds/overlays/browser-only/
```

**Code Interpreter Only:**
```bash
kubectl apply -k terraform/tofu-controller-crds/overlays/code-interpreter-only/
```

### Option 3: Direct Terraform Resource Edit

Edit `terraform/tofu-controller-crds/terraform-resource.yaml`:

```yaml
vars:
  - name: enable_memory
    value: true    # Change to false to disable
  - name: enable_browser
    value: true    # Change to false to disable
  - name: enable_code_interpreter
    value: true    # Change to false to disable
```

Then apply:
```bash
kubectl apply -f terraform/tofu-controller-crds/terraform-resource.yaml
```

## How It Works

1. **Configuration Parameters** flow from ArgoCD → Terraform Resource → Terraform Modules
2. **Terraform Modules** use `count` conditionals to create resources only when enabled
3. **Agent Deployment** uses `optional: true` for secret keys, so missing capabilities don't break deployment
4. **Agent Code** checks environment variables and gracefully handles missing capabilities

## Capability Matrix

| Capability | Environment Variable | Use Case |
|-----------|---------------------|----------|
| Memory | `MEMORY_ID` | Store user preferences and conversation context |
| Browser | `BROWSER_ID` | Web scraping and site interaction |
| Code Interpreter | `CODE_INTERPRETER_ID` | Execute Python code for data analysis |

## Reverting to Original Setup

To revert to the original working configuration:

```bash
# Set all capabilities to true
kubectl patch terraform agent-core-components -n agent-core-infra --type=json -p='[
  {"op": "replace", "path": "/spec/vars/4/value", "value": true},
  {"op": "replace", "path": "/spec/vars/5/value", "value": true},
  {"op": "replace", "path": "/spec/vars/6/value", "value": true}
]'
```

Or simply use the original `terraform-resource.yaml` with all values set to `true`.

## Verification

Check which capabilities are enabled:

```bash
# Check Terraform variables
kubectl get terraform agent-core-components -n agent-core-infra -o jsonpath='{.spec.vars}'

# Check agent logs to see enabled capabilities
kubectl logs -n agent-core-infra deployment/strands-agent | grep "Enabled Capabilities"
```

Expected output:
```
🔧 Enabled Capabilities:
  Browser: ✅
  Code Interpreter: ✅
  Memory: ✅
```
