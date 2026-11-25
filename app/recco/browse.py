"""Movie rows ("collections") for the public landing page `/`.

Each row is one entry in COLLECTIONS: a title, a one-line description and a
rule (genres, minimum number of ratings, sort order). The page shows every row
that has at least one movie, so rows can be added, removed or reordered here
without touching the template; a row whose genres are missing from the data
(e.g. the 6-genre sample DB) just disappears.

Read-only: no writes, no external API calls. `GET /api/collections` returns
the same rows as JSON.
"""
from flask import Blueprint, jsonify

from . import db

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
