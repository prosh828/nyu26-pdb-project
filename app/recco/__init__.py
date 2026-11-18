import os

import click
from flask import Flask, render_template
from werkzeug.security import generate_password_hash

from . import db, movielens, tmdb


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev")
    db.init_app(app)
    app.cli.add_command(movielens.import_movielens_command)
    app.cli.add_command(tmdb.fetch_posters_command)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/health")
    def health():
        """DB 연결 및 테이블 목록 확인용 (환경 구축 검증)."""
        with db.get_db().cursor() as cur:
            cur.execute("SELECT VERSION() AS v, @@session.time_zone AS tz")
            info = cur.fetchone()
            cur.execute(
                "SELECT table_name AS t FROM information_schema.tables "
                "WHERE table_schema = DATABASE() ORDER BY table_name"
            )
            tables = [r["t"] for r in cur.fetchall()]
        return {"mysql_version": info["v"], "time_zone": info["tz"],
                "table_count": len(tables), "tables": tables}

    @app.cli.command("ensure-admin")
    def ensure_admin():
        """관리자가 하나도 없으면 ADMIN_* 환경변수로 생성 (컨테이너 시작 시 자동 실행)."""
        conn = db.get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'admin'")
            if cur.fetchone()["n"] > 0:
                click.echo("admin already exists, skipping")
                return
            username = os.environ.get("ADMIN_USERNAME", "admin")
            cur.execute(
                "INSERT INTO users (username, email, password_hash, role) "
                "VALUES (%s, %s, %s, 'admin')",
                (username,
                 os.environ.get("ADMIN_EMAIL", "admin@recco.local"),
                 generate_password_hash(os.environ.get("ADMIN_PASSWORD", "admin1234"))),
            )
        conn.commit()
        click.echo(f"admin '{username}' created")

    return app
