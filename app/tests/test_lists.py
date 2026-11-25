"""Tests for the watchlist / hidden-movie API (recco/lists.py) and where the lists show up.

Integration tests against the isolated `recco_test` database only (see
tests/support.py). Run (inside the app container):
    python -m unittest discover -s tests -t . -v
"""
import unittest

from recco import search
from tests import support
from tests.test_watch import WatchTestCase


class ListsTestCase(WatchTestCase):
    def setUp(self):
        super().setUp()
        support.execute_checked(self.conn, """
            INSERT INTO movies (movie_id, title, release_year, poster_url) VALUES
              (3, 'Third Comedy', 2003, NULL), (4, 'Fourth Comedy', 2004, NULL)""")
        support.execute_checked(self.conn, """
            INSERT INTO movie_genres (movie_id, genre_id)
            SELECT m.movie_id, g.genre_id FROM (SELECT 3 AS movie_id UNION ALL SELECT 4) m
            JOIN genres g ON g.name = 'Comedy'""")
        # Every movie gets a rating from admin, so all of them are on the "Popular" row.
        support.execute_checked(self.conn, """
            INSERT INTO ratings (user_id, movie_id, score)
            SELECT %(u)s, movie_id, 4.0 FROM movies""", {"u": self.ids["admin"]})
        self.conn.commit()

    def state(self, movie_id=1, username="alice"):
        params = {"u": self.ids[username], "m": movie_id}
        return (bool(self.rows("SELECT 1 FROM watchlist WHERE user_id = %(u)s AND movie_id = %(m)s", params)),
                bool(self.rows("SELECT 1 FROM hidden_movies WHERE user_id = %(u)s AND movie_id = %(m)s", params)))

    def call(self, method, path, status=200):
        resp = self.client.open(path, method=method)
        self.assertEqual(resp.status_code, status, path)
        return resp.get_json()

    def collection_ids(self):
        body = self.client.get("/api/collections").get_json()
        return {m["movie_id"] for row in body["collections"] for m in row["movies"]}


class ListApiTest(ListsTestCase):
    def test_writes_need_login_and_an_existing_movie(self):
        for method, path in (("PUT", "/api/watchlist/1"), ("DELETE", "/api/watchlist/1"),
                             ("PUT", "/api/hidden/1"), ("DELETE", "/api/hidden/1"),
                             ("GET", "/api/watchlist"), ("GET", "/api/hidden")):
            self.assertEqual(self.call(method, path, 401)["error"]["code"], "login_required")
        self.login()
        self.assertEqual(self.call("PUT", "/api/watchlist/999", 404)["error"]["code"], "not_found")
        self.assertEqual(self.call("PUT", "/api/hidden/999", 404)["error"]["code"], "not_found")
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM watchlist")[0]["n"], 0)

    def test_add_and_remove_watchlist_is_idempotent(self):
        self.login()
        self.assertEqual(self.call("PUT", "/api/watchlist/1"),
                         {"movie_id": 1, "in_watchlist": True, "hidden": False})
        support.execute_checked(self.conn, "UPDATE watchlist SET added_at = '2026-01-01 00:00:00'")
        self.conn.commit()
        self.call("PUT", "/api/watchlist/1")                       # again: keeps the first added_at
        rows = self.rows("SELECT added_at FROM watchlist WHERE user_id = %(u)s", {"u": self.ids["alice"]})
        self.assertEqual([str(r["added_at"]) for r in rows], ["2026-01-01 00:00:00"])
        self.assertEqual(self.call("DELETE", "/api/watchlist/1")["in_watchlist"], False)
        self.assertEqual(self.call("DELETE", "/api/watchlist/1")["in_watchlist"], False)
        self.assertEqual(self.state(), (False, False))

    def test_watchlist_and_hidden_exclude_each_other(self):
        self.login()
        self.call("PUT", "/api/watchlist/1")
        self.assertEqual(self.call("PUT", "/api/hidden/1"),
                         {"movie_id": 1, "in_watchlist": False, "hidden": True})
        self.assertEqual(self.state(), (False, True))
        self.call("PUT", "/api/watchlist/1")                       # saving it again un-hides it
        self.assertEqual(self.state(), (True, False))
        self.call("PUT", "/api/hidden/1")
        self.assertEqual(self.call("DELETE", "/api/hidden/1")["hidden"], False)
        self.assertEqual(self.state(), (False, False))

    def test_lists_are_per_user_newest_first(self):
        self.login()
        for movie_id, when in ((1, "2026-01-01"), (3, "2026-01-03"), (2, "2026-01-02")):
            self.call("PUT", f"/api/watchlist/{movie_id}")
            support.execute_checked(self.conn, "UPDATE watchlist SET added_at = %(t)s WHERE movie_id = %(m)s",
                                    {"t": when, "m": movie_id})
            self.conn.commit()               # release the row lock before the app writes again
        self.call("PUT", "/api/hidden/4")
        self.assertEqual([m["movie_id"] for m in self.call("GET", "/api/watchlist")["items"]], [3, 2, 1])
        self.assertEqual([m["movie_id"] for m in self.call("GET", "/api/hidden")["items"]], [4])
        other = self.app.test_client()
        self.login("admin", "adminpass", client=other)
        self.assertEqual(other.get("/api/watchlist").get_json()["items"], [])
        other.delete("/api/watchlist/1")                           # only removes admin's own row
        self.assertEqual(self.state(1), (True, False))


class HiddenMoviesTest(ListsTestCase):
    def test_hidden_movie_leaves_the_landing_rows_for_that_user_only(self):
        self.login()
        self.assertIn(1, self.collection_ids())
        self.call("PUT", "/api/hidden/1")
        self.assertNotIn(1, self.collection_ids())
        self.assertNotIn('href="/movies/1"', self.client.get("/").get_data(as_text=True))
        self.assertIn(1, self.anonymous_ids())                          # other visitors still see it
        self.call("DELETE", "/api/hidden/1")
        self.assertIn(1, self.collection_ids())

    def anonymous_ids(self):
        body = self.app.test_client().get("/api/collections").get_json()
        return {m["movie_id"] for row in body["collections"] for m in row["movies"]}

    def test_search_keeps_title_matches_but_drops_hidden_fill(self):
        saved = search.FILL_MIN_RATINGS
        search.FILL_MIN_RATINGS = 1          # the test DB has one rating per movie
        try:
            self.login()
            body = self.client.get("/api/search?q=Test Movie").get_json()
            self.assertEqual([m["movie_id"] for m in body["matches"]], [1])
            self.assertEqual({m["movie_id"] for m in body["fill"]}, {3, 4})     # same genre (Comedy)
            self.call("PUT", "/api/hidden/1")
            self.call("PUT", "/api/hidden/3")
            body = self.client.get("/api/search?q=Test Movie").get_json()
            self.assertEqual([m["movie_id"] for m in body["matches"]], [1])     # asked for by title
            self.assertEqual({m["movie_id"] for m in body["fill"]}, {4})
        finally:
            search.FILL_MIN_RATINGS = saved


class ListPagesTest(ListsTestCase):
    def test_cards_have_add_and_hide_buttons_and_show_saved_state(self):
        html = self.client.get("/").get_data(as_text=True)          # signed out: buttons lead to login
        self.assertIn('data-action="watchlist" aria-pressed="false"', html)
        self.assertIn('data-action="hide"', html)
        self.login()
        self.call("PUT", "/api/watchlist/1")
        html = self.client.get("/").get_data(as_text=True)
        start = html.index('<div class="card" data-movie-id="1">')
        card = html[start:html.index('data-action="hide"', start)]
        self.assertIn('data-action="watchlist" aria-pressed="true"', card)
        self.assertLess(card.index("</a>"), card.index('class="card-actions"'))   # buttons are not inside the link

    def test_home_lists_watchlist_and_hidden_with_remove_buttons(self):
        self.login()
        html = self.client.get("/home").get_data(as_text=True)
        self.assertIn("Your watchlist is empty", html)
        self.assertIn("No hidden movies", html)
        self.call("PUT", "/api/watchlist/3")
        self.call("PUT", "/api/hidden/4")
        html = self.client.get("/home").get_data(as_text=True)
        watch_row = html[html.index('aria-labelledby="row-watchlist"'):html.index('aria-labelledby="row-hidden"')]
        hidden_row = html[html.index('aria-labelledby="row-hidden"'):]
        self.assertIn('data-movie-id="3"', watch_row)
        self.assertIn('data-action="unwatch"', watch_row)
        self.assertNotIn('data-movie-id="4"', watch_row)
        self.assertIn('data-movie-id="4"', hidden_row)
        self.assertIn('data-action="unhide"', hidden_row)
        self.assertIn('<p class="row-empty" hidden>', watch_row)

    def test_watch_page_buttons_reflect_the_saved_state(self):
        self.login()
        self.call("PUT", "/api/hidden/1")
        html = self.client.get("/movies/1").get_data(as_text=True)
        self.assertIn('id="hide-btn" data-action="hide"\n              aria-pressed="true"', html)
        self.assertIn('id="watchlist-btn" data-action="watchlist"\n              aria-pressed="false"', html)


if __name__ == "__main__":
    unittest.main()
