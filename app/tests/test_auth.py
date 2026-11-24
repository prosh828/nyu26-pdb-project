"""Tests for registration, login/logout, sessions and role-based access.

Unit tests need no database. The integration tests run the Flask app against the
isolated `recco_test` database only (see tests/support.py). One-time setup of that
database is described in AGENTS.md. Run (inside the app container):
    python -m unittest discover -s tests -t . -v
"""
import os
import unittest
from unittest import mock

import pymysql
from werkzeug.datastructures import MultiDict
from werkzeug.security import check_password_hash, generate_password_hash

from recco import auth, create_app, db
from tests import support


# --- unit tests: no database ------------------------------------------------
class ValidateRegistrationTest(unittest.TestCase):
    VALID_IDS = [1, 2, 3, 4, 5]

    def form(self, **overrides):
        data = {"username": "newuser", "email": "new@example.com", "password": "pw",
                "password_confirm": "pw", "genre_ids": ["1", "2", "3"]}
        data.update(overrides)
        return MultiDict([(k, v) for k, val in data.items()
                          for v in (val if isinstance(val, list) else [val])])

    def check(self, **overrides):
        return auth.validate_registration(self.form(**overrides), self.VALID_IDS)

    def test_valid_input(self):
        clean, errors = self.check()
        self.assertEqual(errors, {})
        self.assertEqual(clean["genre_ids"], [1, 2, 3])

    def test_username_is_trimmed_and_limited(self):
        self.assertEqual(self.check(username="  bob  ")[0]["username"], "bob")
        self.assertIn("username", self.check(username="   ")[1])
        self.assertEqual(self.check(username="a" * 50)[1], {})
        self.assertIn("username", self.check(username="a" * 51)[1])

    def test_email_shape(self):
        for bad in ("", "plain", "a@b", "@b.c", "a@.c", "a@b."):
            with self.subTest(email=bad):
                self.assertIn("email", self.check(email=bad)[1])
        self.assertEqual(self.check(email="a@b.c")[1], {})

    def test_password_rules(self):
        self.assertIn("password", self.check(password="", password_confirm="")[1])
        self.assertIn("password_confirm", self.check(password_confirm="other")[1])
        self.assertEqual(self.check(password=" ", password_confirm=" ")[1], {})  # no length/strip policy

    def test_genre_rules(self):
        for ids in (["1", "2"], ["1", "2", "3", "4"], [], ["1", "1", "2"], ["1", "2", "99"],
                    ["1", "2", "x"], ["1", "2", "-3"], ["1", "2", "²"]):
            with self.subTest(ids=ids):
                self.assertIn("genres", self.check(genre_ids=ids)[1])


# --- integration tests: recco_test only -------------------------------------
class AuthTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = support.connect_test_db()
        support.assert_test_database(cls.conn)
        support.reset_schema(cls.conn)
        cls._saved_database = os.environ.get("MYSQL_DATABASE")
        os.environ["MYSQL_DATABASE"] = support.TEST_DB  # this test process only
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

        @cls.app.before_request
        def only_recco_test():  # every request must use the test database
            support.assert_test_database(db.get_db())

    @classmethod
    def tearDownClass(cls):
        if cls._saved_database is None:
            os.environ.pop("MYSQL_DATABASE", None)
        else:
            os.environ["MYSQL_DATABASE"] = cls._saved_database
        cls.conn.close()

    def setUp(self):
        self.ids = support.reset_data(self.conn, support.default_users())
        self.genre_ids = [r["genre_id"] for r in
                          support.fetch(self.conn, "SELECT genre_id FROM genres ORDER BY name")]
        self.client = self.app.test_client()

    # helpers
    def rows(self, sql, params=None):
        return support.fetch(self.conn, sql, params)

    def user_count(self):
        return self.rows("SELECT COUNT(*) AS n FROM users")[0]["n"]

    def register(self, **overrides):
        data = {"username": "newuser", "email": "new@example.com", "password": "secret pw",
                "password_confirm": "secret pw", "genre_ids": [str(i) for i in self.genre_ids[:3]]}
        data.update(overrides)
        return self.client.post("/register", data=data)

    def login(self, username, password, client=None):
        return (client or self.client).post("/login", data={"username": username, "password": password})

    def location(self, response):
        return response.headers["Location"]


class RegistrationTest(AuthTestCase):
    def test_success_creates_user_and_three_genres(self):
        before = self.user_count()
        response = self.register()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.location(response).endswith("/login"))
        self.assertEqual(self.user_count(), before + 1)
        user = self.rows("SELECT * FROM users WHERE username = 'newuser'")[0]
        self.assertEqual(user["role"], "user")
        genres = self.rows("SELECT genre_id FROM user_genres WHERE user_id = %(id)s ORDER BY genre_id",
                           {"id": user["user_id"]})
        self.assertEqual([g["genre_id"] for g in genres], sorted(self.genre_ids[:3]))

    def test_password_is_stored_as_pbkdf2_hash(self):
        self.register()
        stored = self.rows("SELECT password_hash FROM users WHERE username = 'newuser'")[0]["password_hash"]
        self.assertTrue(stored.startswith("pbkdf2:sha256:"))
        self.assertNotIn("secret pw", stored)
        self.assertTrue(check_password_hash(stored, "secret pw"))
        self.assertFalse(check_password_hash(stored, "wrong"))

    def test_success_shows_message_and_does_not_log_in(self):
        response = self.client.post("/register", data={
            "username": "newuser", "email": "new@example.com", "password": "x", "password_confirm": "x",
            "genre_ids": [str(i) for i in self.genre_ids[:3]]}, follow_redirects=True)
        self.assertIn(b"Account created", response.data)
        self.assertEqual(self.client.get("/home").status_code, 302)  # still logged out

    def test_role_cannot_be_chosen_by_the_visitor(self):
        self.register(role="admin")
        self.assertEqual(self.rows("SELECT role FROM users WHERE username = 'newuser'")[0]["role"], "user")

    def assert_rejected(self, response, field, message=None):
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'class="error"', response.data)
        if message:
            self.assertIn(message.encode(), response.data)
        return field

    def test_duplicate_username_and_email(self):
        before = self.user_count()
        self.assert_rejected(self.register(username="alice"), "username", "already taken")
        self.assert_rejected(self.register(username="ALICE"), "username", "already taken")  # case-insensitive
        self.assert_rejected(self.register(email="alice@recco.test"), "email", "already registered")
        self.assertEqual(self.user_count(), before)
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM user_genres")[0]["n"], 0)

    def test_invalid_input_is_rejected_without_db_changes(self):
        before = self.user_count()
        cases = [dict(username=""), dict(email="not-an-email"), dict(email=""), dict(password="", password_confirm=""),
                 dict(password_confirm="different"), dict(username="x" * 51)]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assert_rejected(self.register(**overrides), "field")
        self.assertEqual(self.user_count(), before)

    def test_wrong_number_or_duplicate_genres_are_rejected(self):
        before = self.user_count()
        ids = [str(i) for i in self.genre_ids]
        for chosen in (ids[:2], ids[:4], [], [ids[0], ids[0], ids[1]], ids[:2] + ["9999"], ids[:2] + ["abc"]):
            with self.subTest(genre_ids=chosen):
                self.assert_rejected(self.register(genre_ids=chosen), "genres")
        self.assertEqual(self.user_count(), before)

    def test_form_keeps_input_but_not_the_password(self):
        response = self.register(username="keepme", password_confirm="different")
        self.assertIn(b'value="keepme"', response.data)
        self.assertNotIn(b"secret pw", response.data)

    def test_failure_while_saving_genres_rolls_back_the_user(self):
        before = self.user_count()
        broken = "INSERT INTO user_genres (no_such_column) VALUES (%(user_id)s)"
        with mock.patch.object(auth, "INSERT_USER_GENRE_SQL", broken):
            with self.assertRaises(pymysql.MySQLError):
                self.register()
        self.assertEqual(self.user_count(), before)
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM users WHERE username = 'newuser'")[0]["n"], 0)

    def test_foreign_key_failure_rolls_back_the_user(self):
        # genre id passes validation but disappears before the INSERT (database enforces the FK)
        before = self.user_count()
        with mock.patch.object(auth, "validate_registration",
                               return_value=({"username": "ghost", "email": "g@example.com", "password": "x",
                                              "genre_ids": [self.genre_ids[0], self.genre_ids[1], 987654]}, {})):
            with self.assertRaises(pymysql.MySQLError):
                self.register(username="ghost")
        self.assertEqual(self.user_count(), before)

    def test_sql_injection_text_is_stored_literally(self):
        evil = "x'); DROP TABLE users; --"
        response = self.register(username=evil)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM users WHERE username = %(u)s", {"u": evil})[0]["n"], 1)
        self.assertGreaterEqual(self.user_count(), 5)  # table still exists

    def test_signed_in_user_is_redirected_away_from_register(self):
        self.login("alice", "alicepass")
        self.assertTrue(self.location(self.client.get("/register")).endswith("/home"))


class LoginSessionTest(AuthTestCase):
    def test_user_login_goes_to_home_and_session_persists(self):
        response = self.login("alice", "alicepass")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.location(response).endswith("/home"))
        for _ in range(2):  # later requests keep the session
            page = self.client.get("/home")
            self.assertEqual(page.status_code, 200)
            self.assertIn(b"alice", page.data)

    def test_admin_login_goes_to_admin_home(self):
        response = self.login("admin", "adminpass")
        self.assertTrue(self.location(response).endswith("/admin"))

    def test_session_stores_only_the_user_id(self):
        self.login("alice", "alicepass")
        with self.client.session_transaction() as sess:
            self.assertEqual(set(sess.keys()), {"user_id"})
            self.assertEqual(sess["user_id"], self.ids["alice"])

    def test_both_hash_formats_can_log_in(self):
        self.assertEqual(self.login("alice", "alicepass").status_code, 302)  # pbkdf2:sha256
        other = self.app.test_client()
        self.assertEqual(self.login("legacy", "legacypass", other).status_code, 302)  # Werkzeug default

    def test_failed_logins_look_the_same(self):
        responses = [self.login("alice", "wrong"), self.login("nobody", "alicepass"),
                     self.login("", ""), self.login("ml_user_1", "!"), self.login("ml_user_1", "")]
        for response in responses:
            self.assertEqual(response.status_code, 401)
            self.assertIn(b"Invalid username or password.", response.data)
        self.assertEqual(self.client.get("/home").status_code, 302)  # still not signed in

    def test_sql_injection_in_login_fails(self):
        for username in ("' OR '1'='1", "alice' -- ", "alice'; DROP TABLE users; --"):
            with self.subTest(username=username):
                self.assertEqual(self.login(username, "x").status_code, 401)
        self.assertEqual(self.user_count(), 4)

    def test_signed_in_user_is_redirected_away_from_login(self):
        self.login("alice", "alicepass")
        self.assertTrue(self.location(self.client.get("/login")).endswith("/home"))

    def test_logout_clears_the_session(self):
        self.login("alice", "alicepass")
        response = self.client.post("/logout")
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertNotIn("user_id", sess)
        after = self.client.get("/home")
        self.assertEqual(after.status_code, 302)
        self.assertTrue(self.location(after).endswith("/login"))

    def test_logout_requires_post(self):
        self.login("alice", "alicepass")
        self.assertEqual(self.client.get("/logout").status_code, 405)
        self.assertEqual(self.client.get("/home").status_code, 200)  # GET did not log out

    def test_deleted_user_loses_the_session(self):
        self.login("alice", "alicepass")
        support.execute_checked(self.conn, "DELETE FROM users WHERE username = 'alice'")
        self.conn.commit()
        self.assertEqual(self.client.get("/home").status_code, 302)

    def test_role_comes_from_the_database_on_every_request(self):
        self.login("alice", "alicepass")
        self.assertEqual(self.client.get("/admin").status_code, 403)
        support.execute_checked(self.conn, "UPDATE users SET role = 'admin' WHERE username = 'alice'")
        self.conn.commit()
        self.assertEqual(self.client.get("/admin").status_code, 200)


class AuthorizationTest(AuthTestCase):
    def test_anonymous_is_redirected_to_login(self):
        for path in ("/home", "/admin"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(self.location(response).endswith("/login"))

    def test_regular_user_can_open_home_but_not_admin(self):
        self.login("alice", "alicepass")
        self.assertEqual(self.client.get("/home").status_code, 200)
        denied = self.client.get("/admin")
        self.assertEqual(denied.status_code, 403)
        self.assertIn(b"403 Forbidden", denied.data)
        self.assertNotIn(b"Administrator home", denied.data)

    def test_admin_can_open_both_pages(self):
        self.login("admin", "adminpass")
        self.assertEqual(self.client.get("/home").status_code, 200)
        page = self.client.get("/admin")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Administrator home", page.data)

    def test_navigation_matches_role(self):
        self.login("alice", "alicepass")
        self.assertNotIn(b'href="/admin"', self.client.get("/home").data)
        other = self.app.test_client()
        self.login("admin", "adminpass", other)
        self.assertIn(b'href="/admin"', other.get("/home").data)

    def test_user_text_is_escaped_in_html(self):
        xss = "<script>alert(1)</script>"
        self.register(username=xss, email="xss@example.com")
        self.login(xss, "secret pw")
        page = self.client.get("/home")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"&lt;script&gt;alert(1)&lt;/script&gt;", page.data)
        self.assertNotIn(b"<script>alert(1)", page.data)
        form = self.app.test_client().post("/register", data={"username": xss, "email": "bad"})
        self.assertNotIn(b"<script>alert(1)", form.data)


class ExistingBehaviourTest(AuthTestCase):
    def test_public_routes_still_work(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["table_count"], 10)
        self.assertEqual(self.client.get("/login").status_code, 200)
        self.assertEqual(self.client.get("/register").status_code, 200)

    def test_ensure_admin_skips_when_an_admin_exists(self):
        with self.app.app_context():
            support.assert_test_database(db.get_db())
        result = self.app.test_cli_runner().invoke(args=["ensure-admin"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("admin already exists", result.output)

    def test_ensure_admin_creates_an_admin_that_can_log_in(self):
        support.execute_checked(self.conn, "DELETE FROM users WHERE role = 'admin'")
        self.conn.commit()
        with self.app.app_context():
            support.assert_test_database(db.get_db())
        result = self.app.test_cli_runner().invoke(args=["ensure-admin"])
        self.assertEqual(result.exit_code, 0, result.output)
        username = os.environ.get("ADMIN_USERNAME", "admin")
        password = os.environ.get("ADMIN_PASSWORD", "admin1234")
        response = self.login(username, password)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.location(response).endswith("/admin"))


if __name__ == "__main__":
    unittest.main()
