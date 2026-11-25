"""Basic role-specific home pages. Other features add their own routes with
`@login_required` / `@admin_required` from `recco.auth`."""
from flask import Blueprint, render_template

from . import browse, db, lists
from .auth import admin_required, load_current_user, login_required

bp = Blueprint("pages", __name__)

SELECT_USER_GENRES_SQL = """
SELECT g.name
FROM user_genres ug
JOIN genres g ON g.genre_id = ug.genre_id
WHERE ug.user_id = %(user_id)s
ORDER BY g.name
"""


@bp.route("/home")
@login_required
def home():
    user = load_current_user()
    with db.get_db().cursor() as cur:
        cur.execute(SELECT_USER_GENRES_SQL, {"user_id": user["user_id"]})
        genres = [row["name"] for row in cur.fetchall()]
    watchlist_row, hidden_row = lists.load_rows(user)
    return render_template("home.html", genres=genres,
                           continue_row=browse.load_continue_watching(user),
                           watchlist_row=watchlist_row, hidden_row=hidden_row)


@bp.route("/admin")
@admin_required
def admin_home():
    return render_template("admin_home.html")
