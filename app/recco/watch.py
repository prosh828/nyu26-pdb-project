"""Movie watch page and the rating / review / progress JSON API.

Page
  GET    /movies/<id>                  player (simulated: poster + play/pause + time bar),
                                       details, reviews, and the signed-in user's own rating
API (JSON; errors are {"error": {"code", "message"}})
  GET    /api/movies/<id>              details + rating stats (+ "my_rating" when signed in)
  GET    /api/movies/<id>/reviews      ratings that have review text, newest first (?page=, ?page_size=)
  PUT    /api/movies/<id>/rating       {"score": 0.5-5.0 in half steps, "review": "..." | null}
  DELETE /api/movies/<id>/rating       remove the signed-in user's rating and review
  POST   /api/movies/<id>/progress     {"progress": 0-100}: append a view_events row

A review is the `review` column of `ratings`, so a review always comes with a
score (the schema requires one). Writes need a signed-in user (401 otherwise) and
a JSON body (415 otherwise): a cross-site HTML form cannot send JSON, which is
what keeps these endpoints safe without a CSRF token. Every write commits
immediately, so the page shows the same values when the user comes back.
"""
import math
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, jsonify, render_template, request

from . import db
from .auth import load_current_user

bp = Blueprint("watch", __name__)

REVIEW_MAX_LENGTH = 2000
REVIEWS_PAGE_SIZE = 20
MAX_REVIEWS_PAGE_SIZE = 100
DEFAULT_RUNTIME = 100          # minutes, for the player when TMDB had no runtime
FINISHED = 90                  # progress >= 90 means finished (AGENTS.md business rules)

MOVIE_SQL = """
SELECT m.movie_id, m.title, m.release_year, m.runtime, m.tmdb_id, m.poster_url
FROM movies m WHERE m.movie_id = %(movie_id)s
"""
GENRES_SQL = """
SELECT g.name FROM movie_genres mg JOIN genres g ON g.genre_id = mg.genre_id
WHERE mg.movie_id = %(movie_id)s ORDER BY g.name
"""
STATS_SQL = """
SELECT COUNT(*) AS rating_count, AVG(score) AS avg_score,
       SUM(review IS NOT NULL AND review <> '') AS review_count
FROM ratings WHERE movie_id = %(movie_id)s
"""
REVIEWS_SQL = """
SELECT r.user_id, u.username, r.score, r.review, r.rated_at
FROM ratings r JOIN users u ON u.user_id = r.user_id
WHERE r.movie_id = %(movie_id)s AND r.review IS NOT NULL AND r.review <> ''
ORDER BY r.rated_at DESC, r.user_id
LIMIT %(limit)s OFFSET %(offset)s
"""
MY_RATING_SQL = """
SELECT score, review, rated_at FROM ratings
WHERE user_id = %(user_id)s AND movie_id = %(movie_id)s
"""
# Same statement as query (2) in sql/03_queries.sql.
UPSERT_RATING_SQL = """
INSERT INTO ratings (user_id, movie_id, score, review)
VALUES (%(user_id)s, %(movie_id)s, %(score)s, %(review)s) AS new
ON DUPLICATE KEY UPDATE score    = new.score,
                        review   = new.review,
                        rated_at = CURRENT_TIMESTAMP
"""
DELETE_RATING_SQL = "DELETE FROM ratings WHERE user_id = %(user_id)s AND movie_id = %(movie_id)s"
LAST_PROGRESS_SQL = """
SELECT progress FROM view_events
WHERE user_id = %(user_id)s AND movie_id = %(movie_id)s
ORDER BY viewed_at DESC, event_id DESC LIMIT 1
"""
INSERT_VIEW_SQL = """
INSERT INTO view_events (user_id, movie_id, progress)
VALUES (%(user_id)s, %(movie_id)s, %(progress)s)
"""


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@bp.errorhandler(ApiError)
def api_error(err):
    return jsonify({"error": {"code": err.code, "message": err.message}}), err.status


# --- reads ------------------------------------------------------------------
def _score(value):
    return float(value) if value is not None else None


def _iso(ts):
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None   # stored in UTC


def get_movie(cur, movie_id):
    cur.execute(MOVIE_SQL, {"movie_id": movie_id})
    movie = cur.fetchone()
    if movie is None:
        return None
    cur.execute(GENRES_SQL, {"movie_id": movie_id})
    movie["genres"] = [r["name"] for r in cur.fetchall()]
    return movie


def get_stats(cur, movie_id):
    cur.execute(STATS_SQL, {"movie_id": movie_id})
    s = cur.fetchone()
    return {"rating_count": s["rating_count"],
            "avg_score": round(float(s["avg_score"]), 2) if s["avg_score"] is not None else None,
            "review_count": int(s["review_count"] or 0)}


def get_reviews(cur, movie_id, page=1, page_size=REVIEWS_PAGE_SIZE):
    cur.execute(REVIEWS_SQL, {"movie_id": movie_id, "limit": page_size,
                              "offset": (page - 1) * page_size})
    return [{"user_id": r["user_id"], "username": r["username"], "score": _score(r["score"]),
             "review": r["review"], "rated_at": _iso(r["rated_at"])} for r in cur.fetchall()]


def get_my_rating(cur, user, movie_id):
    if user is None:
        return None
    cur.execute(MY_RATING_SQL, {"user_id": user["user_id"], "movie_id": movie_id})
    r = cur.fetchone()
    return {"score": _score(r["score"]), "review": r["review"],
            "rated_at": _iso(r["rated_at"])} if r else None


def get_resume_progress(cur, user, movie_id):
    """Last saved progress (0-99) to resume from; a finished movie starts over."""
    if user is None:
        return 0
    cur.execute(LAST_PROGRESS_SQL, {"user_id": user["user_id"], "movie_id": movie_id})
    r = cur.fetchone()
    return r["progress"] if r and r["progress"] < FINISHED else 0


def _movie_or_404(cur, movie_id, api=True):
    movie = get_movie(cur, movie_id)
    if movie is None:
        if api:
            raise ApiError(404, "not_found", f"movie {movie_id} does not exist")
        abort(404)
    return movie


def _movie_json(movie):
    return {"movie_id": movie["movie_id"], "title": movie["title"],
            "release_year": movie["release_year"], "runtime": movie["runtime"],
            "tmdb_id": movie["tmdb_id"], "poster_url": movie["poster_url"],
            "genres": movie["genres"]}


# --- input validation -------------------------------------------------------
def parse_score(value):
    """0.5 .. 5.0 in steps of 0.5 (ratings_score_chk), as Decimal."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ApiError(400, "invalid_parameter", "score must be a number from 0.5 to 5.0 in steps of 0.5")
    try:
        score = Decimal(str(value).strip())
    except InvalidOperation:
        score = None
    if score is None or not score.is_finite() or not Decimal("0.5") <= score <= Decimal("5") \
            or (score * 2) % 1 != 0:
        raise ApiError(400, "invalid_parameter", "score must be a number from 0.5 to 5.0 in steps of 0.5")
    return score.quantize(Decimal("0.1"))


def parse_review(value):
    """Optional text; blank becomes NULL."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiError(400, "invalid_parameter", "review must be text or null")
    value = value.strip().replace("\r\n", "\n")
    if len(value) > REVIEW_MAX_LENGTH:
        raise ApiError(400, "invalid_parameter", f"review must be at most {REVIEW_MAX_LENGTH} characters")
    return value or None


def parse_progress(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or not 0 <= value <= 100:
        raise ApiError(400, "invalid_parameter", "progress must be a number from 0 to 100")
    return int(value)


def _signed_in_json_body():
    user = load_current_user()
    if user is None:
        raise ApiError(401, "login_required", "log in to do this")
    body = request.get_json(silent=True) if request.is_json else None
    if not isinstance(body, dict):
        raise ApiError(415, "json_required", "send a JSON object with Content-Type: application/json")
    return user, body


def _page_param(name, default, high):
    raw = request.args.get(name)
    if raw is None:
        return default
    if not raw.isdigit() or not 1 <= int(raw) <= high:
        raise ApiError(400, "invalid_parameter", f"{name} must be an integer between 1 and {high}")
    return int(raw)


# --- page -------------------------------------------------------------------
@bp.route("/movies/<int:movie_id>")
def watch_page(movie_id):
    user = load_current_user()
    with db.get_db().cursor() as cur:
        movie = _movie_or_404(cur, movie_id, api=False)
        ctx = {"movie": movie, "stats": get_stats(cur, movie_id),
               "reviews": get_reviews(cur, movie_id),
               "my_rating": get_my_rating(cur, user, movie_id),
               "resume_progress": get_resume_progress(cur, user, movie_id)}
    return render_template("watch.html", runtime=movie["runtime"] or DEFAULT_RUNTIME,
                           reviews_page_size=REVIEWS_PAGE_SIZE,
                           review_max_length=REVIEW_MAX_LENGTH, **ctx)


# --- API --------------------------------------------------------------------
@bp.route("/api/movies/<int:movie_id>")
def movie_api(movie_id):
    user = load_current_user()
    with db.get_db().cursor() as cur:
        movie = _movie_or_404(cur, movie_id)
        body = {"movie": _movie_json(movie), "stats": get_stats(cur, movie_id)}
        if user is not None:
            body["my_rating"] = get_my_rating(cur, user, movie_id)
    return jsonify(body)


@bp.route("/api/movies/<int:movie_id>/reviews")
def reviews_api(movie_id):
    page = _page_param("page", 1, 100000)
    page_size = _page_param("page_size", REVIEWS_PAGE_SIZE, MAX_REVIEWS_PAGE_SIZE)
    with db.get_db().cursor() as cur:
        _movie_or_404(cur, movie_id)
        stats = get_stats(cur, movie_id)
        items = get_reviews(cur, movie_id, page, page_size)
    return jsonify({"items": items, "stats": stats,
                    "pagination": {"page": page, "page_size": page_size,
                                   "total_items": stats["review_count"],
                                   "total_pages": math.ceil(stats["review_count"] / page_size)}})


@bp.route("/api/movies/<int:movie_id>/rating", methods=["PUT"])
def put_rating(movie_id):
    user, body = _signed_in_json_body()
    score = parse_score(body.get("score"))
    review = parse_review(body.get("review"))
    conn = db.get_db()
    with conn.cursor() as cur:
        _movie_or_404(cur, movie_id)
        try:
            cur.execute(UPSERT_RATING_SQL, {"user_id": user["user_id"], "movie_id": movie_id,
                                            "score": score, "review": review})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return jsonify({"my_rating": get_my_rating(cur, user, movie_id),
                        "stats": get_stats(cur, movie_id)})


@bp.route("/api/movies/<int:movie_id>/rating", methods=["DELETE"])
def delete_rating(movie_id):
    user = load_current_user()
    if user is None:
        raise ApiError(401, "login_required", "log in to do this")
    conn = db.get_db()
    with conn.cursor() as cur:
        _movie_or_404(cur, movie_id)
        cur.execute(DELETE_RATING_SQL, {"user_id": user["user_id"], "movie_id": movie_id})
        conn.commit()
        return jsonify({"my_rating": None, "stats": get_stats(cur, movie_id)})


@bp.route("/api/movies/<int:movie_id>/progress", methods=["POST"])
def post_progress(movie_id):
    user, body = _signed_in_json_body()
    progress = parse_progress(body.get("progress"))
    conn = db.get_db()
    with conn.cursor() as cur:
        _movie_or_404(cur, movie_id)
        cur.execute(INSERT_VIEW_SQL, {"user_id": user["user_id"], "movie_id": movie_id,
                                      "progress": progress})
        conn.commit()
    return "", 204
