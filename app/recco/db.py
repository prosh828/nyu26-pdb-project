import os

import pymysql
from flask import g


def connect(**extra):
    """New PyMySQL connection from the MYSQL_* / DB_* environment variables."""
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=int(os.environ.get("DB_PORT", 3306)),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        init_command="SET time_zone = '+00:00'",  # 모든 TIMESTAMP를 UTC로
        autocommit=False,
        **extra,
    )


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)
