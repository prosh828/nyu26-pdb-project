"""Tests for the Continue Watching row on `/` and `/home` and GET /api/continue-watching.

Integration tests against the isolated `recco_test` database only (see
tests/support.py). Run (inside the app container):
    python -m unittest discover -s tests -t . -v
"""
import unittest

from recco import browse
from tests import support
from tests.test_watch import WatchTestCase


class ContinueWatchingTest(WatchTestCase):
    def setUp(self):
        super().setUp()
        support.execute_checked(self.conn, """
            INSERT INTO movies (movie_id, title, release_year, poster_url) VALUES
              (3, 'Third', 2003, NULL), (4, 'Fourth', 2004, NULL), (5, 'Fifth', 2005, NULL)""")
        self.conn.commit()

    def view(self, movie_id, progress, when, user="alice"):
        support.execute_checked(self.conn, """
            INSERT INTO view_events (user_id, movie_id, progress, viewed_at)
            VALUES (%(u)s, %(m)s, %(p)s, %(t)s)""",
            {"u": self.ids[user], "m": movie_id, "p": progress, "t": when})
        self.conn.commit()

    def items(self):
        resp = self.client.get("/api/continue-watching")
        self.assertEqual(resp.status_code, 200)
        return [(m["movie_id"], m["progress"]) for m in resp.get_json()["items"]]

    def test_latest_view_per_movie_newest_first_finished_excluded(self):
        self.view(1, 20, "2026-01-01 10:00:00")
        self.view(1, 60, "2026-01-05 10:00:00")     # latest for movie 1: 60
        self.view(2, 30, "2026-01-03 10:00:00")
        self.view(3, 50, "2026-01-02 10:00:00")
        self.view(3, 90, "2026-01-04 10:00:00")     # finished (>= 90): excluded
        self.view(4, 95, "2026-01-01 09:00:00")
        self.view(4, 10, "2026-01-06 10:00:00")     # started again after finishing: back in the list
        self.view(5, 40, "2026-01-07 10:00:00", user="admin")   # someone else's
        self.login()
        self.assertEqual(self.items(), [(4, 10), (1, 60), (2, 30)])

    def test_signed_out_and_empty(self):
        self.assertEqual(self.client.get("/api/continue-watching").status_code, 401)
        self.assertNotIn("row-continue", self.client.get("/").get_data(as_text=True))
        self.login()
        self.assertEqual(self.items(), [])
        self.assertNotIn("row-continue", self.client.get("/").get_data(as_text=True))
        self.assertIn("Nothing in progress", self.client.get("/home").get_data(as_text=True))

    def test_main_page_row_comes_first_with_progress_bar(self):
        self.view(1, 42, "2026-01-01 10:00:00")
        self.login()
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn(browse.CONTINUE_WATCHING_ROW["title"], html)
        self.assertIn(browse.CONTINUE_WATCHING_ROW["description"], html)
        first_row = html.index('<section class="row"')
        self.assertEqual(html.index('<section class="row" aria-labelledby="row-continue"'), first_row)
        self.assertIn('aria-valuenow="42"><span style="width: 42%"></span>', html)
        self.assertIn("42% watched", html)

    def test_home_page_shows_the_same_row(self):
        self.view(2, 15, "2026-01-01 10:00:00")
        self.view(1, 70, "2026-01-02 10:00:00")
        self.login()
        html = self.client.get("/home").get_data(as_text=True)
        self.assertIn('aria-labelledby="row-continue"', html)
        self.assertLess(html.index("70% watched"), html.index("15% watched"))
        self.assertIn('href="/movies/1"', html)

    def test_watching_on_the_player_updates_the_row(self):
        self.login()
        self.client.post("/api/movies/2/progress", json={"progress": 25})
        self.assertEqual(self.items(), [(2, 25)])
        self.client.post("/api/movies/2/progress", json={"progress": 92})
        self.assertEqual(self.items(), [])


if __name__ == "__main__":
    unittest.main()
