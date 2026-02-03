# How Sync Waves and Health Checks Work Together

## The Complete Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. YOU APPLY: kubectl apply -f argocd/agent-core-v4-stack.yaml │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. ArgoCD Application Created                                   │
│    Name: agent-core-v4-stack                                    │
│    Source: gitops/agent-core-v4-stack/                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. ArgoCD Reads Kustomization                                   │
│    Path: gitops/agent-core-v4-stack/kustomization.yaml         │
│                                                                 │
│    Resources to deploy:                                         │
│    - terraform/tofu-controller-crds-v4/terraform-resource.yaml  │
│    - strands-agent/deployment-v4/deployment.yaml                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. ArgoCD Reads Sync Wave Annotations                          │
│                                                                 │
│    File: terraform-resource.yaml                                │
│    ┌─────────────────────────────────────────────────────┐     │
│    │ metadata:                                           │     │
│    │   annotations:                                      │     │
│    │     argocd.argoproj.io/sync-wave: "0"  ← WAVE 0    │     │
│    └─────────────────────────────────────────────────────┘     │
│                                                                 │
│    File: deployment.yaml                                        │
│    ┌─────────────────────────────────────────────────────┐     │
│    │ metadata:                                           │     │
│    │   annotations:                                      │     │
│    │     argocd.argoproj.io/sync-wave: "1"  ← WAVE 1    │     │
│    └─────────────────────────────────────────────────────┘     │
│                                                                 │
│ ArgoCD Decision: Deploy wave 0 first, then wave 1              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
╔═════════════════════════════════════════════════════════════════╗
║ 5. WAVE 0 DEPLOYMENT STARTS                                     ║
╚═════════════════════════════════════════════════════════════════╝
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. ArgoCD Creates Resources from Wave 0                        │
│    - Namespace: agent-core-infra                                │
│    - GitRepository: agent-core-terraform-v4                     │
│    - Terraform CR: agent-core-components-v4                     │
│                                                                 │
│ Status: Wave 0 resources "Synced" ✓                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. ArgoCD Checks Health of Wave 0 Resources                    │
│                                                                 │
│    For Terraform CR: agent-core-components-v4                   │
│    ArgoCD looks up health check in ConfigMap                    │
│                                                                 │
│    ConfigMap: argocd-cm (namespace: argocd)                     │
│    Key: resource.customizations.health.infra.contrib.fluxcd... │
│    ┌─────────────────────────────────────────────────────┐     │
│    │ data:                                               │     │
│    │   resource.customizations.health.infra.contrib...   │     │
│    │     Terraform: |                                    │     │
│    │       hs = {}                                       │     │
│    │       if obj.status.conditions[Ready] == "True":    │     │
│    │         hs.status = "Healthy"  ← HEALTH CHECK      │     │
│    │       else:                                         │     │
│    │         hs.status = "Progressing"                   │     │
│    │       return hs                                     │     │
│    └─────────────────────────────────────────────────────┘     │
│                                                                 │
│ ArgoCD runs this Lua script every ~3 seconds                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8. Health Check Loop (runs continuously)                       │
│                                                                 │
│    ArgoCD queries Kubernetes API:                               │
│    kubectl get terraform agent-core-components-v4 -o json       │
│                                                                 │
│    Passes to Lua script as 'obj'                                │
│                                                                 │
│    Lua checks: obj.status.conditions[type=Ready].status        │
│                                                                 │
│    ┌──────────────────────────────────────────────┐            │
│    │ Iteration 1: status.conditions = nil         │            │
│    │ → Lua returns: "Progressing"                 │            │
│    │ → ArgoCD WAITS, does not start wave 1       │            │
│    └──────────────────────────────────────────────┘            │
│                                                                 │
│    ┌──────────────────────────────────────────────┐            │
│    │ Iteration 2 (30s later): Ready = "False"     │            │
│    │ → Lua returns: "Degraded"                    │            │
│    │ → ArgoCD WAITS, does not start wave 1       │            │
│    └──────────────────────────────────────────────┘            │
│                                                                 │
│    ... (Terraform running, 15-20 minutes) ...                   │
│                                                                 │
│    ┌──────────────────────────────────────────────┐            │
│    │ Iteration N (20 mins later): Ready = "True"  │            │
│    │ → Lua returns: "Healthy" ✅                  │            │
│    │ → ArgoCD: Wave 0 is HEALTHY!                │            │
│    └──────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    ✅ WAVE 0 HEALTHY ✅
                              ↓
╔═════════════════════════════════════════════════════════════════╗
║ 9. WAVE 1 DEPLOYMENT STARTS (ONLY NOW!)                        ║
╚═════════════════════════════════════════════════════════════════╝
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 10. ArgoCD Creates Resources from Wave 1                       │
│     - ServiceAccount: strands-agent-sa-v4                       │
│     - Deployment: strands-agent-v4                              │
│                                                                 │
│ Pod starts and reads from Secret: agent-core-outputs-v4         │
│ (Secret was created by Terraform in wave 0)                     │
└─────────────────────────────────────────────────────────────────┘
```

## Key Points

### Where are the sync waves?
- **Terraform CR**: Line 21 of `terraform/tofu-controller-crds-v4/terraform-resource.yaml`
  ```yaml
  annotations:
    argocd.argoproj.io/sync-wave: "0"
  ```

- **Agent Deployment**: Line 6 of `strands-agent/deployment-v4/deployment.yaml`
  ```yaml
  annotations:
    argocd.argoproj.io/sync-wave: "1"
  ```

### Where is the health check?
- **Stored in**: ConfigMap `argocd-cm` in namespace `argocd`
- **Key**: `resource.customizations.health.infra.contrib.fluxcd.io_Terraform`
- **Content**: Lua script from `argocd/terraform-health-check.yaml`
- **Executed by**: ArgoCD application-controller pod
- **Frequency**: Every ~3 seconds during sync

### How does ArgoCD know to wait?
1. ArgoCD sees wave 0 has annotation `sync-wave: "0"`
2. ArgoCD deploys wave 0 resources
3. ArgoCD checks health using the Lua script
4. If health returns "Progressing" or "Degraded" → WAIT
5. If health returns "Healthy" → Proceed to wave 1
6. ArgoCD deploys wave 1 resources

### The Critical Connection
```
Sync Wave Annotation → ArgoCD waits for health
                              ↓
Health Check Lua Script → Checks Terraform CR status
                              ↓
Terraform CR status.conditions[Ready=True] → Returns "Healthy"
                              ↓
ArgoCD proceeds to next wave
```

## Setup Required

**Before deployment, you MUST add the health check to ArgoCD:**

```bash
kubectl edit configmap argocd-cm -n argocd
```

Add this under `data:`:
```yaml
data:
  resource.customizations.health.infra.contrib.fluxcd.io_Terraform: |
    hs = {}
    if obj.status ~= nil then
      if obj.status.conditions ~= nil then
        for i, condition in ipairs(obj.status.conditions) do
          if condition.type == "Ready" and condition.status == "True" then
            hs.status = "Healthy"
            return hs
          end
          if condition.type == "Ready" and condition.status == "False" then
            hs.status = "Degraded"
            return hs
          end
        end
      end
    end
    hs.status = "Progressing"
    return hs
```

**Without this health check, ArgoCD will consider Terraform "Healthy" as soon as the CR is created, and wave 1 will start immediately (before Terraform completes)!**
