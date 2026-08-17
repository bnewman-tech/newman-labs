"""Prefect Secret runtime loading."""

from enum import StrEnum

from prefect.blocks.system import Secret
from pydantic import SecretStr


class PrefectSecret(StrEnum):
    """Secret blocks owned by Newman Labs."""

    DATABASE_DEV_OWNER_URL = "neon-database-dev-direct-url"
    DATABASE_DEV_WEB_URL = "neon-database-dev-web-url"
    DATABASE_PROD_OWNER_URL = "neon-database-prod-direct-url"
    DATABASE_PROD_WEB_URL = "neon-database-prod-web-url"
    INVOICE_PARSER_PASSCODE = "newman-labs-invoice-parser-passcode"
    LOGFIRE_TOKEN = "newman-labs-logfire-token"  # ruff: ignore[hardcoded-password-string] - Block name.
    OLLAMA_API_KEY = "ollama-api-key"
    PYDANTIC_AI_GATEWAY_API_KEY = "pydantic-ai-gateway-api-key"
    NEON_OBJECT_STORAGE_DEV_ENDPOINT = "neon-object-storage-dev-endpoint"
    NEON_OBJECT_STORAGE_DEV_ACCESS_KEY_ID = "neon-object-storage-dev-access-key-id"
    NEON_OBJECT_STORAGE_DEV_SECRET_ACCESS_KEY = "neon-object-storage-dev-secret-access-key"  # ruff: ignore[hardcoded-password-string] - Block name.
    NEON_OBJECT_STORAGE_PROD_ENDPOINT = "neon-object-storage-prod-endpoint"
    NEON_OBJECT_STORAGE_PROD_ACCESS_KEY_ID = "neon-object-storage-prod-access-key-id"
    NEON_OBJECT_STORAGE_PROD_SECRET_ACCESS_KEY = "neon-object-storage-prod-secret-access-key"  # ruff: ignore[hardcoded-password-string] - Block name.


async def get_secret(*, name: PrefectSecret) -> SecretStr:
    """Load one required Newman Labs credential from Prefect."""
    try:
        secret = await Secret.aload(name.value)
    except Exception as exc:
        raise RuntimeError(f"Unable to load required Prefect Secret block {name.value}.") from exc

    value = secret.get()
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Required Prefect Secret block {name.value} is empty.")
    return SecretStr(value.strip())
