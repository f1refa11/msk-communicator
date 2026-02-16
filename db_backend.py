from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from urllib.parse import quote_plus, urlencode, urlparse, urlunparse


@dataclass(frozen=True)
class DatabaseSettings:
    backend: str
    dsn: str
    sqlite_path: str | None = None


def normalize_database_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def build_postgres_url_from_parts(environ: Mapping[str, str]) -> str:
    host = (environ.get("POSTGRES_HOST") or "").strip()
    port = (environ.get("POSTGRES_PORT") or "5432").strip()
    database = (environ.get("POSTGRES_DB") or "").strip()
    username = (environ.get("POSTGRES_USER") or "").strip()
    password = environ.get("POSTGRES_PASSWORD") or ""
    sslmode = (environ.get("POSTGRES_SSLMODE") or "").strip()

    provided = any(
        [
            host,
            (environ.get("POSTGRES_PORT") or "").strip(),
            database,
            username,
            password,
            sslmode,
        ]
    )
    if not provided:
        return ""

    missing = [
        name
        for name, value in (
            ("POSTGRES_HOST", host),
            ("POSTGRES_DB", database),
            ("POSTGRES_USER", username),
            ("POSTGRES_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(
            "Incomplete PostgreSQL configuration. "
            f"Missing variables: {missing_text}."
        )

    dsn = (
        f"postgresql://{quote_plus(username)}:{quote_plus(password)}"
        f"@{host}:{port}/{quote_plus(database)}"
    )
    if sslmode:
        dsn = f"{dsn}?{urlencode({'sslmode': sslmode})}"
    return dsn


def load_database_settings(environ: Mapping[str, str] | None = None) -> DatabaseSettings:
    env = os.environ if environ is None else environ

    raw_database_url = normalize_database_url(env.get("DATABASE_URL") or "")
    if raw_database_url:
        if raw_database_url.startswith("postgresql://"):
            return DatabaseSettings(backend="postgresql", dsn=raw_database_url)
        if raw_database_url.startswith("sqlite:///"):
            sqlite_path = raw_database_url[len("sqlite:///") :] or "database.db"
            return DatabaseSettings(
                backend="sqlite",
                dsn=raw_database_url,
                sqlite_path=sqlite_path,
            )
        raise ValueError(
            "Unsupported DATABASE_URL scheme. Use postgresql:// or sqlite:///"
        )

    postgres_url = build_postgres_url_from_parts(env)
    if postgres_url:
        return DatabaseSettings(backend="postgresql", dsn=postgres_url)

    sqlite_path = (env.get("SQLITE_DB_PATH") or "database.db").strip() or "database.db"
    sqlite_dsn = f"sqlite:///{sqlite_path}"
    return DatabaseSettings(backend="sqlite", dsn=sqlite_dsn, sqlite_path=sqlite_path)


def redact_dsn(dsn: str) -> str:
    parsed = urlparse(dsn)
    if not parsed.scheme.startswith("postgres"):
        return dsn

    username = parsed.username or ""
    password = parsed.password
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""

    auth = ""
    if username:
        auth = quote_plus(username)
        if password is not None:
            auth += ":***"
        auth += "@"

    masked_netloc = f"{auth}{hostname}{port}"
    return urlunparse(parsed._replace(netloc=masked_netloc))


def _adapt_query(query: str, backend: str) -> str:
    if backend == "postgresql":
        return query.replace("?", "%s")
    return query


class CompatCursor:
    def __init__(self, raw_cursor: Any, backend: str):
        self._raw_cursor = raw_cursor
        self._backend = backend

    def execute(self, query: str, params: Iterable[Any] | None = None):
        adapted_query = _adapt_query(query, self._backend)
        if params is None:
            self._raw_cursor.execute(adapted_query)
        else:
            self._raw_cursor.execute(adapted_query, tuple(params))
        return self

    def executemany(self, query: str, seq_of_params: Iterable[Iterable[Any]]):
        adapted_query = _adapt_query(query, self._backend)
        self._raw_cursor.executemany(adapted_query, seq_of_params)
        return self

    def fetchone(self):
        return self._raw_cursor.fetchone()

    def fetchall(self):
        return self._raw_cursor.fetchall()

    def __getattr__(self, name: str):
        return getattr(self._raw_cursor, name)


class CompatConnection:
    def __init__(self, raw_connection: Any, backend: str):
        self._raw_connection = raw_connection
        self.backend = backend

    def cursor(self):
        return CompatCursor(self._raw_connection.cursor(), backend=self.backend)

    def close(self):
        return self._raw_connection.close()

    def commit(self):
        return self._raw_connection.commit()

    def __getattr__(self, name: str):
        return getattr(self._raw_connection, name)


def connect_database(settings: DatabaseSettings) -> CompatConnection:
    if settings.backend == "sqlite":
        sqlite_path = settings.sqlite_path or "database.db"
        raw_connection = sqlite3.connect(sqlite_path, autocommit=True)
        return CompatConnection(raw_connection, backend="sqlite")

    if settings.backend == "postgresql":
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL backend requested, but psycopg is not installed. "
                "Install project dependencies, including psycopg[binary]."
            ) from exc

        raw_connection = psycopg.connect(settings.dsn)
        raw_connection.autocommit = True
        return CompatConnection(raw_connection, backend="postgresql")

    raise ValueError(f"Unsupported database backend: {settings.backend}")


def initialize_schema(cursor: CompatCursor, backend: str):
    if backend == "postgresql":
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                tel TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                pass TEXT NOT NULL,
                admin INTEGER DEFAULT 0
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tutorial_progress (
                user_id BIGINT NOT NULL,
                tutorial_slug TEXT NOT NULL,
                completed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id, tutorial_slug)
            )
            """
        )
        return

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tel TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            pass TEXT NOT NULL,
            admin INTEGER DEFAULT 0
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tutorial_progress (
            user_id INTEGER NOT NULL,
            tutorial_slug TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, tutorial_slug)
        )
        """
    )
