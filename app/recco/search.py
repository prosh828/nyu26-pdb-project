"""Movie search by title: the /search page, its live-update fragment, and the JSON API.

Ranking (see `search()`):
1. A title matches when it shares a run of at least `required_overlap(q)`
   consecutive characters with the query: MIN_OVERLAP_RATIO (2/3) of the
   query's length, never fewer than MIN_OVERLAP = 2 characters. Comparison ignores case,
   accents and repeated spaces.
2. Matches are ordered by the length of that longest shared run, then exact
   title, title starting with the query, query at a word start, then the
   number of ratings.
3. At most MAX_RESULTS movies are shown. If fewer titles match, the rest is
   filled with the highest-rated movies of the same genre: the genre filter if
   one is chosen, otherwise the genres of the best match.

The genre / minimum-average-rating filters apply to both the matches and the
fill. Everything is read-only.
"""
import math
import unicodedata

from flask import Blueprint, jsonify, render_template, request

from . import db

bp = Blueprint("search", __name__)

MAX_RESULTS = 20
MIN_OVERLAP = 2          # minimum shared characters between query and title
MIN_OVERLAP_RATIO = 2 / 3   # ...and at least this share of the query's length
MIN_QUERY_LENGTH = 2     # the page searches from the 2nd typed letter on
MAX_QUERY_LENGTH = 50
RATING_OPTIONS = (3.0, 3.5, 4.0, 4.5)   # "average rating at least ..." choices
FILL_MIN_RATINGS = 20    # fill movies need this many ratings to count as "highly rated"
LIKE_ESCAPE = "!"

STATS_COLUMNS = """m.movie_id, m.title, m.release_year, m.poster_url,
       COUNT(r.user_id) AS rating_count, AVG(r.score) AS avg_score"""
GENRE_FILTER = "\n  AND EXISTS (SELECT 1 FROM movie_genres mg WHERE mg.movie_id = m.movie_id AND mg.genre_id IN %(genre_ids)s)"
EXCLUDE_FILTER = "\n  AND m.movie_id NOT IN %(exclude)s"

# {title_filter}: "(m.title LIKE %(p0)s ESCAPE '!' OR ...)", built from the
# query's substrings; every value is a bound parameter.
CANDIDATES_SQL = """
SELECT """ + STATS_COLUMNS + """
FROM movies m
LEFT JOIN ratings r ON r.movie_id = m.movie_id
WHERE {title_filter}{genre_filter}
GROUP BY m.movie_id, m.title, m.release_year, m.poster_url
HAVING %(min_rating)s IS NULL OR AVG(r.score) >= %(min_rating)s
"""

FILL_SQL = """
SELECT """ + STATS_COLUMNS + """
FROM movies m
JOIN ratings r ON r.movie_id = m.movie_id
WHERE 1 = 1{genre_filter}{exclude_filter}
GROUP BY m.movie_id, m.title, m.release_year, m.poster_url
HAVING COUNT(r.user_id) >= %(fill_min_ratings)s
   AND (%(min_rating)s IS NULL OR AVG(r.score) >= %(min_rating)s)
ORDER BY avg_score DESC, rating_count DESC, m.movie_id
LIMIT %(limit)s
"""

GENRES_SQL = "SELECT genre_id, name FROM genres ORDER BY name"
MOVIE_GENRES_SQL = """
SELECT g.genre_id, g.name FROM movie_genres mg JOIN genres g ON g.genre_id = mg.genre_id
WHERE mg.movie_id = %(movie_id)s ORDER BY g.name
"""


# --- text matching ----------------------------------------------------------
def normalize(text):
    """Lower case, accents removed, runs of whitespace collapsed."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())


def required_overlap(q):
    """Shared characters a title needs: 2/3 of the query, at least MIN_OVERLAP."""
    return min(len(q), max(MIN_OVERLAP, math.ceil(len(q) * MIN_OVERLAP_RATIO - 1e-9)))


def overlap(q, title):
    """Length of the longest run of characters `q` and `title` share (normalized)."""
    for length in range(len(q), 0, -1):
        for start in range(len(q) - length + 1):
            if q[start:start + length] in title:
                return length
    return 0


def _like(text):
    escaped = (text.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
                   .replace("%", LIKE_ESCAPE + "%").replace("_", LIKE_ESCAPE + "_"))
    return "%" + escaped + "%"


def _movie(row, overlap_len=None):
    return {"movie_id": row["movie_id"], "title": row["title"],
            "release_year": row["release_year"], "poster_url": row["poster_url"],
            "rating_count": row["rating_count"],
            "avg_score": round(float(row["avg_score"]), 2) if row["avg_score"] is not None else None,
            "overlap": overlap_len}


# --- search -----------------------------------------------------------------
def search(cur, q, genre_id=None, min_rating=None):
    """{"matches": [...], "fill": [...], "fill_genres": [...]}, at most MAX_RESULTS movies."""
    nq = normalize(q)[:MAX_QUERY_LENGTH]
    need = required_overlap(nq)
    # Every title sharing `need` characters contains one of the query's
    # substrings of exactly that length, so this LIKE pre-filter loses nothing.
    pieces = sorted({nq[i:i + need] for i in range(len(nq) - need + 1)})
    params = {f"p{i}": _like(p) for i, p in enumerate(pieces)}
    params["min_rating"] = min_rating
    title_filter = "(" + " OR ".join(f"m.title LIKE %(p{i})s ESCAPE '!'" for i in range(len(pieces))) + ")"
    genre_filter = ""
    if genre_id is not None:
        genre_filter, params["genre_ids"] = GENRE_FILTER, (genre_id,)
    cur.execute(CANDIDATES_SQL.format(title_filter=title_filter, genre_filter=genre_filter), params)

    scored = []
    for row in cur.fetchall():
        title = normalize(row["title"])
        length = overlap(nq, title)
        if length < need:          # LIKE is looser than normalize() in rare cases
            continue
        tier = (0 if title == nq else 1 if title.startswith(nq) else
                2 if (" " + nq) in (" " + title) else 3)
        scored.append(((-length, tier, -row["rating_count"], row["title"], row["movie_id"]), row, length))
    scored.sort(key=lambda s: s[0])
    matches = [_movie(row, length) for _, row, length in scored[:MAX_RESULTS]]

    fill, fill_genres = [], []
    missing = MAX_RESULTS - len(matches)
    if missing > 0:
        if genre_id is not None:
            cur.execute("SELECT genre_id, name FROM genres WHERE genre_id = %(g)s", {"g": genre_id})
            fill_genres = cur.fetchall()
        elif matches:
            cur.execute(MOVIE_GENRES_SQL, {"movie_id": matches[0]["movie_id"]})
            fill_genres = cur.fetchall()
        fparams = {"fill_min_ratings": FILL_MIN_RATINGS, "min_rating": min_rating, "limit": missing}
        gfilter = efilter = ""
        if fill_genres:
            gfilter, fparams["genre_ids"] = GENRE_FILTER, tuple(g["genre_id"] for g in fill_genres)
        if matches:
            efilter, fparams["exclude"] = EXCLUDE_FILTER, tuple(m["movie_id"] for m in matches)
        cur.execute(FILL_SQL.format(genre_filter=gfilter, exclude_filter=efilter), fparams)
        fill = [_movie(row) for row in cur.fetchall()]
    return {"matches": matches, "fill": fill, "fill_genres": [g["name"] for g in fill_genres]}


# --- request handling -------------------------------------------------------
def _params(cur):
    """(q, genre_id, min_rating, genres) from the query string; bad values are ignored."""
    q = " ".join(request.args.get("q", "").split())[:MAX_QUERY_LENGTH]
    cur.execute(GENRES_SQL)
    genres = cur.fetchall()
    raw_genre = request.args.get("genre", "")
    genre_id = int(raw_genre) if raw_genre.isdigit() and any(
        g["genre_id"] == int(raw_genre) for g in genres) else None
    try:
        min_rating = float(request.args.get("min_rating", ""))
    except ValueError:
        min_rating = None
    if min_rating not in RATING_OPTIONS:
        min_rating = None
    return q, genre_id, min_rating, genres


def _rows(q, result):
    """The search result as movie rows for templates/_movies.html."""
    rows = []
    if result["matches"]:
        rows.append({"key": "matches", "title": f'Results for "{q}"',
                     "description": f'{len(result["matches"])} titles match your search, closest first.',
                     "movies": result["matches"]})
    if result["fill"]:
        names = result["fill_genres"]
        genres = (", ".join(names[:-1]) + " & " + names[-1]) if len(names) > 1 else "".join(names)
        rows.append({"key": "fill",
                     "title": f"More {genres} movies" if genres else "Top rated movies",
                     "description": (f"Highly rated {genres} movies to round out your results."
                                     if genres else "Highly rated movies you might like instead."),
                     "movies": result["fill"]})
    return rows


def _run():
    with db.get_db().cursor() as cur:
        q, genre_id, min_rating, genres = _params(cur)
        result = search(cur, q, genre_id, min_rating) if len(q) >= MIN_QUERY_LENGTH else None
    return {"q": q, "genre_id": genre_id, "min_rating": min_rating, "genres": genres,
            "result": result, "rows": _rows(q, result) if result else []}


@bp.route("/search")
def search_page():
    ctx = _run()
    return render_template("search.html", rating_options=RATING_OPTIONS,
                           min_query_length=MIN_QUERY_LENGTH, **ctx)


@bp.route("/search/results")
def search_results():
    """HTML fragment the search page swaps in while the user types."""
    return render_template("_search_results.html", min_query_length=MIN_QUERY_LENGTH, **_run())


@bp.route("/api/search")
def search_api():
    ctx = _run()
    result = ctx["result"] or {"matches": [], "fill": [], "fill_genres": []}
    return jsonify({"query": {"q": ctx["q"], "genre": ctx["genre_id"], "min_rating": ctx["min_rating"]},
                    **result})
