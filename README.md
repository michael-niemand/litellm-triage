# litellm-triage

Content-aware privacy routing guardrail for LiteLLM. Classifies incoming prompts and automatically reroutes sensitive requests (PII, health data, credentials, financial data) to a **local model**, while letting safe queries flow to cloud providers.

Drop it into any LiteLLM deployment as a single guardrail. Zero changes to your application code.

## How it works

```
+--------+    +----------------------+
| Client +--->|   LiteLLM Proxy      |
+--------+    |                      |
              |  TriageGuardrail     |  ← fires on every request
              |  ┌───────────────┐   |
              |  │  Presidio     │   |  Stage 1: fast PII scan (~10–20ms)
              |  │  (names, SSN, │   |  catches: names, SSNs, emails,
              |  │  cards, email)│   |  credit cards, medical IDs, ...
              |  └──────┬────────┘   |
              |         │ ambiguous  |
              |  ┌──────▼────────┐   |  Stage 2: local LLM semantic scan
              |  │  Local LLM    │   |  (~200–400ms, hybrid mode only)
              |  │  classifier   │   |  catches: implied health/legal/
              |  └──────┬────────┘   |  financial context without named PII
              |         │            |
              +---------|------------+
                        │
             sensitive? │ not sensitive?
                   ┌────┘      └────┐
                   ▼                ▼
             Local Model        Cloud Model
            (Ollama/Llama)     (GPT-4o etc.)
              stays on          leaves your
            your machine      infrastructure
```

## Quick Start (production — Ollama local model)

Requires Docker. Sensitive prompts stay on your machine; safe prompts go to OpenAI.

```bash
git clone git@github.com:michael-niemand/litellm-triage.git
cd litellm-triage

# Set your cloud API key
export OPENAI_API_KEY=sk-...

# Start everything: Presidio + Ollama + LiteLLM
docker compose up -d

# Pull the local model (first run only, ~2GB)
docker exec -it litellm-triage-ollama-1 ollama pull llama3
# Pull the classifier model (small, ~800MB)
docker exec -it litellm-triage-ollama-1 ollama pull llama3.2:1b

# Test — clean prompt, goes to GPT-4o
curl -s -X POST http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{"model":"cloud-model","messages":[{"role":"user","content":"What is 2+2?"}],"max_tokens":20}'

# Test — sensitive prompt, rerouted to local Llama3 (never leaves your machine)
curl -s -X POST http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{"model":"cloud-model","messages":[{"role":"user","content":"My SSN is 123-45-6789, help me with taxes"}],"max_tokens":20}'
```

## Quick Start (test — no Ollama, no GPU required)

Uses Anthropic API for both model slots to validate routing without running a local model.
Sensitive prompts route to Haiku (cheap/fast), safe prompts to Sonnet. **Both are still cloud** — this is for testing routing logic only.

```bash
git clone git@github.com:michael-niemand/litellm-triage.git
cd litellm-triage

export ANTHROPIC_API_KEY=sk-ant-...

# Start Presidio + LiteLLM only (no Ollama)
docker compose -f docker-compose.test.yml up -d

# Wait ~15s for services to be healthy

# Clean prompt — STAYS on Sonnet (score=0.00, no PII)
curl -s -X POST http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ANTHROPIC_API_KEY" \
  -d '{"model":"cloud-model","messages":[{"role":"user","content":"What is 2+2?"}],"max_tokens":20}'

# Sensitive prompt — REROUTED to Haiku (score=0.85, entity=PERSON)
curl -s -X POST http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ANTHROPIC_API_KEY" \
  -d '{"model":"cloud-model","messages":[{"role":"user","content":"My name is John Smith, SSN 123-45-6789"}],"max_tokens":20}'
```

## LiteLLM Config

```yaml
guardrails:
  - guardrail_name: "triage"
    litellm_params:
      guardrail: litellm_triage.guardrail.TriageGuardrail
      mode: "pre_call"
      default_on: true

      # ⚠️  Use provider model strings, NOT LiteLLM group names.
      # The hook fires inside litellm.acompletion() after group names are resolved.
      sensitive_model: "ollama/llama3"           # stays local
      public_model: "openai/gpt-4o"             # goes to cloud

      classifier: "hybrid"   # presidio | local_llm | hybrid
      threshold: 0.85
      presidio_url: "http://presidio-analyzer:3000"
      ollama_url: "http://ollama:11434"
      ollama_classifier_model: "llama3.2:1b"
```

> **Note:** `sensitive_model` and `public_model` must be provider model strings
> (e.g. `"ollama/llama3"`, `"anthropic/claude-haiku-4-5-20251001"`) — not LiteLLM
> router group names. This is a consequence of where the guardrail hook fires in
> LiteLLM's call stack (after router resolution). See [Known Issues](#known-issues).

## Classifier Options

| Mode | Latency | What it catches |
|---|---|---|
| `presidio` | ~10–20ms | Named PII: names, SSNs, emails, credit cards, medical IDs, phone numbers |
| `local_llm` | ~200–400ms | Semantic sensitivity: implied health/legal/financial context without named PII |
| `hybrid` *(recommended)* | ~10–400ms | Presidio fast path → local LLM escalation for ambiguous cases |

**Threshold (0.0–1.0):** Presidio confidence required to classify as sensitive.
- `0.85` (default) — good balance; avoids false positives on place names ("France" scores 0.85 as LOCATION)
- Lower values increase sensitivity but raise false positive rate

## Observability

Every request gets triage metadata injected into `metadata.triage`, which rides LiteLLM's built-in OTel/Langfuse pipeline:

```json
{
  "metadata": {
    "triage": {
      "score": 0.85,
      "decision": "local",
      "classifier_stage": "presidio",
      "entities": ["PERSON", "US_SSN"],
      "latency_ms": 14.2,
      "total_latency_ms": 16.8
    }
  }
}
```

## Kubernetes / Helm

Deploy the full stack on Kubernetes with GPU-aware Ollama scheduling:

```bash
helm install litellm-triage ./helm/litellm-triage \
  --set apiKeys.openai=sk-... \
  --set cloudModel.model=openai/gpt-4o
```

With GPU support:

```bash
helm install litellm-triage ./helm/litellm-triage \
  --set apiKeys.openai=sk-... \
  --set ollama.gpu.enabled=true \
  --set "ollama.gpu.nodeSelector.nvidia\.com/gpu\.present=true"
```

See [helm/litellm-triage/README.md](helm/litellm-triage/README.md) for full documentation.

## Installation

```bash
# From PyPI (once published)
pip install litellm-triage

# From source
pip install -e .

# Development
pip install -e ".[dev]"
pytest
```

## Known Issues

### `default_on: true` ignored by LiteLLM (upstream bug)

LiteLLM's `async_pre_call_deployment_hook` bails early if `guardrails` is absent from
the request kwargs, before checking `default_on`. This plugin overrides that method to
fix the behaviour. A bug report against LiteLLM is pending.

### Provider model strings required

`sensitive_model` / `public_model` must be provider model strings, not router group names,
because the hook fires inside `litellm.acompletion()` after the router has already resolved
group names to deployments. Rewriting to a group name at that point causes a routing error.

## License

MIT
