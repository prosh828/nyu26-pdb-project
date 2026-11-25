"""Movie rows ("collections") for the public landing page `/`.

Each row is one entry in COLLECTIONS: a title, a one-line description and a
rule (genres, minimum number of ratings, sort order). The page shows every row
that has at least one movie, so rows can be added, removed or reordered here
without touching the template; a row whose genres are missing from the data
(e.g. the 6-genre sample DB) just disappears.

Read-only: no writes, no external API calls. `GET /api/collections` returns
the same rows as JSON.

The signed-in user's "Continue Watching" row (`load_continue_watching`) comes
first on `/` and also appears on `/home`; its cards carry a progress bar.
`GET /api/continue-watching` returns it as JSON.
"""
from flask import Blueprint, jsonify

from . import db
from .auth import load_current_user

bp = Blueprint("browse", __name__, url_prefix="/api")

MOVIES_PER_ROW = 20

# key: URL-safe id. genres: movie must have at least one of them (empty = any).
# min_ratings: ignore movies with fewer ratings. sort: a key of ORDER_BY.
# min_year: only movies released in or after this year (None = any).
COLLECTIONS = [
    {"key": "popular", "title": "Popular on Recco",
     "description": "The movies our members rate most often.",
     "genres": [], "min_ratings": 1, "sort": "popular"},
    {"key": "top-rated", "title": "Top Rated",
     "description": "Highest average score among movies with at least 50 ratings.",
     "genres": [], "min_ratings": 50, "sort": "top_rated"},
    {"key": "family", "title": "Family Movies",
     "description": "Animated and children's films the whole family can enjoy together.",
     "genres": ["Children", "Animation"], "min_ratings": 5, "sort": "popular"},
    {"key": "sci-fi", "title": "Sci-Fi & Fantasy",
     "description": "Other worlds, distant futures and a little bit of magic.",
     "genres": ["Sci-Fi", "Fantasy"], "min_ratings": 5, "sort": "popular"},
    {"key": "comedy", "title": "Laugh Out Loud",
     "description": "Comedies for when you just want to have a good time.",
     "genres": ["Comedy"], "min_ratings": 5, "sort": "popular"},
    {"key": "thriller", "title": "Edge of Your Seat",
     "description": "Thrillers and crime stories that keep you guessing.",
     "genres": ["Thriller", "Crime"], "min_ratings": 5, "sort": "popular"},
    {"key": "romance", "title": "Love Stories",
     "description": "Romantic films, from sweet to heartbreaking.",
     "genres": ["Romance"], "min_ratings": 5, "sort": "popular"},
    {"key": "documentary", "title": "Real Stories",
     "description": "Documentaries about real people and real events.",
     "genres": ["Documentary"], "min_ratings": 3, "sort": "popular"},
    {"key": "recent", "title": "Recent Releases",
     "description": "Popular movies released in 2015 or later.",
     "genres": [], "min_ratings": 3, "sort": "popular", "min_year": 2015},
]

# Fixed SQL fragments chosen by key; nothing user-supplied is ever pasted in.
ORDER_BY = {
    "popular":   "rating_count DESC, avg_score DESC, m.movie_id",
    "top_rated": "avg_score DESC, rating_count DESC, m.movie_id",
}
GENRE_FILTER = """
  AND EXISTS (SELECT 1 FROM movie_genres mg JOIN genres g ON g.genre_id = mg.genre_id
              WHERE mg.movie_id = m.movie_id AND g.name IN %(genres)s)"""
YEAR_FILTER = "\n  AND m.release_year >= %(min_year)s"

ROW_SQL = """
SELECT m.movie_id, m.title, m.release_year, m.poster_url,
       COUNT(r.user_id) AS rating_count, AVG(r.score) AS avg_score
FROM movies m
LEFT JOIN ratings r ON r.movie_id = m.movie_id
WHERE 1 = 1{filters}
GROUP BY m.movie_id, m.title, m.release_year, m.poster_url
HAVING COUNT(r.user_id) >= %(min_ratings)s
ORDER BY {order_by}
LIMIT %(limit)s
"""


def _row_movies(cur, spec, limit):
    filters, params = "", {"min_ratings": spec["min_ratings"], "limit": limit}
    if spec["genres"]:
        filters += GENRE_FILTER
        params["genres"] = tuple(spec["genres"])   # PyMySQL expands a tuple for IN
    if spec.get("min_year"):
        filters += YEAR_FILTER
        params["min_year"] = spec["min_year"]
    cur.execute(ROW_SQL.format(filters=filters, order_by=ORDER_BY[spec["sort"]]), params)
    return [{"movie_id": r["movie_id"], "title": r["title"],
             "release_year": r["release_year"], "poster_url": r["poster_url"],
             "rating_count": r["rating_count"],
             "avg_score": round(float(r["avg_score"]), 2) if r["avg_score"] is not None else None}
            for r in cur.fetchall()]


# "Continue watching" = query (3) of sql/03_queries.sql (latest view event per
# movie, progress < 90), plus the columns a movie card needs.
FINISHED = 90   # progress >= 90 means finished (AGENTS.md business rules)
CONTINUE_WATCHING_SQL = """
SELECT m.movie_id, m.title, m.release_year, m.poster_url, lv.progress, lv.viewed_at AS last_viewed,
       (SELECT AVG(r.score) FROM ratings r WHERE r.movie_id = m.movie_id) AS avg_score
FROM  (SELECT ve.movie_id, ve.progress, ve.viewed_at, ve.event_id,
              ROW_NUMBER() OVER (PARTITION BY ve.movie_id
                                 ORDER BY ve.viewed_at DESC, ve.event_id DESC) AS rn
       FROM   view_events ve
       WHERE  ve.user_id = %(user_id)s) AS lv
JOIN   movies m ON m.movie_id = lv.movie_id
WHERE  lv.rn = 1
  AND  lv.progress < %(finished)s
ORDER BY lv.viewed_at DESC, lv.event_id DESC
LIMIT %(limit)s
"""
CONTINUE_WATCHING_ROW = {
    "key": "continue", "title": "Continue Watching",
    "description": "Pick up right where you left off. Most recently watched first.",
}


def load_continue_watching(user, limit=MOVIES_PER_ROW):
    """The signed-in user's unfinished movies as one row, or None (signed out / nothing)."""
    if user is None:
        return None
    with db.get_db().cursor() as cur:
        cur.execute(CONTINUE_WATCHING_SQL, {"user_id": user["user_id"], "finished": FINISHED,
                                            "limit": limit})
        movies = [{"movie_id": r["movie_id"], "title": r["title"],
                   "release_year": r["release_year"], "poster_url": r["poster_url"],
                   "progress": r["progress"],
                   "last_viewed": r["last_viewed"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "avg_score": round(float(r["avg_score"]), 2) if r["avg_score"] is not None else None}
                  for r in cur.fetchall()]
    return dict(CONTINUE_WATCHING_ROW, movies=movies) if movies else None


def load_collections(limit=MOVIES_PER_ROW):
    """Every non-empty row of COLLECTIONS, in order, with its movies."""
    rows = []
    with db.get_db().cursor() as cur:
        for spec in COLLECTIONS:
            movies = _row_movies(cur, spec, limit)
            if movies:
                rows.append({"key": spec["key"], "title": spec["title"],
                             "description": spec["description"], "movies": movies})
    return rows


@bp.route("/collections")
def list_collections():
    return jsonify({"collections": load_collections()})


@bp.route("/continue-watching")
def continue_watching_api():
    """The signed-in user's continue-watching row as JSON (401 when signed out)."""
    user = load_current_user()
    if user is None:
        return jsonify({"error": {"code": "login_required", "message": "log in to do this"}}), 401
    row = load_continue_watching(user)
    return jsonify({"items": row["movies"] if row else []})
