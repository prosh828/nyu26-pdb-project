"""Tests for GET /api/movies.

Run inside the app container (it has the MYSQL_* variables and reaches the db):
    docker compose -f env/docker-compose.yml exec app python -m unittest discover -s tests -t . -v

The integration tests only SELECT. Expected values come from direct SQL on a
separate read-only connection, so they hold for the sample data (20 movies) and
for the full MovieLens import alike.
"""
import math
import unittest

from recco import create_app, db
from recco.movies import MAX_PAGE_SIZE, MAX_QUERY_LENGTH, escape_like


class EscapeLikeTest(unittest.TestCase):
    def test_wildcards_and_escape_character_are_escaped(self):
        self.assertEqual(escape_like("100%"), "100!%")
        self.assertEqual(escape_like("a_b"), "a!_b")
        self.assertEqual(escape_like("wow!"), "wow!!")
        self.assertEqual(escape_like("!%_"), "!!!%!_")

    def test_plain_text_and_backslash_are_unchanged(self):
        self.assertEqual(escape_like("The Matrix"), "The Matrix")
        self.assertEqual(escape_like("a\\b"), "a\\b")


class MoviesApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = create_app().test_client()
        cls.conn = db.connect()
        with cls.conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    # --- helpers -----------------------------------------------------------
    def sql_all(self, sql, params=None):
        with self.conn.cursor() as cur:
            cur.execute(sql, params or {})
            rows = cur.fetchall()
        self.conn.rollback()  # end the read snapshot so later reads see current data
        return rows

    def sql_one(self, sql, params=None):
        return self.sql_all(sql, params)[0]

    def get(self, query="", status=200):
        resp = self.client.get("/api/movies" + query)
        self.assertEqual(resp.status_code, status, resp.get_data(as_text=True))
        self.assertTrue(resp.is_json)
        return resp.get_json()

    def assert_invalid(self, query, param):
        body = self.get(query, status=400)
        self.assertEqual(body["error"]["code"], "invalid_parameter")
        self.assertEqual(body["error"]["param"], param)
        self.assertTrue(body["error"]["message"])

    # --- listing -----------------------------------------------------------
    def test_default_listing_shape_and_total(self):
        body = self.get()
        total = self.sql_one("SELECT COUNT(*) AS n FROM movies")["n"]
        self.assertEqual(body["query"], {"q": ""})
        self.assertEqual(body["pagination"], {
            "page": 1, "page_size": 20, "total_items": total,
            "total_pages": math.ceil(total / 20)})
        self.assertEqual(len(body["items"]), min(20, total))
        for item in body["items"]:
            self.assertEqual(set(item), {"movie_id", "title", "release_year", "genres"})
            self.assertIsInstance(item["movie_id"], int)
            self.assertIsInstance(item["genres"], list)

    def test_order_is_title_then_movie_id(self):
        expected = [r["movie_id"] for r in self.sql_all(
            "SELECT movie_id FROM movies ORDER BY title, movie_id LIMIT 20")]
        self.assertEqual([i["movie_id"] for i in self.get()["items"]], expected)

    def test_genres_match_database_and_are_sorted_lists(self):
        movie = self.sql_one(
            "SELECT m.movie_id, m.title FROM movies m "
            "JOIN movie_genres mg ON mg.movie_id = m.movie_id "
            "GROUP BY m.movie_id, m.title HAVING COUNT(*) >= 2 "
            "ORDER BY m.movie_id LIMIT 1")
        expected = [r["name"] for r in self.sql_all(
            "SELECT g.name FROM movie_genres mg JOIN genres g ON g.genre_id = mg.genre_id "
            "WHERE mg.movie_id = %(id)s ORDER BY g.name", {"id": movie["movie_id"]})]
        got = self.find_item(movie)
        self.assertEqual(got["genres"], expected)
        self.assertGreaterEqual(len(got["genres"]), 2)

    def test_movie_without_genres_has_empty_list(self):
        rows = self.sql_all(
            "SELECT m.movie_id, m.title FROM movies m WHERE NOT EXISTS "
            "(SELECT 1 FROM movie_genres mg WHERE mg.movie_id = m.movie_id) LIMIT 1")
        if not rows:
            self.skipTest("no movie without genres in this database")
        self.assertEqual(self.find_item(rows[0])["genres"], [])

    def test_missing_release_year_is_null(self):
        rows = self.sql_all("SELECT movie_id, title FROM movies WHERE release_year IS NULL LIMIT 1")
        if not rows:
            self.skipTest("no movie without release_year in this database")
        self.assertIsNone(self.find_item(rows[0])["release_year"])

    def find_item(self, movie):
        """Look a movie up through the API by its exact title."""
        body = self.get("?page_size=%d&q=%s" % (MAX_PAGE_SIZE, self.url_quote(movie["title"])))
        matches = [i for i in body["items"] if i["movie_id"] == movie["movie_id"]]
        self.assertEqual(len(matches), 1, "movie not found through the API")
        return matches[0]

    @staticmethod
    def url_quote(text):
        from urllib.parse import quote
        return quote(text, safe="")

    # --- search ------------------------------------------------------------
    def test_search_is_case_insensitive_substring(self):
        lower = self.get("?q=matrix&page_size=100")
        upper = self.get("?q=MATRIX&page_size=100")
        self.assertGreaterEqual(lower["pagination"]["total_items"], 1)
        self.assertEqual(lower["pagination"]["total_items"], upper["pagination"]["total_items"])
        self.assertEqual(lower["items"], upper["items"])
        for item in lower["items"]:
            self.assertIn("matrix", item["title"].lower())
        self.assertEqual(lower["query"], {"q": "matrix"})

    def test_search_term_is_trimmed(self):
        self.assertEqual(self.get("?q=%20%20matrix%20")["query"], {"q": "matrix"})

    def test_empty_result(self):
        body = self.get("?q=zzzzqqqqxxxx")
        self.assertEqual(body["items"], [])
        self.assertEqual(body["pagination"]["total_items"], 0)
        self.assertEqual(body["pagination"]["total_pages"], 0)

    def test_wildcards_are_literal(self):
        for char, sql_char in (("%", "%"), ("_", "_"), ("!", "!")):
            with self.subTest(char=char):
                expected = self.sql_one(
                    "SELECT COUNT(*) AS n FROM movies WHERE INSTR(title, %(c)s) > 0",
                    {"c": sql_char})["n"]
                body = self.get("?q=" + self.url_quote(char) + "&page_size=100")
                self.assertEqual(body["pagination"]["total_items"], expected)
                for item in body["items"]:
                    self.assertIn(char, item["title"])

    def test_sql_injection_text_is_just_a_search_term(self):
        before = self.sql_one("SELECT COUNT(*) AS n FROM movies")["n"]
        body = self.get("?q=" + self.url_quote("'; DROP TABLE movies; --"))
        self.assertEqual(body["pagination"]["total_items"], 0)
        self.assertEqual(self.sql_one("SELECT COUNT(*) AS n FROM movies")["n"], before)

    # --- pagination --------------------------------------------------------
    def test_pages_are_consecutive_without_overlap(self):
        first = [i["movie_id"] for i in self.get("?page_size=15")["items"]]
        pages = []
        for page in (1, 2, 3):
            pages += [i["movie_id"] for i in self.get("?page_size=5&page=%d" % page)["items"]]
        self.assertEqual(pages, first)
        self.assertEqual(len(set(pages)), len(pages))

    def test_last_page_and_beyond(self):
        size = 7
        total = self.sql_one("SELECT COUNT(*) AS n FROM movies")["n"]
        last = math.ceil(total / size)
        body = self.get("?page_size=%d&page=%d" % (size, last))
        self.assertEqual(len(body["items"]), total - (last - 1) * size)
        self.assertEqual(body["pagination"]["total_pages"], last)

        beyond = self.get("?page_size=%d&page=%d" % (size, last + 1))
        self.assertEqual(beyond["items"], [])
        self.assertEqual(beyond["pagination"], {
            "page": last + 1, "page_size": size, "total_items": total, "total_pages": last})

    def test_max_page_is_accepted(self):
        body = self.get("?page=100000&page_size=100")
        self.assertEqual(body["items"], [])

    # --- validation (no database access needed) -----------------------------
    def test_invalid_page(self):
        for value in ("0", "-1", "abc", "1.5", "", "+1", "%201", "100001", "%C2%B2"):
            with self.subTest(page=value):
                self.assert_invalid("?page=" + value, "page")

    def test_invalid_page_size(self):
        for value in ("0", "101", "-5", "ten", "2.0", ""):
            with self.subTest(page_size=value):
                self.assert_invalid("?page_size=" + value, "page_size")

    def test_query_too_long(self):
        self.assert_invalid("?q=" + "a" * (MAX_QUERY_LENGTH + 1), "q")
        self.assertEqual(self.get("?q=" + "a" * MAX_QUERY_LENGTH)["items"], [])

    def test_repeated_parameters_are_rejected(self):
        self.assert_invalid("?page=1&page=2", "page")
        self.assert_invalid("?page_size=5&page_size=5", "page_size")
        self.assert_invalid("?q=a&q=b", "q")

    def test_unknown_parameters_are_ignored(self):
        self.assertEqual(self.get("?foo=bar")["pagination"]["page"], 1)


if __name__ == "__main__":
    unittest.main()
