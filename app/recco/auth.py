"""Registration, login, logout and the role checks other routes reuse.

Session design: only `user_id` is stored in the (signed) Flask session cookie.
The current user, including `role`, is re-read from the database on each request
that needs it (`load_current_user`), so a deleted user or a changed role takes
effect immediately and the role is never trusted from the client.

Protect a route with `@login_required` (any signed-in user) or `@admin_required`
(role 'admin'). Both are checked on the server; hiding links is only a convenience.
"""
import functools
import re

import pymysql
from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from . import db

bp = Blueprint("auth", __name__)

USERNAME_MAX = 50          # users.username VARCHAR(50)
EMAIL_MAX = 254            # users.email VARCHAR(254)
FAVOURITE_GENRE_COUNT = 3  # proposal: exactly three favourite genres at sign-up
PASSWORD_HASH_METHOD = "pbkdf2:sha256"

ER_DUP_ENTRY = 1062
ER_CHECK_CONSTRAINT_VIOLATED = 3819

_DIGITS = re.compile(r"[0-9]+")
# Same shape as the CHECK on users.email (LIKE '%_@_%._%'); the CHECK stays the last line of defence.
_EMAIL = re.compile(r".+@.+\..+", re.DOTALL)

SELECT_GENRES_SQL = "SELECT genre_id, name FROM genres ORDER BY name"

# role is always 'user' here: visitors can never register as administrators.
INSERT_USER_SQL = """
INSERT INTO users (username, email, password_hash, role)
VALUES (%(username)s, %(email)s, %(password_hash)s, 'user')
"""

INSERT_USER_GENRE_SQL = """
INSERT INTO user_genres (user_id, genre_id)
VALUES (%(user_id)s, %(genre_id)s)
"""

SELECT_LOGIN_SQL = """
SELECT user_id, username, role, password_hash
FROM users
WHERE username = %(username)s
"""

SELECT_USER_BY_ID_SQL = """
SELECT user_id, username, email, role
FROM users
WHERE user_id = %(user_id)s
"""


# --- current user and role checks ------------------------------------------
def load_current_user():
    """The signed-in user (dict with user_id, username, email, role) or None.
    Looked up once per request; a session pointing at a missing user is cleared."""
    if "current_user" not in g:
        user = None
        user_id = session.get("user_id")
        if user_id is not None:
            with db.get_db().cursor() as cur:
                cur.execute(SELECT_USER_BY_ID_SQL, {"user_id": user_id})
                user = cur.fetchone()
            if user is None:
                session.clear()
        g.current_user = user
    return g.current_user


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if load_current_user() is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        user = load_current_user()
        if user is None:
            return redirect(url_for("auth.login"))
        if user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def home_for(user):
    return url_for("pages.admin_home" if user["role"] == "admin" else "pages.home")


# --- registration -----------------------------------------------------------
def _to_int(text):
    return int(text) if _DIGITS.fullmatch(text) else None


def _parse_genre_ids(raw_ids, valid_ids):
    """(ids, error): exactly three distinct, existing genre ids."""
    ids = [_to_int(raw) for raw in raw_ids]
    if None in ids:
        return [], "Select genres from the list."
    if len(set(ids)) != len(ids):
        return ids, "Do not select the same genre twice."
    if len(ids) != FAVOURITE_GENRE_COUNT:
        return ids, f"Select exactly {FAVOURITE_GENRE_COUNT} favourite genres."
    if not set(ids) <= set(valid_ids):
        return ids, "Select genres from the list."
    return ids, None


def validate_registration(form, valid_genre_ids):
    """Check the sign-up form. Returns (clean_values, errors); errors maps a
    field name to a message and is empty when the input is acceptable."""
    errors = {}
    username = (form.get("username") or "").strip()
    email = (form.get("email") or "").strip()
    password = form.get("password") or ""
    confirm = form.get("password_confirm") or ""

    if not username:
        errors["username"] = "Username is required."
    elif len(username) > USERNAME_MAX:
        errors["username"] = f"Username must be at most {USERNAME_MAX} characters."

    if not email:
        errors["email"] = "Email is required."
    elif len(email) > EMAIL_MAX:
        errors["email"] = f"Email must be at most {EMAIL_MAX} characters."
    elif not _EMAIL.fullmatch(email):
        errors["email"] = "Enter a valid email address."

    if not password:
        errors["password"] = "Password is required."
    elif password != confirm:
        errors["password_confirm"] = "Passwords do not match."

    genre_ids, genre_error = _parse_genre_ids(form.getlist("genre_ids"), valid_genre_ids)
    if genre_error:
        errors["genres"] = genre_error

    clean = {"username": username, "email": email, "password": password,
             "genre_ids": genre_ids}
    return clean, errors


def _database_errors(exc):
    """Translate a MySQL constraint error into a form error, else re-raise."""
    code, message = exc.args[0], str(exc.args[1]) if len(exc.args) > 1 else ""
    if code == ER_DUP_ENTRY and "users_username_uq" in message:
        return {"username": "This username is already taken."}
    if code == ER_DUP_ENTRY and "users_email_uq" in message:
        return {"email": "This email is already registered."}
    if code == ER_CHECK_CONSTRAINT_VIOLATED and "users_email_chk" in message:
        return {"email": "Enter a valid email address."}
    raise exc


def create_user(conn, values):
    """Insert the user and the three favourite genres in ONE transaction.
    Returns {} on success or a field->message dict for duplicates; any other
    failure rolls everything back and is re-raised."""
    try:
        with conn.cursor() as cur:
            cur.execute(INSERT_USER_SQL, {
                "username": values["username"],
                "email": values["email"],
                "password_hash": generate_password_hash(
                    values["password"], method=PASSWORD_HASH_METHOD),
            })
            user_id = cur.lastrowid
            cur.executemany(INSERT_USER_GENRE_SQL, [
                {"user_id": user_id, "genre_id": genre_id}
                for genre_id in values["genre_ids"]])
        conn.commit()
    except pymysql.MySQLError as exc:
        conn.rollback()
        return _database_errors(exc)
    except Exception:
        conn.rollback()
        raise
    return {}


@bp.route("/register", methods=["GET", "POST"])
def register():
    user = load_current_user()
    if user is not None:
        return redirect(home_for(user))

    conn = db.get_db()
    with conn.cursor() as cur:
        cur.execute(SELECT_GENRES_SQL)
        genres = cur.fetchall()

    form, errors, selected = {}, {}, set()
    if request.method == "POST":
        values, errors = validate_registration(request.form, [g_["genre_id"] for g_ in genres])
        form = {"username": values["username"], "email": values["email"]}
        selected = {i for i in values["genre_ids"]}
        if not errors:
            errors = create_user(conn, values)
        if not errors:
            flash("Account created. Please log in.", "success")
            return redirect(url_for("auth.login"))
    status = 400 if errors else 200
    return render_template("register.html", genres=genres, form=form,
                           errors=errors, selected=selected), status


# --- login / logout ---------------------------------------------------------
def _password_matches(password_hash, password):
    try:
        return check_password_hash(password_hash, password)
    except ValueError:  # placeholder hashes such as '!' (MovieLens users) never match
        return False


@bp.route("/login", methods=["GET", "POST"])
def login():
    user = load_current_user()
    if user is not None:
        return redirect(home_for(user))

    username = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        account = None
        if username:
            with db.get_db().cursor() as cur:
                cur.execute(SELECT_LOGIN_SQL, {"username": username})
                account = cur.fetchone()
        # Same message for an unknown user and a wrong password.
        if account and _password_matches(account["password_hash"], password):
            session.clear()
            session["user_id"] = account["user_id"]
            return redirect(home_for(account))
        return render_template("login.html", username=username,
                               error="Invalid username or password."), 401
    return render_template("login.html", username=username, error=None)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))
