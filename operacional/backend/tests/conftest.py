"""Isolated CI configuration. These values are never valid production credentials."""
import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://test_only:test_only@127.0.0.1:5439/portal_uma_test",
)
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("OIDC_ISSUER", "")
os.environ.setdefault("OIDC_AUDIENCE", "")
os.environ.setdefault("OIDC_JWKS_URL", "")
