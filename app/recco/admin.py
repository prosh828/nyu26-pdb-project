"""Admin area: the sub-menu pages under /admin (admin role only).

  /admin                    overview with links to every section (route in pages.py)
  /admin/catalog            catalogue management: movies and genre tags    (placeholder)
  /admin/data               MovieLens CSV upload into movies/genres/ratings (placeholder)
  /admin/recommendations    popular / genre / item-to-item algorithms       (placeholder)
  /admin/stats              statistics with charts, ?days=7|30|90|365|all
  GET /api/admin/stats      the same numbers as JSON

Every route uses @admin_required (403 for other users, login redirect when signed
out). The statistics are read-only aggregates; their SQL lives in this module.
"""
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, render_template, request

from . import db
from .auth import admin_required

bp = Blueprint("admin", __name__)

# The admin sub-menu, in order: (endpoint, label, one-line purpose).
SECTIONS = [
    ("admin.stats", "Statistics",
     "Reviews, ratings, genre averages, active users, plays, watch time and completion."),
    ("admin.catalog", "Catalogue",
     "Add, edit and delete movies and their genre tags."),
    ("admin.data", "Data loading",
     "Upload MovieLens CSV files into movies, genres and ratings, then add poster links."),
    ("admin.recommendations", "Recommendations",
     "Manage the popular, genre and item-to-item recommendation algorithms."),
]

FINISHED = 90                    # progress >= 90 means finished (AGENTS.md business rules)
DEFAULT_RUNTIME = 100            # minutes, when TMDB had no runtime (same as the watch page)
GENRE_MIN_RATINGS = 3            # a genre needs this many ratings to get an average
TOP_PLAYED = 10
WINDOWS = {"7": 7, "30": 30, "90": 90, "365": 365, "all": None}
WINDOW_LABELS = {"7": "Last 7 days", "30": "Last 30 days", "90": "Last 90 days",
                 "365": "Last 12 months", "all": "All time"}
DEFAULT_WINDOW = "30"

# --- statistics SQL -----------------------------------------------------------
# %(since)s is a UTC timestamp, or NULL for "all time".
TOTALS_SQL = """
SELECT (SELECT COUNT(*) FROM users)                                  AS users,
       (SELECT COUNT(*) FROM movies)                                 AS movies,
       (SELECT COUNT(*) FROM ratings)                                AS ratings,
       (SELECT AVG(score) FROM ratings)                              AS avg_score,
       (SELECT COUNT(*) FROM ratings
        WHERE review IS NOT NULL AND review <> '')                   AS reviews
"""
# Active user = rated or watched something in the window.
ACTIVE_USERS_SQL = """
SELECT COUNT(DISTINCT a.user_id) AS active_users
FROM  (SELECT user_id FROM ratings     WHERE %(since)s IS NULL OR rated_at  >= %(since)s
       UNION ALL
       SELECT user_id FROM view_events WHERE %(since)s IS NULL OR viewed_at >= %(since)s) AS a
"""
SCORE_DISTRIBUTION_SQL = """
SELECT score, COUNT(*) AS n FROM ratings GROUP BY score ORDER BY score
"""
GENRE_AVERAGES_SQL = """
SELECT g.name, COUNT(*) AS n, AVG(r.score) AS avg_score
FROM genres g
JOIN movie_genres mg ON mg.genre_id = g.genre_id
JOIN ratings r       ON r.movie_id  = mg.movie_id
GROUP BY g.genre_id, g.name
HAVING COUNT(*) >= %(min_ratings)s
ORDER BY avg_score DESC, g.name
"""
RATINGS_BY_YEAR_SQL = """
SELECT YEAR(rated_at) AS y, COUNT(*) AS ratings,
       SUM(review IS NOT NULL AND review <> '') AS reviews
FROM ratings GROUP BY YEAR(rated_at) ORDER BY y
"""
ACTIVE_BY_YEAR_SQL = """
SELECT a.y, COUNT(DISTINCT a.user_id) AS users
FROM  (SELECT user_id, YEAR(rated_at)  AS y FROM ratings
       UNION ALL
       SELECT user_id, YEAR(viewed_at) AS y FROM view_events) AS a
GROUP BY a.y ORDER BY a.y
"""
# A "play" is one user watching one movie on one day: view_events gets a row on
# every pause, every minute and at page leave, so raw rows would overcount.
PLAYS_BY_DAY_SQL = """
SELECT p.d, COUNT(*) AS plays, COUNT(DISTINCT p.user_id) AS viewers
FROM  (SELECT DISTINCT user_id, movie_id, DATE(viewed_at) AS d
       FROM view_events
       WHERE %(since)s IS NULL OR viewed_at >= %(since)s) AS p
GROUP BY p.d ORDER BY p.d
"""
# Per (user, movie) in the window: the furthest point reached. Watch time =
# that share of the runtime; finished = reached FINISHED percent.
VIEWING_SQL = """
SELECT COUNT(*)                                                 AS watched_pairs,
       COALESCE(SUM(w.max_progress >= %(finished)s), 0)         AS finished_pairs,
       AVG(w.max_progress / 100 * COALESCE(m.runtime, %(default_runtime)s)) AS avg_minutes,
       AVG(w.max_progress)                                      AS avg_progress
FROM  (SELECT user_id, movie_id, MAX(progress) AS max_progress
       FROM view_events
       WHERE %(since)s IS NULL OR viewed_at >= %(since)s
       GROUP BY user_id, movie_id) AS w
JOIN movies m ON m.movie_id = w.movie_id
"""
PROGRESS_BUCKETS_SQL = """
SELECT LEAST(FLOOR(w.max_progress / 10), 9) AS bucket, COUNT(*) AS n
FROM  (SELECT user_id, movie_id, MAX(progress) AS max_progress
       FROM view_events
       WHERE %(since)s IS NULL OR viewed_at >= %(since)s
       GROUP BY user_id, movie_id) AS w
GROUP BY bucket ORDER BY bucket
"""
TOP_PLAYED_SQL = """
SELECT m.movie_id, m.title, COUNT(*) AS plays, COUNT(DISTINCT p.user_id) AS viewers
FROM  (SELECT DISTINCT user_id, movie_id, DATE(viewed_at) AS d
       FROM view_events
       WHERE %(since)s IS NULL OR viewed_at >= %(since)s) AS p
JOIN movies m ON m.movie_id = p.movie_id
GROUP BY m.movie_id, m.title
ORDER BY plays DESC, viewers DESC, m.title
LIMIT %(limit)s
"""


def _f(value, digits=2):
    return round(float(value), digits) if value is not None else None


def _window():
    key = request.args.get("days", DEFAULT_WINDOW)
    return key if key in WINDOWS else DEFAULT_WINDOW


def _plays_series(rows, since, today):
    """Plays per day (window up to 90 days) or per month, with empty periods as 0."""
    if not rows:
        return {"unit": "day", "points": []}
    first = since.date() if since else rows[0]["d"]
    by_day = {r["d"]: r for r in rows}
    if (today - first).days <= 92:
        points, d = [], first
        while d <= today:
            r = by_day.get(d)
            points.append({"label": d.isoformat(), "value": r["plays"] if r else 0,
                           "viewers": r["viewers"] if r else 0})
            d += timedelta(days=1)
        return {"unit": "day", "points": points}
    months = {}
    for r in rows:
        key = r["d"].strftime("%Y-%m")
        months[key] = months.get(key, 0) + r["plays"]
    points, y, mo = [], first.year, first.month
    while (y, mo) <= (today.year, today.month):
        key = f"{y:04d}-{mo:02d}"
        points.append({"label": key, "value": months.get(key, 0)})
        y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    return {"unit": "month", "points": points}


def _fill_years(rows, field):
    """Year series from the first to the last year, gaps as 0 (no rating 2019-2025 is real)."""
    if not rows:
        return []
    by_year = {r["y"]: r[field] for r in rows}
    return [{"label": str(y), "value": int(by_year.get(y, 0))}
            for y in range(min(by_year), max(by_year) + 1)]


def load_stats(window=DEFAULT_WINDOW, now=None):
    now = now or datetime.now(timezone.utc)
    days = WINDOWS[window]
    since = (now - timedelta(days=days)).replace(tzinfo=None) if days else None
    p = {"since": since, "finished": FINISHED, "default_runtime": DEFAULT_RUNTIME,
         "min_ratings": GENRE_MIN_RATINGS, "limit": TOP_PLAYED}
    with db.get_db().cursor() as cur:
        cur.execute(TOTALS_SQL)
        totals = cur.fetchone()
        cur.execute(ACTIVE_USERS_SQL, p)
        active = cur.fetchone()["active_users"]
        cur.execute(SCORE_DISTRIBUTION_SQL)
        scores = {float(r["score"]): r["n"] for r in cur.fetchall()}
        cur.execute(GENRE_AVERAGES_SQL, p)
        genres = cur.fetchall()
        cur.execute(RATINGS_BY_YEAR_SQL)
        by_year = cur.fetchall()
        cur.execute(ACTIVE_BY_YEAR_SQL)
        active_by_year = cur.fetchall()
        cur.execute(PLAYS_BY_DAY_SQL, p)
        plays_by_day = cur.fetchall()
        cur.execute(VIEWING_SQL, p)
        viewing = cur.fetchone()
        cur.execute(PROGRESS_BUCKETS_SQL, p)
        buckets = {int(r["bucket"]): r["n"] for r in cur.fetchall()}
        cur.execute(TOP_PLAYED_SQL, p)
        top = cur.fetchall()
    pairs, finished = int(viewing["watched_pairs"]), int(viewing["finished_pairs"])
    return {
        "window": {"key": window, "label": WINDOW_LABELS[window], "days": days,
                   "since": since.strftime("%Y-%m-%dT%H:%M:%SZ") if since else None},
        "totals": {
            "users": totals["users"], "movies": totals["movies"], "ratings": totals["ratings"],
            "avg_score": _f(totals["avg_score"]), "reviews": totals["reviews"],
            "review_share": _f(100 * totals["reviews"] / totals["ratings"], 3) if totals["ratings"] else None,
        },
        "activity": {
            "active_users": active,
            "plays": sum(r["plays"] for r in plays_by_day),   # same as the sum of the series
            "watched_pairs": pairs, "finished_pairs": finished,
            "completion_rate": _f(100 * finished / pairs, 1) if pairs else None,
            "avg_watch_minutes": _f(viewing["avg_minutes"], 1),
            "avg_progress": _f(viewing["avg_progress"], 1),
        },
        "score_distribution": [{"label": f"{s / 2:.1f}", "value": scores.get(s / 2, 0)}
                               for s in range(1, 11)],
        "genre_averages": [{"label": g["name"], "value": _f(g["avg_score"]), "count": g["n"]}
                           for g in genres],
        "ratings_by_year": _fill_years(by_year, "ratings"),
        "reviews_by_year": _fill_years(by_year, "reviews"),
        "active_users_by_year": _fill_years(active_by_year, "users"),
        "plays": _plays_series(plays_by_day, since, now.date()),
        "progress_buckets": [{"label": f"{b * 10}-{b * 10 + 9}%" if b < 9 else "90-100%",
                              "value": buckets.get(b, 0)} for b in range(10)],
        "top_played": [{"movie_id": r["movie_id"], "label": r["title"], "value": r["plays"],
                        "viewers": r["viewers"]} for r in top],
    }


# --- pages ----------------------------------------------------------------------
def _placeholder(section, planned):
    _, label, purpose = next(entry for entry in SECTIONS if entry[0] == section)
    return render_template("admin/placeholder.html", label=label, purpose=purpose, planned=planned)


@bp.route("/admin/stats")
@admin_required
def stats():
    window = _window()
    return render_template("admin/stats.html", stats=load_stats(window), windows=WINDOW_LABELS,
                           finished=FINISHED, genre_min_ratings=GENRE_MIN_RATINGS, top_limit=TOP_PLAYED)


@bp.route("/api/admin/stats")
@admin_required
def stats_api():
    return jsonify(load_stats(_window()))


@bp.route("/admin/catalog")
@admin_required
def catalog():
    return _placeholder("admin.catalog", [
        "Search the catalogue and open a movie to edit its title, year, runtime and poster link.",
        "Add a new movie and tag it with genres.",
        "Add, rename and delete genre tags (a genre still used by a movie cannot be deleted).",
        "Delete a movie (its ratings, views and list entries go with it).",
    ])


@bp.route("/admin/data")
@admin_required
def data():
    return _placeholder("admin.data", [
        "Upload MovieLens movies.csv, ratings.csv and links.csv.",
        "Insert them into movies, genres, movie_genres and ratings in one transaction.",
        "Fill poster links from TMDB for the new movies.",
        "Show a summary of what was inserted, merged or skipped.",
    ])


@bp.route("/admin/recommendations")
@admin_required
def recommendations():
    return _placeholder("admin.recommendations", [
        "Popular: the most-rated movies chart, shared by everyone.",
        "Genre: top-rated movies in each user's favourite genres.",
        "Item-to-item: \"Because you liked X\" lists from co-rated movies.",
        "Regenerate the stored lists and see when each was last refreshed.",
    ])

