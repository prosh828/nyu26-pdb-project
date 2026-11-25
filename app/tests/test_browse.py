"""Tests for the landing page `/` and GET /api/collections (read-only).

Run inside the app container:
    docker compose -f env/docker-compose.yml exec app python -m unittest discover -s tests -t . -v
"""
import unittest
from unittest import mock

from recco import browse, create_app, db


class CollectionsApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = create_app().test_client()
        cls.conn = db.connect()
        with cls.conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def sql_one(self, sql, params=None):
        with self.conn.cursor() as cur:
            cur.execute(sql, params or {})
            row = cur.fetchone()
        self.conn.rollback()
        return row

    def collections(self):
        resp = self.client.get("/api/collections")
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()["collections"]

    def test_rows_follow_config_order_and_shape(self):
        rows = self.collections()
        order = [c["key"] for c in browse.COLLECTIONS]
        keys = [r["key"] for r in rows]
        self.assertEqual(keys, [k for k in order if k in keys])
        for row in rows:
            self.assertEqual(set(row), {"key", "title", "description", "movies"})
            self.assertTrue(row["movies"])
            self.assertLessEqual(len(row["movies"]), browse.MOVIES_PER_ROW)
            for m in row["movies"]:
                self.assertEqual(set(m), {"movie_id", "title", "release_year", "poster_url",
                                          "rating_count", "avg_score"})

    def test_row_rules_hold(self):
        specs = {c["key"]: c for c in browse.COLLECTIONS}
        for row in self.collections():
            spec = specs[row["key"]]
            movies = row["movies"]
            ids = [m["movie_id"] for m in movies]
            self.assertEqual(len(ids), len(set(ids)), row["key"])
            for m in movies:
                self.assertGreaterEqual(m["rating_count"], spec["min_ratings"])
                if spec.get("min_year"):
                    self.assertGreaterEqual(m["release_year"], spec["min_year"])
                if spec["genres"]:
                    hit = self.sql_one(
                        "SELECT COUNT(*) AS n FROM movie_genres mg JOIN genres g USING (genre_id)"
                        " WHERE mg.movie_id = %(id)s AND g.name IN %(g)s",
                        {"id": m["movie_id"], "g": tuple(spec["genres"])})
                    self.assertGreater(hit["n"], 0, (row["key"], m["title"]))
            key = "avg_score" if spec["sort"] == "top_rated" else "rating_count"
            values = [m[key] for m in movies]
            self.assertEqual(values, sorted(values, reverse=True), row["key"])

    def test_poster_url_matches_db(self):
        for row in self.collections():
            for m in row["movies"][:3]:
                db_row = self.sql_one("SELECT poster_url FROM movies WHERE movie_id = %(id)s",
                                      {"id": m["movie_id"]})
                self.assertEqual(m["poster_url"], db_row["poster_url"])

    def test_row_with_no_movies_is_hidden(self):
        fake = [{"key": "none", "title": "Nothing", "description": "x",
                 "genres": ["No Such Genre"], "min_ratings": 0, "sort": "popular"},
                browse.COLLECTIONS[0]]
        with mock.patch.object(browse, "COLLECTIONS", fake):
            keys = [r["key"] for r in self.collections()]
        self.assertNotIn("none", keys)


class LandingPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = create_app().test_client()

    def test_public_page_shows_rows_and_posters(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        rows = self.client.get("/api/collections").get_json()["collections"]
        for row in rows:
            self.assertIn(row["title"].replace("&", "&amp;"), html)
        with_poster = [m for r in rows for m in r["movies"] if m["poster_url"]]
        if with_poster:
            self.assertIn(f'src="{with_poster[0]["poster_url"]}"', html)
        self.assertIn("not endorsed or certified by TMDB", html)


if __name__ == "__main__":
    unittest.main()
