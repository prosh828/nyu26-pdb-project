# Recco — context for AI coding agents

Read this file before doing any task in this repo. It is the shared context for every
team member's AI agent (Claude Code reads it through `CLAUDE.md`; Codex, Cursor and other
tools read `AGENTS.md` directly). Keep it accurate: if you change something described here,
update this file in the same commit.

## Project

- **Recco**: a movie recommendation web app. Users rate and review movies, keep a watchlist,
  hide titles, continue watching, and get ranked recommendations. Admins manage the catalogue
  and refresh recommendations.
- NYU CS-GY 6083 (Principles of Database Systems), Fall 2026, team project.
  Team: Jonghyun Jeong (jj4335), Seho Kim (sk13811), Harry Song (cs8293).
- Repo: https://github.com/prosh828/nyu26-pdb-project (default branch `main`).
- Stack: **Python 3.12, Flask 3.0, PyMySQL 1.1 (raw SQL, no ORM), MySQL 8.0**, all in Docker.
  Data source: MovieLens `ml-latest-small` (+ TMDB API for posters).
- The course grades the **SQL and the database design**. Write explicit, readable SQL.
  Do not introduce an ORM (SQLAlchemy etc.) or a query builder.

## Repository layout

```
env/docker-compose.yml   db / loader / posters / app / adminer services (paths relative to env/)
env/.env.example         optional overrides; a local env/.env (git-ignored) goes here too
app/                     Flask app (Dockerfile, requirements.txt, recco/ package)
  recco/__init__.py      create_app() factory, routes, `flask ensure-admin` CLI command
  recco/db.py            connect(); get_db(): one PyMySQL connection per request (flask.g)
  recco/movielens.py     `flask import-movielens`: download + run db/import/movielens.sql
  recco/tmdb.py          `flask fetch-posters`: fill movies.poster_url / runtime from TMDB
  recco/movies.py        `GET /api/movies` JSON API (title search + pagination); its SQL lives here
  tests/                 unittest tests (read-only against the running DB), see "Running and verifying"
db/init/                 SQL run automatically ONLY when the DB volume is empty
  01_schema.sql          10 tables (source of truth for the schema)
  02_sample_data.sql     hand-crafted sample data incl. demo accounts
db/import/movielens.sql  MovieLens CSV -> tables (run by the loader service, not by MySQL init)
sql/03_queries.sql       the 11 app queries with %(name)s placeholders (reference, not runnable)
sql/04_test_queries.sql  the same queries with concrete values + EXPECTED ERROR checks
data/                    optional local MovieLens CSVs in data/ml-latest-small/ (git-ignored)
part2/                   Part 2 deliverables: report, diagrams, submitted SQL — READ-ONLY
```

- `db/init/01_schema.sql`, `02_sample_data.sql` and `sql/*.sql` were copied from `part2/sql/`.
  From now on edit the root copies. **Do not edit anything under `part2/`**; it is the record
  of what was submitted. `part2/report/report.md` is the best explanation of the design.
- `.gitignore` / `.gitattributes` stay at the repo root (git only reads them there).
  `.gitattributes` forces LF line endings (team members use Windows and macOS).

## Running and verifying

Always run Docker commands **from the repo root** with `-f env/docker-compose.yml`
(or `export COMPOSE_FILE=env/docker-compose.yml` once per shell).

```bash
docker compose -f env/docker-compose.yml up -d --build      # start / rebuild
docker compose -f env/docker-compose.yml ps                 # recco-db must be "healthy"
curl -s localhost:5001/health                               # expect "table_count": 10
docker compose -f env/docker-compose.yml logs -f app
docker compose -f env/docker-compose.yml exec db mysql -urecco -preccopass recco
docker compose -f env/docker-compose.yml down -v && docker compose -f env/docker-compose.yml up -d   # reset DB
```

| Service | Host address | Notes |
|---|---|---|
| Flask app | http://localhost:5001 | container port 5000; host 5001 because macOS AirPlay owns 5000 |
| Adminer | http://localhost:8081 | server `db`, user `recco` / `reccopass`, db `recco` |
| MySQL | `localhost:3307` | root password `rootpass` (dev only) |

- `app/` is bind-mounted and Flask runs with `--debug`, so Python/template edits reload live.
  Only `requirements.txt` or `Dockerfile` changes need `--build`.
- **After any change in `db/init/` or `db/import/`, reset the volume (`down -v`, then `up -d`).** Init scripts
  never re-run on an existing volume. Tell the user that their local data will be wiped.
- Regression test for the schema and queries, on a **fresh, sample-only** DB (it inserts rows,
  so a second run fails on purpose):
  ```bash
  docker compose -f env/docker-compose.yml down -v
  LOAD_MOVIELENS=false docker compose -f env/docker-compose.yml up -d
  docker compose -f env/docker-compose.yml exec -T db mysql -urecco -preccopass --force -t recco < sql/04_test_queries.sql
  ```
  Exactly 3 errors are expected (duplicate email, rating CHECK, duplicate rank). The result
  rows must match `part2/results/test_results.txt` except for timestamps. Reset the DB afterwards
  (`down -v`, then `up -d` without the variable to get MovieLens back).
- Python tests use the standard-library `unittest` (no pytest). They run inside the app container
  and only SELECT from the running DB (works with sample data or MovieLens; they never write):
  ```bash
  docker compose -f env/docker-compose.yml exec app python -m unittest discover -s tests -t . -v
  ```
  There is no linter yet. "Verified" means: the stack starts, `/health` shows 10
  tables, the loader log says MovieLens was imported (or skipped), and the page or query you
  changed works against the data.

## Accounts

- Sample data creates demo users whose **password equals the username**:
  `admin` (role admin, user_id 1), `alice`, `bob`, `carol`, `david`, `eve`, `frank` (new user, no ratings).
  Hashes are werkzeug `pbkdf2:sha256`, so use `werkzeug.security.check_password_hash`.
- `flask ensure-admin` runs at every app start. It creates an admin from the `ADMIN_*` env vars
  (default `admin` / `admin1234`) **only if no admin exists**, so with sample data loaded it skips.

## Database schema (MySQL 8.0, utf8mb4, InnoDB)

| Table | Key | Notes |
|---|---|---|
| users | user_id | username, email UNIQUE; role IN ('user','admin'); email CHECK `LIKE '%_@_%._%'` |
| genres | genre_id | name UNIQUE |
| movies | movie_id | UNIQUE(title, release_year), UNIQUE(tmdb_id); release_year 1870–2100 and runtime > 0, both nullable |
| movie_genres | (movie_id, genre_id) | genre FK **ON DELETE RESTRICT**: a genre still used by a movie cannot be deleted |
| user_genres | (user_id, genre_id) | favourite genres, exactly 3 picked at sign-up |
| ratings | (user_id, movie_id) | score DECIMAL(2,1), 0.5–5.0 in half steps; one current rating per user/movie |
| view_events | event_id | append-only log; progress 0–100; **progress >= 90 means finished** |
| watchlist | (user_id, movie_id) | added_at |
| hidden_movies | (user_id, movie_id) | "not interested" |
| recommendations | rec_id | stored ranked lists, see below |

All other FKs are `ON DELETE CASCADE`. Every timestamp is `TIMESTAMP` stored and read in
**UTC**: the server runs with `--default-time-zone=+00:00` and `db.py` sets
`time_zone = '+00:00'` on every connection. In Python use `datetime.now(timezone.utc)`.

**recommendations**
- A *list* = (user_id, strategy, seed_movie_id, generated_at). strategy ∈ `popular`, `genre`, `item_cf`.
- `seed_movie_id` is set **only** for `item_cf` ("Because you liked X"), and never equals `movie_id`.
- Column is `rec_rank`, not `rank`, because `RANK` is a reserved word in MySQL 8.
- `seed_key = COALESCE(seed_movie_id, 0)` is a **VIRTUAL** generated column. It exists because
  UNIQUE treats NULLs as distinct. It cannot be STORED because `seed_movie_id`'s FK is CASCADE.
  Never insert into `seed_key`.
- `shown_at` stays NULL until the page displays the row. Stamp it once (keep the first value)
  and `shown_at >= generated_at`.

## Business rules the queries implement (see `sql/03_queries.sql`)

- **Liked** = score >= 4.0. **Top-rated / genre picks** need at least 3 ratings per movie.
- **Trending** = views in the last 7 days, ranked by distinct viewers, then total views.
- **Continue watching** = the latest view event per movie has progress < 90.
- Personal recommendations (`genre`, `item_cf`) exclude movies the user rated, finished (>= 90),
  hid, or saw in another personal list in the last 24 hours.
- **24-hour rule**: counted from the first `shown_at`. Refreshing a page shows the same list.
  `popular` charts are exempt in both directions.
- Sign-up must pick exactly 3 existing genres, in one transaction with the user insert.
- Admin-only writes check the role inside the SQL (e.g. `INSERT ... SELECT ... WHERE` the caller is an admin).

## Coding conventions

- SQL: always pass values as parameters (`cur.execute(sql, {"user_id": uid})` with `%(name)s`).
  Never build SQL with f-strings or `%` formatting on user input. Table and column names come
  from code only.
- `get_db()` returns a connection with `DictCursor` and **autocommit off**: call
  `conn.commit()` after writes, and `conn.rollback()` on failure. Multi-statement operations
  (sign-up, list regeneration) belong in one transaction.
- `INSERT ... VALUES (...) AS new ON DUPLICATE KEY UPDATE col = new.col` is the upsert style
  in use (needs MySQL 8.0.19+). Do not use the deprecated `VALUES(col)` function.
- Reuse the queries from `sql/03_queries.sql` when building features. If a query has to change,
  change it there too and re-check `sql/04_test_queries.sql`. The movie-browsing SQL in
  `recco/movies.py` is deliberately not in `sql/03`, which stays at the 11 Part 2 queries.
- Schema changes go in `db/init/` (edit `01_schema.sql`, or add a numbered file such as
  `03_views.sql`; files run in name order). Keep `02_sample_data.sql` consistent with them.
- New Python dependencies: add a pinned version to `app/requirements.txt`.
- Secrets (TMDB key, passwords other than the dev defaults) go in `env/.env`, never in git.
  `env/.env` must be created before the first run: `cp env/.env.example env/.env`.

## MovieLens import (automatic)

- Startup order: `db` healthy -> `loader` (one-shot, `flask import-movielens`) exits 0 -> `app`.
  If the loader fails, the app does not start: read `docker compose -f env/docker-compose.yml logs loader`.
- The loader skips when `LOAD_MOVIELENS=false` or when users with `@movielens.invalid` e-mails
  exist (already imported). Re-run: `docker compose -f env/docker-compose.yml run --rm loader`.
- CSV source, first match wins: `data/ml-latest-small/`, `data/`, then the `movielens_cache`
  volume; otherwise it downloads the official zip and checks its MD5. If the download fails it
  warns and exits 0, so the app starts with sample data only.
- `db/import/movielens.sql` does the work, in ONE transaction: `LOAD DATA LOCAL INFILE` into
  TEMPORARY staging tables, then `INSERT ... SELECT` into the real tables. Any error rolls
  everything back. Python treats LOAD DATA warnings and row-count mismatches as errors.
  Its format rules (comments on their own lines, `;` at line end) come from the simple splitter.
- Mapping: MovieLens userId N -> user_id 1000+N (`ml_user_N`, password hash `!`, cannot log in);
  movieId N -> movie_id 1000+N, unless the movie already exists (sample data), matched by
  `tmdb_id`, then by (title, release_year). 19 of the 20 sample movies match.
- Clean-up: "Matrix, The (1999)" -> "The Matrix" + 1999 (articles The/A/An/Le/La/Les/El/Das);
  no year -> NULL; the 5 duplicate (title, year) pairs are merged into the lowest movieId
  (if a user rated both copies, the later rating wins); a tmdbId shared by two movies stays on
  the first; "(no genres listed)" -> no genre rows. `runtime` and `poster_url` stay NULL.
- Result on a fresh DB: movies 9,738, genres 19, users 617, ratings 100,888.
- `sql/04_test_queries.sql` matches the Part 2 results only with `LOAD_MOVIELENS=false`
  (MovieLens adds genres and ratings to the sample movies).
- A TEMPORARY table can appear only once per statement in MySQL ("Can't reopen table"):
  use window functions or another temporary table instead of self-joins.
- Server-side `LOAD DATA INFILE` from `/var/lib/mysql-files` is not set up: mounting there
  read-only breaks the MySQL entrypoint's chown. Use `LOAD DATA LOCAL INFILE`.

## Posters (TMDB)

- Startup: `posters` (one-shot `flask fetch-posters`) runs after `loader`; the app does NOT wait
  for it. It looks up only movies with a `tmdb_id` and `poster_url IS NULL`, commits every 200,
  so it can be stopped and re-run (`docker compose -f env/docker-compose.yml run --rm posters`).
- Stores only the URL, `https://image.tmdb.org/t/p/w342/<poster_path>`; images are never
  downloaded into the DB. It also fills `runtime` when it is NULL. Existing values are never
  overwritten (`COALESCE`).
- Needs `TMDB_API_KEY` in `env/.env` (v3 key; a v4 token starting with `eyJ` also works).
  Without it the job logs a skip and exits 0. **Never print, log or commit the key.**
- Movies without a poster on TMDB stay NULL and are looked up again on the next run (few).
  Pages must show a placeholder when `poster_url` is NULL.
- TMDB terms: show "This product uses the TMDB API but is not endorsed or certified by TMDB."
  somewhere in the web UI once posters are displayed.

## Open questions (ask the team, do not decide silently)

- movie_genres → genres FK: the proposal's "Key decisions" say RESTRICT (implemented), but its
  table says CASCADE. Pending team confirmation (see PR #5).
- MovieLens duplicate title/year rows are merged (implemented). Confirm the team agrees.

## Git workflow

- Branch from the latest `origin/main` (`feature/...`, `fix/...`, `setup/...`), open a PR into
  `main`, and let a teammate review. Do not push directly to `main`.
- Write commit messages in English, imperative mood ("Add watchlist page").
- Never commit `env/.env`, CSVs in `data/`, `.DS_Store`, or zip archives.
- If a step was not verified (e.g. Docker was not running), say so in the PR.
