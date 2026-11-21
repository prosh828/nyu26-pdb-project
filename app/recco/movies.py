"""Movie browsing JSON API: GET /api/movies (title search + pagination).

Read-only: no writes, so no commit is needed. No external API is called.
"""
import json
import math
import re

from flask import Blueprint, jsonify, request

from . import db

bp = Blueprint("movies", __name__, url_prefix="/api")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_PAGE = 100000
MAX_QUERY_LENGTH = 100
LIKE_ESCAPE = "!"  # backslash is ambiguous in MySQL string literals

_DIGITS = re.compile(r"[0-9]+")

# Same WHERE clause in both statements. A literal '%' would have to be written
# '%%' here because PyMySQL formats the statement; there is none.
COUNT_MOVIES_SQL = """
SELECT COUNT(*) AS total
FROM movies
WHERE title LIKE %(pattern)s ESCAPE '!'
"""

# Cut the page out of `movies` first, then attach the genres, so the genre join
# cannot change which movies are on the page. A movie without genres yields [null].
LIST_MOVIES_SQL = """
SELECT p.movie_id, p.title, p.release_year,
       JSON_ARRAYAGG(g.name) AS genres
FROM (
    SELECT movie_id, title, release_year
    FROM movies
    WHERE title LIKE %(pattern)s ESCAPE '!'
    ORDER BY title, movie_id
    LIMIT %(limit)s OFFSET %(offset)s
) AS p
LEFT JOIN movie_genres mg ON mg.movie_id = p.movie_id
LEFT JOIN genres g        ON g.genre_id = mg.genre_id
GROUP BY p.movie_id, p.title, p.release_year
ORDER BY p.title, p.movie_id
"""


class ParamError(ValueError):
    def __init__(self, param, message):
        super().__init__(message)
        self.param = param
        self.message = message


def escape_like(text):
    """Make `text` match literally inside LIKE ... ESCAPE '!'."""
    return (text.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
                .replace("%", LIKE_ESCAPE + "%")
                .replace("_", LIKE_ESCAPE + "_"))


def _single_value(name):
    """The only value of a query parameter, None if absent; repeats are an error."""
    values = request.args.getlist(name)
    if len(values) > 1:
        raise ParamError(name, "must be given at most once")
    return values[0] if values else None


def _int_param(name, default, low, high):
    raw = _single_value(name)
    if raw is None:
        return default
    if not _DIGITS.fullmatch(raw):
        raise ParamError(name, f"must be an integer between {low} and {high}")
    value = int(raw)
    if not low <= value <= high:
        raise ParamError(name, f"must be an integer between {low} and {high}")
    return value


def parse_params():
    q = (_single_value("q") or "").strip()
    if len(q) > MAX_QUERY_LENGTH:
        raise ParamError("q", f"must be at most {MAX_QUERY_LENGTH} characters")
    page = _int_param("page", 1, 1, MAX_PAGE)
    page_size = _int_param("page_size", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
    return q, page, page_size


def _genre_list(value):
    """JSON_ARRAYAGG arrives as text (PyMySQL does not decode JSON); drop the NULL
    a movie without genres produces and sort for a stable order."""
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        value = json.loads(value)
    return sorted(name for name in (value or []) if name is not None)


@bp.errorhandler(ParamError)
def invalid_parameter(err):
    body = {"error": {"code": "invalid_parameter", "param": err.param,
                      "message": err.message}}
    return jsonify(body), 400


@bp.route("/movies")
def list_movies():
    q, page, page_size = parse_params()
    pattern = "%" + escape_like(q) + "%"

    with db.get_db().cursor() as cur:
        cur.execute(COUNT_MOVIES_SQL, {"pattern": pattern})
        total = cur.fetchone()["total"]
        cur.execute(LIST_MOVIES_SQL, {"pattern": pattern, "limit": page_size,
                                      "offset": (page - 1) * page_size})
        rows = cur.fetchall()

    items = [{"movie_id": r["movie_id"], "title": r["title"],
              "release_year": r["release_year"], "genres": _genre_list(r["genres"])}
             for r in rows]
    return jsonify({
        "items": items,
        "pagination": {"page": page, "page_size": page_size, "total_items": total,
                       "total_pages": math.ceil(total / page_size)},
        "query": {"q": q},
    })
