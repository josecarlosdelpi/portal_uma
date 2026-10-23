"""An unconfigured provider must never authenticate anyone."""
from fastapi import HTTPException
from app.auth import verify_identity
from app.config import Settings


def test_missing_identity_config_rejects_all_tokens():
    settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost/test",
        oidc_issuer="", oidc_audience="", oidc_jwks_url="",
    )
    try:
        verify_identity("untrusted-token", settings)
        assert False, "Expected failure"
    except HTTPException as error:
        assert error.status_code == 503
