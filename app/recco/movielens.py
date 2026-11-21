"""MovieLens ml-latest-small importer.

Run as `flask import-movielens` by the one-shot `loader` service in
env/docker-compose.yml, before the app starts. It

1. skips if LOAD_MOVIELENS is false or MovieLens was already imported,
2. finds the CSVs in data/ (or the download cache), otherwise downloads
   and checksum-verifies the official zip,
3. runs db/import/movielens.sql (LOAD DATA LOCAL INFILE into TEMPORARY
   staging tables, then INSERT ... SELECT into the real tables) in one
   transaction.
"""
import csv
import hashlib
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import click
import pymysql

from . import db

URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
# Published at URL + ".md5". The ml-latest-small snapshot has not changed since 2018.
MD5 = "31a303aabbc519bd33d025e44d6c2570"
CSV_FILES = ("movies.csv", "links.csv", "ratings.csv")
SQL_PATH = Path(os.environ.get("MOVIELENS_SQL", "/import/movielens.sql"))
DATA_DIR = Path(os.environ.get("MOVIELENS_DATA_DIR", "/data"))      # host data/, read-only
CACHE_DIR = Path(os.environ.get("MOVIELENS_CACHE_DIR", "/cache"))   # docker volume
# Every imported rater gets an e-mail in this reserved domain.
MARKER = "%@movielens.invalid"
# LOAD DATA target table for each CSV, used to check that no row was lost.
STAGING = {"movies.csv": "stg_movies", "links.csv": "stg_links", "ratings.csv": "stg_ratings"}


def _has_csvs(folder: Path) -> bool:
    return all((folder / name).is_file() for name in CSV_FILES)


def _download(dest: Path) -> None:
    click.echo(f"downloading {URL}")
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "ml.zip"
        with urllib.request.urlopen(URL, timeout=60) as resp, open(zip_path, "wb") as out:
            shutil.copyfileobj(resp, out)
        digest = hashlib.md5(zip_path.read_bytes()).hexdigest()
        if digest != MD5:
            raise click.ClickException(f"checksum mismatch for {URL}: {digest} != {MD5}")
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            # Extract only the files we need, by exact name (no path tricks).
            for name in CSV_FILES + ("README.txt",):
                with zf.open(f"ml-latest-small/{name}") as src, open(dest / name, "wb") as out:
                    shutil.copyfileobj(src, out)
    click.echo(f"saved to {dest}")


def find_or_download() -> Path | None:
    """Folder with the CSVs, or None if they are missing and the download failed."""
    for folder in (DATA_DIR / "ml-latest-small", DATA_DIR, CACHE_DIR / "ml-latest-small"):
        if _has_csvs(folder):
            click.echo(f"using CSVs in {folder}")
            return folder
    try:
        _download(CACHE_DIR / "ml-latest-small")
    except OSError as exc:  # network down, DNS, disk ...
        click.echo(f"WARNING: could not download MovieLens ({exc}).", err=True)
        return None
    return CACHE_DIR / "ml-latest-small"


def _statements(sql: str):
    """Split the import script. Comments sit on their own lines and every
    statement ends with ';' at the end of a line (see the file header)."""
    buf = []
    for line in sql.splitlines():
        if not buf and (not line.strip() or line.lstrip().startswith("--")):
            continue
        if line.lstrip().startswith("--"):
            continue
        buf.append(line)
        if line.rstrip().endswith(";"):
            yield "\n".join(buf).rstrip().rstrip(";")
            buf = []
    if buf:
        raise ValueError("import script ends without ';'")


def _csv_rows(path: Path) -> int:
    with open(path, newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.reader(f)) - 1  # minus header


def run_import(conn, ml_dir: Path) -> None:
    sql = SQL_PATH.read_text(encoding="utf-8").replace("{{ML_DIR}}", str(ml_dir))
    with conn.cursor() as cur:
        for stmt in _statements(sql):
            try:
                cur.execute(stmt)
            except pymysql.MySQLError as exc:
                first_line = stmt.strip().splitlines()[0]
                raise click.ClickException(
                    f"{exc.args[-1]} (MySQL error {exc.args[0]})\n  in statement: {first_line} ...\n"
                    "  Nothing was imported (the transaction was rolled back)."
                ) from exc
            if stmt.lstrip().upper().startswith("LOAD DATA"):
                # With LOCAL, bad values become warnings instead of errors:
                # treat any warning as a failure.
                warnings = conn.show_warnings()
                if warnings:
                    raise click.ClickException(f"LOAD DATA warnings: {warnings[:5]}")
        for name, table in STAGING.items():
            cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
            loaded, expected = cur.fetchone()["n"], _csv_rows(ml_dir / name)
            if loaded != expected:
                raise click.ClickException(f"{name}: loaded {loaded} rows, CSV has {expected}")


def _counts(conn) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT (SELECT COUNT(*) FROM movies) AS movies, (SELECT COUNT(*) FROM genres) AS genres,"
            " (SELECT COUNT(*) FROM movie_genres) AS movie_genres, (SELECT COUNT(*) FROM users) AS users,"
            " (SELECT COUNT(*) FROM ratings) AS ratings"
        )
        return ", ".join(f"{k} {v}" for k, v in cur.fetchone().items())


@click.command("import-movielens")
def import_movielens_command():
    """Import MovieLens ml-latest-small once (run by the loader service)."""
    if os.environ.get("LOAD_MOVIELENS", "true").strip().lower() in ("0", "false", "no", "off"):
        click.echo("LOAD_MOVIELENS is off: skipping MovieLens import")
        return
    conn = db.connect(local_infile=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT EXISTS (SELECT 1 FROM users WHERE email LIKE %s) AS done", (MARKER,))
            if cur.fetchone()["done"]:
                click.echo(f"MovieLens already imported, skipping ({_counts(conn)})")
                return
        ml_dir = find_or_download()
        if ml_dir is None:
            click.echo("WARNING: starting WITHOUT MovieLens data. Retry later with:\n"
                       "  docker compose -f env/docker-compose.yml run --rm loader", err=True)
            return
        click.echo("importing MovieLens (one transaction) ...")
        try:
            run_import(conn, ml_dir)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        click.echo(f"MovieLens imported: {_counts(conn)}")
    finally:
        conn.close()
