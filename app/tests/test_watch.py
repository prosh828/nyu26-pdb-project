"""Tests for the watch page /movies/<id> and the rating / review / progress API.

Unit tests need no database. The integration tests write, so they run the Flask
app against the isolated `recco_test` database only (see tests/support.py and
AGENTS.md for the one-time setup). Run (inside the app container):
    python -m unittest discover -s tests -t . -v
"""
import os
import unittest
from decimal import Decimal

from recco import create_app, db, watch
from tests import support


class ParseTest(unittest.TestCase):
    def test_score_half_steps_only(self):
        for good, expected in ((0.5, "0.5"), (5, "5.0"), ("3.5", "3.5"), (4.0, "4.0")):
            self.assertEqual(watch.parse_score(good), Decimal(expected))
        for bad in (0, 0.4, 5.5, 3.3, "abc", None, True, [], "nan", "inf", -1):
            with self.subTest(score=bad), self.assertRaises(watch.ApiError):
                watch.parse_score(bad)

    def test_review_is_trimmed_blank_is_null_and_limited(self):
        self.assertEqual(watch.parse_review("  great  "), "great")
        self.assertIsNone(watch.parse_review("   "))
        self.assertIsNone(watch.parse_review(None))
        self.assertEqual(len(watch.parse_review("x" * watch.REVIEW_MAX_LENGTH)), watch.REVIEW_MAX_LENGTH)
        for bad in ("x" * (watch.REVIEW_MAX_LENGTH + 1), 5, ["a"]):
            with self.assertRaises(watch.ApiError):
                watch.parse_review(bad)

    def test_progress_range(self):
        self.assertEqual(watch.parse_progress(0), 0)
        self.assertEqual(watch.parse_progress(99.7), 99)
        for bad in (-1, 101, "50", None, True, float("nan")):
            with self.assertRaises(watch.ApiError):
                watch.parse_progress(bad)


class WatchTestCase(unittest.TestCase):
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
        def only_recco_test():
            support.assert_test_database(db.get_db())

    @classmethod
    def tearDownClass(cls):
        cls._clear_movies()  # genres FK is RESTRICT: leave no movie_genres for other test classes
        if cls._saved_database is None:
            os.environ.pop("MYSQL_DATABASE", None)
        else:
            os.environ["MYSQL_DATABASE"] = cls._saved_database
        cls.conn.close()

    @classmethod
    def _clear_movies(cls):
        for table in ("view_events", "ratings", "movie_genres", "movies"):
            support.execute_checked(cls.conn, f"DELETE FROM {table}")
        cls.conn.commit()

    def setUp(self):
        self._clear_movies()
        self.ids = support.reset_data(self.conn, support.default_users())
        support.execute_checked(self.conn, """
            INSERT INTO movies (movie_id, title, release_year, runtime, tmdb_id, poster_url) VALUES
              (1, 'Test Movie', 2001, 95, 501, 'https://image.tmdb.org/t/p/w342/x.jpg'),
              (2, 'No Runtime', NULL, NULL, NULL, NULL)""")
        support.execute_checked(self.conn, """
            INSERT INTO movie_genres (movie_id, genre_id)
            SELECT 1, genre_id FROM genres WHERE name IN ('Comedy', 'Drama')""")
        self.conn.commit()
        self.client = self.app.test_client()

    def rows(self, sql, params=None):
        return support.fetch(self.conn, sql, params)

    def login(self, username="alice", password="alicepass", client=None):
        resp = (client or self.client).post("/login", data={"username": username, "password": password})
        self.assertEqual(resp.status_code, 302)

    def put(self, body, movie_id=1, client=None):
        return (client or self.client).put(f"/api/movies/{movie_id}/rating", json=body)

    def my_rating_row(self, username="alice", movie_id=1):
        rows = self.rows("SELECT score, review FROM ratings WHERE user_id = %(u)s AND movie_id = %(m)s",
                         {"u": self.ids[username], "m": movie_id})
        return rows[0] if rows else None


class WatchPageTest(WatchTestCase):
    def test_page_shows_player_details_and_login_prompt(self):
        resp = self.client.get("/movies/1")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        for needle in ('id="player"', 'data-duration="5700"', 'id="seek"', "Test Movie", "1h 35m",
                       "Comedy", "Drama", "themoviedb.org/movie/501", "Log in</a> to rate"):
            self.assertIn(needle, html)
        self.assertNotIn('id="rating-form"', html)

    def test_unknown_movie_is_404(self):
        self.assertEqual(self.client.get("/movies/999").status_code, 404)
        self.assertEqual(self.client.get("/api/movies/999").status_code, 404)

    def test_missing_runtime_uses_default_duration(self):
        html = self.client.get("/movies/2").get_data(as_text=True)
        self.assertIn(f'data-duration="{watch.DEFAULT_RUNTIME * 60}"', html)
        self.assertIn("Runtime unknown", html)

    def test_saved_rating_and_review_are_shown_again(self):
        self.login()
        self.assertEqual(self.put({"score": 4.5, "review": "Loved it <b>really</b>"}).status_code, 200)
        fresh = self.app.test_client()          # a later visit, new browser session
        self.login(client=fresh)
        html = fresh.get("/movies/1").get_data(as_text=True)
        self.assertIn('data-score="4.5"', html)
        self.assertIn("Loved it &lt;b&gt;really&lt;/b&gt;", html)   # escaped, in form and in list
        self.assertIn('class="review mine"', html)
        self.assertNotIn("<b>really</b>", html)

    def test_resume_from_last_progress_unless_finished(self):
        self.login()
        self.client.post("/api/movies/1/progress", json={"progress": 40})
        self.assertIn('data-resume="40"', self.client.get("/movies/1").get_data(as_text=True))
        self.client.post("/api/movies/1/progress", json={"progress": 95})
        self.assertIn('data-resume="0"', self.client.get("/movies/1").get_data(as_text=True))


class RatingApiTest(WatchTestCase):
    def test_writes_need_login(self):
        self.assertEqual(self.put({"score": 4}).status_code, 401)
        self.assertEqual(self.client.delete("/api/movies/1/rating").status_code, 401)
        self.assertEqual(self.client.post("/api/movies/1/progress", json={"progress": 1}).status_code, 401)
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM ratings")[0]["n"], 0)

    def test_create_update_and_delete(self):
        self.login()
        resp = self.put({"score": "3.5", "review": "  ok  "})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["my_rating"]["score"], 3.5)
        self.assertEqual(body["my_rating"]["review"], "ok")
        self.assertEqual(body["stats"], {"rating_count": 1, "avg_score": 3.5, "review_count": 1})
        self.assertEqual(self.my_rating_row(), {"score": Decimal("3.5"), "review": "ok"})

        self.put({"score": 5, "review": ""})                       # re-rate, clear the review
        self.assertEqual(self.my_rating_row(), {"score": Decimal("5.0"), "review": None})
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM ratings")[0]["n"], 1)

        resp = self.client.delete("/api/movies/1/rating")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.get_json()["my_rating"])
        self.assertIsNone(self.my_rating_row())

    def test_invalid_input_changes_nothing(self):
        self.login()
        for body in ({"score": 6}, {"score": 2.3}, {}, {"score": 4, "review": 7},
                     {"score": 4, "review": "x" * (watch.REVIEW_MAX_LENGTH + 1)}):
            with self.subTest(body=body):
                resp = self.put(body)
                self.assertEqual(resp.status_code, 400)
                self.assertEqual(resp.get_json()["error"]["code"], "invalid_parameter")
        self.assertIsNone(self.my_rating_row())

    def test_json_body_required(self):
        self.login()
        resp = self.client.put("/api/movies/1/rating", data={"score": "4"})   # an HTML form post
        self.assertEqual(resp.status_code, 415)
        self.assertIsNone(self.my_rating_row())

    def test_unknown_movie(self):
        self.login()
        self.assertEqual(self.put({"score": 4}, movie_id=999).status_code, 404)

    def test_users_only_change_their_own_rating(self):
        self.login()
        self.put({"score": 2, "review": "alice's"})
        other = self.app.test_client()
        self.login("admin", "adminpass", client=other)
        self.put({"score": 4, "review": "admin's", "user_id": self.ids["alice"]}, client=other)
        other.delete("/api/movies/1/rating")
        self.assertEqual(self.my_rating_row(), {"score": Decimal("2.0"), "review": "alice's"})
        self.assertIsNone(self.my_rating_row("admin"))

    def test_movie_api_includes_my_rating_when_signed_in(self):
        self.assertNotIn("my_rating", self.client.get("/api/movies/1").get_json())
        self.login()
        self.assertIsNone(self.client.get("/api/movies/1").get_json()["my_rating"])
        self.put({"score": 4})
        self.assertEqual(self.client.get("/api/movies/1").get_json()["my_rating"]["score"], 4.0)


class ReviewsApiTest(WatchTestCase):
    def test_lists_only_text_reviews_newest_first_with_paging(self):
        for i, name in enumerate(("alice", "admin", "legacy")):
            support.execute_checked(self.conn, """
                INSERT INTO ratings (user_id, movie_id, score, review, rated_at)
                VALUES (%(u)s, 1, 4.0, %(r)s, %(t)s)""",
                {"u": self.ids[name], "r": None if name == "legacy" else f"by {name}",
                 "t": f"2026-01-0{i + 1} 00:00:00"})
        self.conn.commit()
        body = self.client.get("/api/movies/1/reviews").get_json()
        self.assertEqual([r["username"] for r in body["items"]], ["admin", "alice"])
        self.assertEqual(body["stats"], {"rating_count": 3, "avg_score": 4.0, "review_count": 2})
        self.assertEqual(body["items"][0]["rated_at"], "2026-01-02T00:00:00Z")
        page2 = self.client.get("/api/movies/1/reviews?page=2&page_size=1").get_json()
        self.assertEqual([r["username"] for r in page2["items"]], ["alice"])
        self.assertEqual(page2["pagination"]["total_pages"], 2)
        for bad in ("page=0", "page_size=101", "page=x"):
            self.assertEqual(self.client.get(f"/api/movies/1/reviews?{bad}").status_code, 400)


class ProgressApiTest(WatchTestCase):
    def test_progress_is_appended(self):
        self.login()
        for p in (10, 55):
            self.assertEqual(self.client.post("/api/movies/1/progress", json={"progress": p}).status_code, 204)
        rows = self.rows("SELECT progress FROM view_events WHERE user_id = %(u)s ORDER BY event_id",
                         {"u": self.ids["alice"]})
        self.assertEqual([r["progress"] for r in rows], [10, 55])
        self.assertEqual(self.client.post("/api/movies/1/progress", json={"progress": 150}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
