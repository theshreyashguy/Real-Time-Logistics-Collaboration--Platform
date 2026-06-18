"""Config safety: the app must fail closed rather than boot in production
with the well-known dev JWT secret (forgeable tokens)."""
import pytest

from app.core.config import Settings, _INSECURE_JWT_SECRET


def test_production_rejects_dev_jwt_secret():
    with pytest.raises(ValueError):
        Settings(app_env="production", jwt_secret=_INSECURE_JWT_SECRET)


def test_production_accepts_strong_secret():
    s = Settings(app_env="production", jwt_secret="a-strong-unique-secret-value")
    assert s.jwt_secret == "a-strong-unique-secret-value"


def test_development_allows_dev_secret():
    # local dev / CI stays frictionless with the placeholder
    s = Settings(app_env="development", jwt_secret=_INSECURE_JWT_SECRET)
    assert s.jwt_secret == _INSECURE_JWT_SECRET
