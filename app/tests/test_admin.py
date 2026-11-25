"""Tests for the admin area: sub-menu pages and the statistics (recco/admin.py).

Integration tests against the isolated `recco_test` database only (see
tests/support.py). Run (inside the app container):
    python -m unittest discover -s tests -t . -v
"""
import unittest
from datetime import datetime, timezone

from recco import admin
from tests import support
from tests.test_watch import WatchTestCase

NOW = datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)


class AdminTestCase(WatchTestCase):
    def setUp(self):
        super().setUp()           # movie 1: runtime 95, Comedy + Drama; movie 2: no runtime, no genre
        u = self.ids
        support.execute_checked(self.conn, """
            INSERT INTO ratings (user_id, movie_id, score, review, rated_at) VALUES
              (%(alice)s, 1, 4.0, 'good', '2025-01-01'), (%(admin)s, 1, 5.0, NULL, '2025-01-01'),
              (%(legacy)s, 1, 3.0, '',    '2025-01-01'), (%(alice)s, 2, 2.5, NULL, '2025-01-01')""", u)
        support.execute_checked(self.conn, """
            INSERT INTO view_events (user_id, movie_id, progress, viewed_at) VALUES
              (%(alice)s,  1, 30, '2026-03-01 10:00:00'),
              (%(alice)s,  1, 95, '2026-03-01 11:00:00'),
              (%(admin)s,  2, 50, '2026-03-05 09:00:00'),
              (%(legacy)s, 1, 40, '2026-01-01 09:00:00')""", u)
        self.conn.commit()

    def stats(self, window):
        with self.app.app_context():
            return admin.load_stats(window, now=NOW)


class StatsTest(AdminTestCase):
    def test_totals_are_all_time(self):
        t = self.stats("7")["totals"]
        self.assertEqual((t["users"], t["movies"], t["ratings"], t["reviews"]), (4, 2, 4, 1))
        self.assertEqual(t["avg_score"], 3.62)                     # (4 + 5 + 3 + 2.5) / 4 = 3.625
        self.assertEqual(t["review_share"], 25.0)                  # blank review text is not a review

    def test_viewing_numbers_follow_the_window(self):
        a = self.stats("7")["activity"]                            # since 2026-02-27 12:00
        self.assertEqual(a["active_users"], 2)                     # alice and admin watched; ratings are older
        self.assertEqual(a["plays"], 2)                            # alice's two events on one day = one play
        self.assertEqual((a["watched_pairs"], a["finished_pairs"], a["completion_rate"]), (2, 1, 50.0))
        self.assertEqual(a["avg_watch_minutes"], 70.1)             # (95% of 95 + 50% of 100 default) / 2
        a = self.stats("all")["activity"]
        self.assertEqual((a["active_users"], a["plays"], a["watched_pairs"], a["finished_pairs"]), (3, 3, 3, 1))

    def test_chart_series(self):
        s = self.stats("all")
        self.assertEqual([p["value"] for p in s["score_distribution"]], [0, 0, 0, 0, 1, 1, 0, 1, 0, 1])
        self.assertEqual({(g["label"], g["value"], g["count"]) for g in s["genre_averages"]},
                         {("Comedy", 4.0, 3), ("Drama", 4.0, 3)})
        self.assertEqual(s["ratings_by_year"], [{"label": "2025", "value": 4}])
        self.assertEqual(s["reviews_by_year"], [{"label": "2025", "value": 1}])
        self.assertEqual(s["active_users_by_year"], [{"label": "2025", "value": 3}, {"label": "2026", "value": 3}])
        self.assertEqual([p["value"] for p in s["progress_buckets"]], [0, 0, 0, 0, 1, 1, 0, 0, 0, 1])
        self.assertEqual([(p["movie_id"], p["value"]) for p in s["top_played"]], [(1, 2), (2, 1)])

    def test_plays_per_day_has_every_day_of_the_window(self):
        plays = self.stats("7")["plays"]
        self.assertEqual(plays["unit"], "day")
        self.assertEqual([p["label"] for p in plays["points"]][::7], ["2026-02-27", "2026-03-06"])
        self.assertEqual({p["label"]: p["value"] for p in plays["points"] if p["value"]},
                         {"2026-03-01": 1, "2026-03-05": 1})
        self.assertEqual(self.stats("365")["plays"]["unit"], "month")

    def test_empty_window(self):
        support.execute_checked(self.conn, "DELETE FROM view_events")
        self.conn.commit()
        a = self.stats("30")["activity"]
        self.assertEqual((a["plays"], a["watched_pairs"], a["completion_rate"], a["avg_watch_minutes"]), (0, 0, None, None))


class AdminPagesTest(AdminTestCase):
    PAGES = ("/admin", "/admin/stats", "/admin/catalog", "/admin/data", "/admin/recommendations")

    def test_only_admins(self):
        for path in self.PAGES + ("/api/admin/stats",):
            self.assertEqual(self.client.get(path).status_code, 302, path)       # to /login
        self.login()
        for path in self.PAGES + ("/api/admin/stats",):
            self.assertEqual(self.client.get(path).status_code, 403, path)

    def test_every_page_has_the_admin_menu(self):
        self.login("admin", "adminpass")
        for path in self.PAGES:
            html = self.client.get(path).get_data(as_text=True)
            self.assertIn('class="admin-nav"', html, path)
            self.assertIn('aria-current="page"', html, path)
            for _, label, _ in admin.SECTIONS:
                self.assertIn(f">{label}</a>", html, path)
        self.assertIn("Coming soon", self.client.get("/admin/catalog").get_data(as_text=True))

    def test_stats_page_and_api(self):
        self.login("admin", "adminpass")
        html = self.client.get("/admin/stats?days=nonsense").get_data(as_text=True)
        self.assertIn('aria-current="true">Last 30 days</a>', html)              # bad value -> default
        html = self.client.get("/admin/stats?days=all").get_data(as_text=True)  # fixtures are from March 2026
        for chart_id in ("score-dist", "ratings-year", "genre-avg", "active-year", "plays", "progress", "top-played"):
            self.assertIn(f'id="{chart_id}" data-kind=', html)
        self.assertIn("admin-charts.js", html)
        body = self.client.get("/api/admin/stats?days=all").get_json()
        self.assertEqual(body["window"]["key"], "all")
        self.assertEqual(body["totals"]["ratings"], 4)


if __name__ == "__main__":
    unittest.main()
