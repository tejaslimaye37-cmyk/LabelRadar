"""Tests for configuration and logging."""

from app.core.config import Settings
from app.core.logging import setup_logging


def test_settings_async_database_url_default():
    s = Settings(
        _env_file=None,
        DATABASE_URL=None,
        POSTGRES_USER="user",
        POSTGRES_PASSWORD="pwd",
        POSTGRES_HOST="dbhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="dbname",
    )
    assert s.async_database_url == "postgresql+asyncpg://user:pwd@dbhost:5432/dbname"


def test_settings_async_database_url_override_postgresql_prefix():
    s = Settings(
        _env_file=None,
        DATABASE_URL="postgresql://custom_user:custom_pwd@remote:5433/custom_db",
    )
    assert s.async_database_url == "postgresql+asyncpg://custom_user:custom_pwd@remote:5433/custom_db"


def test_settings_async_database_url_override_already_asyncpg():
    s = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://custom_user:custom_pwd@remote:5433/custom_db",
    )
    assert s.async_database_url == "postgresql+asyncpg://custom_user:custom_pwd@remote:5433/custom_db"


def test_setup_logging():
    logger_debug = setup_logging(debug=True)
    assert logger_debug.name == "labelradar"
    logger_info = setup_logging(debug=False)
    assert logger_info.name == "labelradar"
