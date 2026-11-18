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
env/docker-compose.yml   db / app / adminer services (paths inside are relative to env/)
env/.env.example         optional overrides; a local env/.env (git-ignored) goes here too
app/                     Flask app (Dockerfile, requirements.txt, recco/ package)
  recco/__init__.py      create_app() factory, routes, `flask ensure-admin` CLI command
  recco/db.py            get_db(): one PyMySQL connection per request (flask.g)
db/init/                 SQL run automatically ONLY when the DB volume is empty
  01_schema.sql          10 tables (source of truth for the schema)
  02_sample_data.sql     hand-crafted sample data incl. demo accounts
sql/03_queries.sql       the 11 app queries with %(name)s placeholders (reference, not runnable)
sql/04_test_queries.sql  the same queries with concrete values + EXPECTED ERROR checks
data/                    MovieLens CSVs (git-ignored except data/README.md)
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
- **After any change in `db/init/`, reset the volume (`down -v`, then `up -d`).** Init scripts
  never re-run on an existing volume. Tell the user that their local data will be wiped.
- Regression test for the schema and queries, on a **fresh** DB (it inserts rows, so a second
  run fails on purpose):
  ```bash
  docker compose -f env/docker-compose.yml exec -T db mysql -urecco -preccopass --force -t recco < sql/04_test_queries.sql
  ```
  Exactly 3 errors are expected (duplicate email, rating CHECK, duplicate rank). The result
  rows must match `part2/results/test_results.txt` except for timestamps. Reset the DB afterwards.
- There is no test suite or linter yet. "Verified" means: the stack starts, `/health` shows 10
  tables, and the page or query you changed works against the sample data.

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
  change it there too and re-check `sql/04_test_queries.sql`.
- Schema changes go in `db/init/` (edit `01_schema.sql`, or add a numbered file such as
  `03_views.sql`; files run in name order). Keep `02_sample_data.sql` consistent with them.
- New Python dependencies: add a pinned version to `app/requirements.txt`.
- Secrets (TMDB key, passwords other than the dev defaults) go in `env/.env`, never in git.

## MovieLens import (not built yet)

- Put CSVs in `data/`. Inside containers they are at `/data/` (both `app` and `db`).
- In MySQL use `LOAD DATA LOCAL INFILE '/data/movies.csv' ...` with
  `mysql --local-infile=1`. Server-side `LOAD DATA INFILE` from `/var/lib/mysql-files`
  is not set up: mounting there read-only breaks the MySQL entrypoint's chown.
- MovieLens titles carry the year in the title ("Toy Story (1995)"). Split it into
  `title` + `release_year`. Some movies have no year, and there are duplicate title/year pairs
  that would violate `UNIQUE(title, release_year)`. Decide how to handle them before importing.
- `links.csv` gives `tmdbId` (may be empty) for posters. Ratings in MovieLens are already half steps.

## Open questions (ask the team, do not decide silently)

- movie_genres → genres FK: the proposal's "Key decisions" say RESTRICT (implemented), but its
  table says CASCADE. Pending team confirmation (see PR #5).
- How to treat MovieLens duplicate title/year rows (merge, skip, or relax the UNIQUE).

## Git workflow

- Branch from the latest `origin/main` (`feature/...`, `fix/...`, `setup/...`), open a PR into
  `main`, and let a teammate review. Do not push directly to `main`.
- Write commit messages in English, imperative mood ("Add watchlist page").
- Never commit `env/.env`, CSVs in `data/`, `.DS_Store`, or zip archives.
- If a step was not verified (e.g. Docker was not running), say so in the PR.
