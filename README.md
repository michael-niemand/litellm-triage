# litellm-triage

Content-aware privacy routing guardrail for LiteLLM. Automatically routes sensitive requests (PII, health data, credentials) to local models while allowing non-sensitive queries to use cloud providers.

## Architecture

```
                                    +------------------+
                                    |   Cloud Model    |
                                    |   (e.g. GPT-4o)  |
                                    +--------^---------+
                                             |
                                             | non-sensitive
+--------+    +------------------+    +------+------+
| Client +--->| TriageGuardrail  +--->|   Router    |
+--------+    +--------+---------+    +------+------+
                       |                     |
              +--------v---------+           | sensitive
              |   Classifiers    |           |
              |                  |           v
              | +-------------+  |    +------+------+
              | |  Presidio   |  |    | Local Model |
              | | (fast PII)  |  |    | (e.g. Llama)|
              | +------+------+  |    +-------------+
              |        |         |
              |        v         |
              | +-------------+  |
              | | Local LLM   |  |
              | | (semantic)  |  |
              | +-------------+  |
              +------------------+
```

## Quick Start

1. Start the services:
   ```bash
   docker compose up
   ```

2. Pull the classifier model (first time only):
   ```bash
   docker exec -it litellm-triage-ollama-1 ollama pull llama3.2:1b
   docker exec -it litellm-triage-ollama-1 ollama pull llama3
   ```

3. Send requests to LiteLLM on `http://localhost:4000`:
   ```bash
   curl http://localhost:4000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "gpt-4o",
       "messages": [{"role": "user", "content": "What is the capital of France?"}]
     }'
   ```

   Sensitive content is automatically routed to the local model:
   ```bash
   curl http://localhost:4000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "gpt-4o",
       "messages": [{"role": "user", "content": "My SSN is 123-45-6789, help me with taxes"}]
     }'
   ```

## LiteLLM Configuration

Add the guardrail to your `config.yaml`:

```yaml
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY

  - model_name: ollama/llama3
    litellm_params:
      model: ollama/llama3
      api_base: http://ollama:11434

guardrails:
  - guardrail_name: "triage"
    litellm_params:
      guardrail: litellm_triage.guardrail.TriageGuardrail
      mode: "pre_call"
      sensitive_model: "ollama/llama3"
      public_model: "gpt-4o"
      classifier: "hybrid"
      threshold: 0.6
      presidio_url: "http://presidio-analyzer:3000"
      ollama_url: "http://ollama:11434"
      ollama_classifier_model: "llama3.2:1b"

general_settings:
  guardrails_on_all_requests: true
```

## Classifier Options

| Classifier   | Latency | Accuracy | Description |
|--------------|---------|----------|-------------|
| `presidio`   | ~5-20ms | Good for PII | Fast regex/NLP-based detection of names, emails, SSNs, credit cards, etc. |
| `local_llm`  | ~100-500ms | Best semantic | Semantic understanding of sensitive context (health, financial, confidential) |
| `hybrid`     | ~5-500ms | Best overall | Presidio first (fast path), escalates to local LLM if no PII detected |

### Threshold

The `threshold` parameter (0.0-1.0) controls sensitivity:
- **Lower values (e.g., 0.4)**: More conservative, routes more to local
- **Higher values (e.g., 0.8)**: More permissive, routes more to cloud

## Installation

### As a pip package

```bash
pip install litellm-triage
```

Or install from source:

```bash
pip install -e .
```

### Development

```bash
pip install -e ".[dev]"
pytest
```

## Observability

The guardrail injects metadata into each request for observability:

```json
{
  "metadata": {
    "triage": {
      "score": 0.85,
      "decision": "local",
      "classifier_stage": "presidio",
      "entities": ["PERSON", "EMAIL_ADDRESS"],
      "latency_ms": 12.5,
      "total_latency_ms": 15.2
    }
  }
}
```

This integrates with LiteLLM's built-in observability (Langfuse, OpenTelemetry, etc.).

## Environment Variables

- `OPENAI_API_KEY`: API key for OpenAI (cloud model)
- `ANTHROPIC_API_KEY`: API key for Anthropic (alternative cloud model)

## License

MIT
