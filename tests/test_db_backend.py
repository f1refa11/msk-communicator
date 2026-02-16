import sqlite3

import pytest

from db_backend import (
    CompatCursor,
    build_postgres_url_from_parts,
    initialize_schema,
    load_database_settings,
    normalize_database_url,
    redact_dsn,
)


class DummyCursor:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return self


def test_normalize_database_url_accepts_postgres_alias():
    url = "postgres://app:secret@db.example.com:5432/msk"
    assert (
        normalize_database_url(url)
        == "postgresql://app:secret@db.example.com:5432/msk"
    )


def test_load_database_settings_defaults_to_sqlite():
    settings = load_database_settings({})
    assert settings.backend == "sqlite"
    assert settings.sqlite_path == "database.db"
    assert settings.dsn == "sqlite:///database.db"


def test_load_database_settings_uses_database_url():
    settings = load_database_settings(
        {"DATABASE_URL": "postgres://app:secret@db.example.com:5432/msk"}
    )
    assert settings.backend == "postgresql"
    assert settings.dsn == "postgresql://app:secret@db.example.com:5432/msk"


def test_build_postgres_url_from_parts_with_sslmode():
    dsn = build_postgres_url_from_parts(
        {
            "POSTGRES_HOST": "db.example.com",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "msk",
            "POSTGRES_USER": "app",
            "POSTGRES_PASSWORD": "secret",
            "POSTGRES_SSLMODE": "require",
        }
    )
    assert dsn == "postgresql://app:secret@db.example.com:5432/msk?sslmode=require"


def test_build_postgres_url_from_parts_requires_full_config():
    with pytest.raises(ValueError):
        build_postgres_url_from_parts({"POSTGRES_HOST": "db.example.com"})


def test_redact_dsn_hides_password():
    dsn = "postgresql://app:secret@db.example.com:5432/msk?sslmode=require"
    assert redact_dsn(dsn) == "postgresql://app:***@db.example.com:5432/msk?sslmode=require"


def test_compat_cursor_rewrites_placeholders_for_postgres():
    dummy = DummyCursor()
    cursor = CompatCursor(dummy, backend="postgresql")

    cursor.execute("SELECT * FROM users WHERE tel = ? AND pass = ?", ("1", "2"))

    assert dummy.calls == [
        ("SELECT * FROM users WHERE tel = %s AND pass = %s", ("1", "2"))
    ]


def test_initialize_schema_creates_sqlite_tables():
    connection = sqlite3.connect(":memory:", autocommit=True)
    cursor = CompatCursor(connection.cursor(), backend="sqlite")

    initialize_schema(cursor, backend="sqlite")

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    users_table = cursor.fetchone()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tutorial_progress'"
    )
    progress_table = cursor.fetchone()

    assert users_table == ("users",)
    assert progress_table == ("tutorial_progress",)
