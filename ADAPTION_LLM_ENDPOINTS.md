# Adaption LLM Endpoints

Base URL: `https://api.prod.adaptionlabs.ai`

Authentication: set `ADAPTION_API_KEY` to the API key from Adaption.

## List hosted models

`GET /api/v1/models?type=hosted`

Returns the hosted models enabled for the API key. The tested model IDs are:

- `gemma-4-31b-it`
- `glm-5.2`
- `qwen3.5-397b`
- `gemma-4-26b-a4b-it`
- `qwen3.8-27b`
- `deepseek-v4-flash`
- `glm-53-flash`

## Generate a response

`POST /api/v1/responses`

Accepts a model ID and text input. It returns `output_text` and usage metadata.

## Test request

```bash
curl -sS "$ADAPTION_API_BASE/api/v1/responses" \
  -H "Authorization: Bearer $ADAPTION_API_KEY" \
  -H "Content-Type: application/json" \
  --data '{"model":"qwen3.8-27b","input":"Reply with exactly OK.","max_output_tokens":128}'
```

Set the base URL first if needed:

```bash
export ADAPTION_API_BASE="https://api.prod.adaptionlabs.ai"
```

`/model.s` is not a valid LLM endpoint; it returned `404 Cannot POST /model.s` during testing.
