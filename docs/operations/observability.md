# Observability

`libs/pydantic_ai_core/observability.py` configures Logfire once per process and
instruments Pydantic AI, embeddings, HTTPX, standard-library logging, FastAPI, and
the application SQLAlchemy engine.

The `newman-labs-logfire-token` Prefect Secret is loaded before configuration.
FastAPI startup fails closed when its managed token cannot be loaded. Standalone AI
entrypoints configure Logfire before creating a model or embedder.

Pydantic AI prompts, results, tool content, and binary content are captured. A
public document upload must disclose that behavior beside the upload action. HTTP
headers and bodies are excluded from general HTTPX capture, and credentials must
never be added to telemetry. Liveness requests are excluded from tracing.

After rotating the token, redeploy or restart the consuming process. Verify
`/health/ready`, then confirm `service.name = 'newman-labs'` in Logfire Live.
