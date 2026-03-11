# litellm-triage Helm Chart

Deploys the litellm-triage stack on Kubernetes: LiteLLM proxy with the triage guardrail, Presidio (analyzer + anonymizer), and Ollama for local model inference.

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+
- For GPU support: NVIDIA device plugin installed on the cluster

## Installation

### Basic Install (CPU-only Ollama)

```bash
helm install litellm-triage ./helm/litellm-triage \
  --set apiKeys.openai=sk-your-key-here \
  --set cloudModel.model=openai/gpt-4o
```

### GPU-enabled Install

For faster local model inference, enable GPU scheduling:

```bash
helm install litellm-triage ./helm/litellm-triage \
  --set apiKeys.openai=sk-your-key-here \
  --set cloudModel.model=openai/gpt-4o \
  --set ollama.gpu.enabled=true \
  --set "ollama.gpu.nodeSelector.nvidia\.com/gpu\.present=true"
```

### Using an Existing API Key Secret

If you have an existing Kubernetes secret with your API keys:

```bash
helm install litellm-triage ./helm/litellm-triage \
  --set cloudModel.apiKeySecret.name=my-existing-secret \
  --set cloudModel.apiKeySecret.key=openai-api-key \
  --set cloudModel.model=openai/gpt-4o
```

### With Anthropic Instead of OpenAI

```bash
helm install litellm-triage ./helm/litellm-triage \
  --set apiKeys.anthropic=sk-ant-your-key-here \
  --set cloudModel.model=anthropic/claude-sonnet-4-5-20250929
```

### With Ingress

```bash
helm install litellm-triage ./helm/litellm-triage \
  --set apiKeys.openai=sk-your-key-here \
  --set ingress.enabled=true \
  --set ingress.className=nginx \
  --set "ingress.hosts[0].host=litellm.example.com" \
  --set "ingress.hosts[0].paths[0].path=/" \
  --set "ingress.hosts[0].paths[0].pathType=Prefix"
```

## Testing the Deployment

Once deployed, port-forward to the LiteLLM service:

```bash
kubectl port-forward svc/litellm-triage-litellm 4000:4000
```

Test a clean prompt (goes to cloud model):

```bash
curl -s -X POST http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"cloud-model","messages":[{"role":"user","content":"What is 2+2?"}],"max_tokens":20}'
```

Test a sensitive prompt (rerouted to local Ollama):

```bash
curl -s -X POST http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"cloud-model","messages":[{"role":"user","content":"My SSN is 123-45-6789, help me with taxes"}],"max_tokens":20}'
```

## Values Reference

| Key | Description | Default |
|-----|-------------|---------|
| `global.imagePullPolicy` | Image pull policy for all containers | `IfNotPresent` |
| **LiteLLM** | | |
| `litellm.image.repository` | LiteLLM image repository | `ghcr.io/berriai/litellm` |
| `litellm.image.tag` | LiteLLM image tag | `main-latest` |
| `litellm.replicaCount` | Number of LiteLLM replicas | `1` |
| `litellm.service.type` | Service type | `ClusterIP` |
| `litellm.service.port` | Service port | `4000` |
| `litellm.masterKey` | LiteLLM master key for auth | `""` |
| `litellm.resources` | Resource requests/limits | See values.yaml |
| **Presidio Analyzer** | | |
| `presidioAnalyzer.image.repository` | Presidio Analyzer image | `mcr.microsoft.com/presidio-analyzer` |
| `presidioAnalyzer.image.tag` | Presidio Analyzer tag | `latest` |
| `presidioAnalyzer.replicaCount` | Number of replicas | `1` |
| `presidioAnalyzer.service.port` | Service port | `3000` |
| **Presidio Anonymizer** | | |
| `presidioAnonymizer.image.repository` | Presidio Anonymizer image | `mcr.microsoft.com/presidio-anonymizer` |
| `presidioAnonymizer.image.tag` | Presidio Anonymizer tag | `latest` |
| `presidioAnonymizer.replicaCount` | Number of replicas | `1` |
| `presidioAnonymizer.service.port` | Service port | `3000` |
| **Ollama** | | |
| `ollama.image.repository` | Ollama image | `ollama/ollama` |
| `ollama.image.tag` | Ollama tag | `latest` |
| `ollama.service.port` | Service port | `11434` |
| `ollama.model` | Main model for sensitive queries | `llama3` |
| `ollama.classifierModel` | Classifier model for hybrid mode | `llama3.2:1b` |
| `ollama.persistence.enabled` | Enable persistent storage | `true` |
| `ollama.persistence.size` | PVC size | `20Gi` |
| `ollama.persistence.storageClass` | Storage class (empty = default) | `""` |
| `ollama.gpu.enabled` | Enable GPU scheduling | `false` |
| `ollama.gpu.nodeSelector` | Node selector for GPU nodes | `{nvidia.com/gpu.present: "true"}` |
| `ollama.gpu.useAffinity` | Use nodeAffinity instead of nodeSelector | `false` |
| `ollama.gpu.tolerations` | Tolerations for GPU node taints | See values.yaml |
| `ollama.gpu.count` | Number of GPUs to allocate | `1` |
| **Triage Guardrail** | | |
| `triage.classifier` | Classifier strategy | `hybrid` |
| `triage.threshold` | Sensitivity threshold (0.0-1.0) | `"0.85"` |
| `triage.defaultOn` | Fire guardrail on all requests | `true` |
| **Cloud Model** | | |
| `cloudModel.model` | Provider model string for cloud | `openai/gpt-4o` |
| `cloudModel.apiKeySecret.name` | Existing secret name | `""` |
| `cloudModel.apiKeySecret.key` | Key in secret | `api-key` |
| **API Keys** | | |
| `apiKeys.openai` | OpenAI API key (creates secret) | `""` |
| `apiKeys.anthropic` | Anthropic API key (creates secret) | `""` |
| **Ingress** | | |
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.className` | Ingress class name | `""` |
| `ingress.annotations` | Ingress annotations | `{}` |
| `ingress.hosts` | Ingress hosts configuration | See values.yaml |
| `ingress.tls` | TLS configuration | `[]` |

## GPU Scheduling Options

The chart supports multiple ways to schedule Ollama on GPU nodes:

### Using nodeSelector (default)

```yaml
ollama:
  gpu:
    enabled: true
    nodeSelector:
      nvidia.com/gpu.present: "true"
```

Common node labels by cloud provider:
- **GKE:** `cloud.google.com/gke-accelerator: nvidia-tesla-t4`
- **EKS:** `k8s.amazonaws.com/accelerator: nvidia-tesla-t4`
- **AKS:** `accelerator: nvidia`
- **Bare metal with NFD:** `nvidia.com/gpu.present: "true"`

### Using nodeAffinity

For more flexible scheduling:

```yaml
ollama:
  gpu:
    enabled: true
    useAffinity: true
    affinity:
      nodeAffinity:
        requiredDuringSchedulingIgnoredDuringExecution:
          nodeSelectorTerms:
            - matchExpressions:
                - key: nvidia.com/gpu.present
                  operator: In
                  values: ["true"]
```

### Tolerations

If your GPU nodes have taints:

```yaml
ollama:
  gpu:
    enabled: true
    tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
```

## Architecture

```
                          ┌──────────────────┐
                          │     Ingress      │
                          └────────┬─────────┘
                                   │
                          ┌────────▼─────────┐
                          │  LiteLLM Proxy   │
                          │  (port 4000)     │
                          │                  │
                          │ TriageGuardrail  │
                          └───┬─────────┬────┘
                              │         │
              ┌───────────────┘         └───────────────┐
              │                                         │
    ┌─────────▼─────────┐                    ┌──────────▼────────┐
    │ Presidio Analyzer │                    │      Ollama       │
    │   (port 3000)     │                    │   (port 11434)    │
    └───────────────────┘                    │                   │
                                             │  - llama3         │
    ┌───────────────────┐                    │  - llama3.2:1b    │
    │Presidio Anonymizer│                    └───────────────────┘
    │   (port 3000)     │
    └───────────────────┘
```

## Uninstall

```bash
helm uninstall litellm-triage
```

Note: The PVC for Ollama data is not deleted automatically. To remove it:

```bash
kubectl delete pvc litellm-triage-ollama
```
