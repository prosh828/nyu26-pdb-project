"""The signed-in user's watchlist and hidden ("not interested") movies.

API (JSON; errors are {"error": {"code", "message"}})
  GET    /api/watchlist             the user's watchlist, newest first
  PUT    /api/watchlist/<id>        add a movie (also un-hides it)
  DELETE /api/watchlist/<id>        remove a movie
  GET    /api/hidden                the user's hidden movies, newest first
  PUT    /api/hidden/<id>           hide a movie (also takes it off the watchlist)
  DELETE /api/hidden/<id>           un-hide a movie
Every write answers {"movie_id", "in_watchlist", "hidden"} and is idempotent.

A movie is either on the watchlist or hidden, never both: each PUT removes the
movie from the other table in the same transaction. Hidden movies are left out
of the landing-page rows (`browse.load_collections`) and of the search fill
(`search.search`); a title match in search, the watch page and Continue Watching
still show them.

Writes need a signed-in user (401 otherwise). They take no body; PUT and DELETE
cannot be sent by a cross-site HTML form, and a cross-site fetch with them needs a
CORS preflight that this app never grants, so no CSRF token is needed.
"""
from flask import Blueprint, g, jsonify

from . import db
from .auth import load_current_user
from .watch import ApiError, api_error

bp = Blueprint("lists", __name__, url_prefix="/api")
bp.register_error_handler(ApiError, api_error)

# table -> (timestamp column). Table names come from this dict only, never from the URL.
TABLES = {"watchlist": "added_at", "hidden_movies": "hidden_at"}
OTHER = {"watchlist": "hidden_movies", "hidden_movies": "watchlist"}

MOVIE_EXISTS_SQL = "SELECT 1 FROM movies WHERE movie_id = %(movie_id)s"
# Adding again keeps the first timestamp (the no-op UPDATE leaves the row as it is).
ADD_SQL = """
INSERT INTO {table} (user_id, movie_id) VALUES (%(user_id)s, %(movie_id)s) AS new
ON DUPLICATE KEY UPDATE user_id = new.user_id
"""
REMOVE_SQL = "DELETE FROM {table} WHERE user_id = %(user_id)s AND movie_id = %(movie_id)s"
STATE_SQL = """
SELECT EXISTS (SELECT 1 FROM watchlist     WHERE user_id = %(user_id)s AND movie_id = %(movie_id)s) AS in_watchlist,
       EXISTS (SELECT 1 FROM hidden_movies WHERE user_id = %(user_id)s AND movie_id = %(movie_id)s) AS hidden
"""
MY_IDS_SQL = """
SELECT 'watchlist' AS list, movie_id FROM watchlist     WHERE user_id = %(user_id)s
UNION ALL
SELECT 'hidden',            movie_id FROM hidden_movies WHERE user_id = %(user_id)s
"""
# The cards' columns, newest addition first.
LIST_SQL = """
SELECT m.movie_id, m.title, m.release_year, m.poster_url, l.{ts} AS listed_at,
       (SELECT AVG(r.score) FROM ratings r WHERE r.movie_id = m.movie_id) AS avg_score
FROM   {table} l
JOIN   movies m ON m.movie_id = l.movie_id
WHERE  l.user_id = %(user_id)s
ORDER BY l.{ts} DESC, m.movie_id
LIMIT %(limit)s
"""
LIST_LIMIT = 100

WATCHLIST_ROW = {"key": "watchlist", "title": "My Watchlist",
                 "description": "Movies you saved for later, newest first. Use − to take one off the list.",
                 "empty": "Your watchlist is empty. Hover over a poster and press + to save a movie for later."}
HIDDEN_ROW = {"key": "hidden", "title": "Hidden Movies",
              "description": "Titles you marked as not interested. They stay out of your recommendations; "
                             "press the thumbs-up to bring one back.",
              "empty": "No hidden movies. Press the thumbs-down on a poster to stop seeing it in recommendations."}


def get_state(cur, user_id, movie_id):
    cur.execute(STATE_SQL, {"user_id": user_id, "movie_id": movie_id})
    s = cur.fetchone()
    return {"movie_id": movie_id, "in_watchlist": bool(s["in_watchlist"]), "hidden": bool(s["hidden"])}


def my_list_ids():
    """{"watchlist": set(ids), "hidden": set(ids)} for the signed-in user, cached per request.

    Registered as a Jinja global so the `movie_row` macro can mark its buttons."""
    if "my_list_ids" not in g:
        ids = {"watchlist": set(), "hidden": set()}
        user = load_current_user()
        if user is not None:
            with db.get_db().cursor() as cur:
                cur.execute(MY_IDS_SQL, {"user_id": user["user_id"]})
                for r in cur.fetchall():
                    ids[r["list"]].add(r["movie_id"])
        g.my_list_ids = ids
    return g.my_list_ids


def load_list(user, table, limit=LIST_LIMIT):
    with db.get_db().cursor() as cur:
        cur.execute(LIST_SQL.format(table=table, ts=TABLES[table]),
                    {"user_id": user["user_id"], "limit": limit})
        return [{"movie_id": r["movie_id"], "title": r["title"], "release_year": r["release_year"],
                 "poster_url": r["poster_url"],
                 "listed_at": r["listed_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "avg_score": round(float(r["avg_score"]), 2) if r["avg_score"] is not None else None}
                for r in cur.fetchall()]


def load_rows(user):
    """(watchlist row, hidden row) for /home; each row's movies may be empty."""
    return (dict(WATCHLIST_ROW, movies=load_list(user, "watchlist")),
            dict(HIDDEN_ROW, movies=load_list(user, "hidden_movies")))


def _signed_in():
    user = load_current_user()
    if user is None:
        raise ApiError(401, "login_required", "log in to do this")
    return user


def _write(table, movie_id, add):
    user = _signed_in()
    params = {"user_id": user["user_id"], "movie_id": movie_id}
    conn = db.get_db()
    with conn.cursor() as cur:
        cur.execute(MOVIE_EXISTS_SQL, params)
        if cur.fetchone() is None:
            raise ApiError(404, "not_found", f"movie {movie_id} does not exist")
        try:
            if add:     # one transaction: on the watchlist or hidden, never both
                cur.execute(REMOVE_SQL.format(table=OTHER[table]), params)
                cur.execute(ADD_SQL.format(table=table), params)
            else:
                cur.execute(REMOVE_SQL.format(table=table), params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return jsonify(get_state(cur, user["user_id"], movie_id))


@bp.route("/watchlist")
def watchlist_api():
    return jsonify({"items": load_list(_signed_in(), "watchlist")})


@bp.route("/hidden")
def hidden_api():
    return jsonify({"items": load_list(_signed_in(), "hidden_movies")})


@bp.route("/watchlist/<int:movie_id>", methods=["PUT"])
def add_to_watchlist(movie_id):
    return _write("watchlist", movie_id, add=True)


@bp.route("/watchlist/<int:movie_id>", methods=["DELETE"])
def remove_from_watchlist(movie_id):
    return _write("watchlist", movie_id, add=False)


@bp.route("/hidden/<int:movie_id>", methods=["PUT"])
def hide(movie_id):
    return _write("hidden_movies", movie_id, add=True)


@bp.route("/hidden/<int:movie_id>", methods=["DELETE"])
def unhide(movie_id):
    return _write("hidden_movies", movie_id, add=False)
