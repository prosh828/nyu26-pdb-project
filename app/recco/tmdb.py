"""Fill movies.poster_url (and a missing runtime) from the TMDB API.

Run as `flask fetch-posters` by the one-shot `posters` service in
env/docker-compose.yml. The app does not wait for it: pages show a
placeholder until a poster URL exists.

- Only movies with a tmdb_id and no poster_url are looked up, so the job
  can be stopped and re-run at any time; it continues where it left off.
- Only the URL is stored. The image itself stays on TMDB's CDN.
- Needs TMDB_API_KEY in env/.env (v3 API key, or a v4 read access token).
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor

import click
import requests

from . import db

API = "https://api.themoviedb.org/3/movie/{tmdb_id}"
IMAGE_BASE = "https://image.tmdb.org/t/p/"
POSTER_SIZE = "w342"     # TMDB sizes: w92 w154 w185 w342 w500 w780 original
WORKERS = 8              # parallel requests; TMDB allows roughly 40-50 per second
BATCH = 200              # commit after this many movies, so progress survives a stop


class InvalidKey(Exception):
    pass


def _session(key: str) -> requests.Session:
    s = requests.Session()
    if key.startswith("eyJ"):            # v4 read access token (JWT)
        s.headers["Authorization"] = f"Bearer {key}"
    else:                                # v3 API key
        s.params = {"api_key": key}
    s.headers["Accept"] = "application/json"
    return s


def lookup(session: requests.Session, tmdb_id: int):
    """(poster_url or None, runtime or None) for one movie. Retries on 429/5xx."""
    for attempt in range(5):
        try:
            r = session.get(API.format(tmdb_id=tmdb_id), timeout=15)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            data = r.json()
            path = data.get("poster_path")
            runtime = data.get("runtime")
            return (f"{IMAGE_BASE}{POSTER_SIZE}{path}" if path else None,
                    runtime if isinstance(runtime, int) and 0 < runtime < 32768 else None)
        if r.status_code == 401:
            raise InvalidKey(r.json().get("status_message", "401 Unauthorized"))
        if r.status_code == 404:                       # tmdb_id unknown to TMDB
            return None, None
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(float(r.headers.get("Retry-After", 2 ** attempt)))
            continue
        return None, None                              # other 4xx: give up on this movie
    return None, None


@click.command("fetch-posters")
@click.option("--limit", type=int, default=None, help="Look up at most this many movies.")
def fetch_posters_command(limit):
    """Fill poster_url (and missing runtime) from TMDB for movies that lack one."""
    key = os.environ.get("TMDB_API_KEY", "").strip()
    if not key:
        click.echo("TMDB_API_KEY is not set (env/.env): skipping posters")
        return
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT movie_id, tmdb_id FROM movies "
                "WHERE poster_url IS NULL AND tmdb_id IS NOT NULL ORDER BY movie_id"
                + (" LIMIT %s" % int(limit) if limit else "")
            )
            todo = cur.fetchall()
        if not todo:
            click.echo("all movies with a tmdb_id already have a poster_url")
            return
        click.echo(f"looking up {len(todo)} movies on TMDB ({WORKERS} parallel requests) ...")
        session = _session(key)
        found = no_poster = 0
        started = time.monotonic()
        with ThreadPoolExecutor(WORKERS) as pool:
            for start in range(0, len(todo), BATCH):
                chunk = todo[start:start + BATCH]
                try:
                    results = list(pool.map(lambda m: lookup(session, m["tmdb_id"]), chunk))
                except InvalidKey as exc:
                    raise click.ClickException(f"TMDB rejected the API key: {exc}")
                with conn.cursor() as cur:
                    for movie, (poster_url, runtime) in zip(chunk, results):
                        if poster_url is None:
                            no_poster += 1
                        else:
                            found += 1
                        # Write only empty columns: never overwrite curated data.
                        cur.execute(
                            "UPDATE movies SET poster_url = COALESCE(poster_url, %s),"
                            " runtime = COALESCE(runtime, %s) WHERE movie_id = %s",
                            (poster_url, runtime, movie["movie_id"]),
                        )
                conn.commit()
                done = start + len(chunk)
                if done % 1000 < BATCH or done == len(todo):
                    click.echo(f"  {done}/{len(todo)} ({time.monotonic() - started:.0f}s)")
        click.echo(f"done: {found} posters saved, {no_poster} movies without a poster on TMDB")
    finally:
        conn.close()
