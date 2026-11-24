"""Helpers for tests that write to MySQL. They only ever touch the `recco_test` database.

Safety rules (a test run must never modify the development database `recco`):
  1. The connection is opened directly on TEST_DB. The target is NOT read from MYSQL_DATABASE.
  2. Every statement that changes data or tables goes through `execute_checked`, which first
     verifies `SELECT DATABASE()` == TEST_DB and aborts otherwise.
  3. The schema script is run statement by statement from an allow-list. Its
     `CREATE DATABASE ... recco` and `USE recco` lines are skipped on purpose; any other
     unexpected statement aborts the run instead of being executed.

One-time setup (creates the empty database and lets the app user use it):
    see SETUP_HINT below, also documented in AGENTS.md.
"""
import os
import re
from pathlib import Path

import pymysql
from werkzeug.security import generate_password_hash

from recco.movielens import _statements

TEST_DB = "recco_test"

SETUP_HINT = (
    "The test database `recco_test` is missing or not accessible. Create it once "
    "(see AGENTS.md, section 'Running and verifying') and run the tests again."
)

# Repo checkout (running on the host) or the read-only mount of db/init inside the app container.
SCHEMA_FILE_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "db" / "init" / "01_schema.sql",
    Path("/db-init/01_schema.sql"),
)

# Statements of 01_schema.sql that must NOT be executed (they name the development DB).
_SKIPPED = {
    "CREATE DATABASE IF NOT EXISTS recco CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci",
    "USE recco",
}
_ALLOWED = (
    re.compile(r"SET time_zone = '\+00:00'"),
    re.compile(r"DROP TABLE IF EXISTS [a-z_]+"),
    re.compile(r"CREATE TABLE [a-z_]+ \(.*", re.DOTALL),
)
_DEV_DB_WORD = re.compile(r"\brecco\b", re.IGNORECASE)

SAMPLE_GENRES = ["Action", "Comedy", "Drama", "Horror", "Sci-Fi"]


class UnsafeDatabaseError(RuntimeError):
    """Raised when a test is about to write to a database other than TEST_DB."""


def connect_test_db():
    """PyMySQL connection pinned to TEST_DB (credentials come from the container env)."""
    try:
        return pymysql.connect(
            host=os.environ.get("DB_HOST", "db"),
            port=int(os.environ.get("DB_PORT", 3306)),
            user=os.environ["MYSQL_USER"],
            password=os.environ["MYSQL_PASSWORD"],
            database=TEST_DB,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            init_command="SET time_zone = '+00:00'",
            autocommit=False,
        )
    except pymysql.err.OperationalError as exc:
        if exc.args and exc.args[0] in (1044, 1049):  # access denied / unknown database
            raise RuntimeError(SETUP_HINT) from None  # no driver message: it contains the account
        raise


def assert_test_database(conn):
    """Abort unless `conn` currently points at TEST_DB."""
    with conn.cursor() as cur:
        cur.execute("SELECT DATABASE() AS name")
        name = cur.fetchone()["name"]
    if name != TEST_DB:
        raise UnsafeDatabaseError(
            f"refusing to continue: connection uses database {name!r}, expected {TEST_DB!r}")


def execute_checked(conn, sql, params=None):
    """Run a modifying statement only after verifying the active database."""
    assert_test_database(conn)
    with conn.cursor() as cur:
        cur.execute(sql, params)


def fetch(conn, sql, params=None):
    """Read rows. Ends the current transaction first so recent commits are visible."""
    conn.commit()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _schema_sql():
    for path in SCHEMA_FILE_CANDIDATES:
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise RuntimeError("db/init/01_schema.sql not found (expected at /db-init in the app container)")


def reset_schema(conn):
    """Recreate the 10 tables in TEST_DB from db/init/01_schema.sql (allow-list only)."""
    assert_test_database(conn)
    for stmt in _statements(_schema_sql()):
        normalized = " ".join(stmt.split())
        if normalized in _SKIPPED:
            continue
        if not any(p.fullmatch(normalized) for p in _ALLOWED) or _DEV_DB_WORD.search(normalized):
            raise UnsafeDatabaseError(
                f"unexpected statement in the schema script, not executed: {normalized[:60]!r}")
        execute_checked(conn, stmt)
    conn.commit()


def reset_data(conn, passwords):
    """Empty the user tables of TEST_DB and insert the fixtures. Returns {username: user_id}.

    `passwords` maps username -> (role, password_hash_or_None, email)."""
    assert_test_database(conn)
    execute_checked(conn, "DELETE FROM user_genres")
    execute_checked(conn, "DELETE FROM users")
    execute_checked(conn, "DELETE FROM genres")
    for name in SAMPLE_GENRES:
        execute_checked(conn, "INSERT INTO genres (name) VALUES (%(name)s)", {"name": name})
    ids = {}
    for username, (role, password_hash, email) in passwords.items():
        execute_checked(
            conn,
            "INSERT INTO users (username, email, password_hash, role) "
            "VALUES (%(username)s, %(email)s, %(password_hash)s, %(role)s)",
            {"username": username, "email": email, "password_hash": password_hash, "role": role})
        ids[username] = fetch(conn, "SELECT LAST_INSERT_ID() AS id")[0]["id"]
    conn.commit()
    return ids


def default_users():
    """Fixture accounts. alice/admin use the project's pbkdf2:sha256 convention (like the
    sample data), `legacy` uses Werkzeug's default method (like `flask ensure-admin`),
    `ml_user_1` has the '!' placeholder hash of imported MovieLens users."""
    pbkdf2 = lambda pw: generate_password_hash(pw, method="pbkdf2:sha256")
    return {
        "admin": ("admin", pbkdf2("adminpass"), "admin@recco.test"),
        "alice": ("user", pbkdf2("alicepass"), "alice@recco.test"),
        "legacy": ("user", generate_password_hash("legacypass"), "legacy@recco.test"),
        "ml_user_1": ("user", "!", "ml_user_1@movielens.invalid"),
    }
