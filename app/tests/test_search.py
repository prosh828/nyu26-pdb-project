"""Tests for title search: /search, /search/results and GET /api/search (read-only).

Run inside the app container:
    docker compose -f env/docker-compose.yml exec app python -m unittest discover -s tests -t . -v

Queries are built from titles found in the running DB, so the tests hold for the
sample data and for the full MovieLens import alike.
"""
import unittest

from recco import create_app, db, search


class MatchingTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(search.normalize("  Amélie   Poulain "), "amelie poulain")

    def test_required_overlap(self):
        self.assertEqual(search.required_overlap("ab"), 2)
        self.assertEqual(search.required_overlap("abc"), 2)
        self.assertEqual(search.required_overlap("matrix"), 4)
        self.assertEqual(search.required_overlap("toy story"), 6)

    def test_overlap_is_longest_shared_run(self):
        self.assertEqual(search.overlap("matrix", "the matrix"), 6)
        self.assertEqual(search.overlap("matrix", "the patriot"), 4)   # "atri"
        self.assertEqual(search.overlap("xyz", "the matrix"), 1)
        self.assertEqual(search.overlap("qq", "the matrix"), 0)


class SearchApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = create_app().test_client()
        cls.conn = db.connect()
        with cls.conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            # A well-rated title to search for, and a genre it belongs to.
            cur.execute("""
                SELECT m.movie_id, m.title, MIN(mg.genre_id) AS genre_id
                FROM movies m JOIN ratings r ON r.movie_id = m.movie_id
                JOIN movie_genres mg ON mg.movie_id = m.movie_id
                WHERE CHAR_LENGTH(m.title) BETWEEN 6 AND 30
                GROUP BY m.movie_id, m.title ORDER BY COUNT(*) DESC, m.movie_id LIMIT 1""")
            cls.movie = cur.fetchone()
        cls.conn.rollback()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def sql_all(self, sql, params=None):
        with self.conn.cursor() as cur:
            cur.execute(sql, params or {})
            rows = cur.fetchall()
        self.conn.rollback()
        return rows

    def api(self, **params):
        resp = self.client.get("/api/search", query_string=params)
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()

    def all_movies(self, body):
        return body["matches"] + body["fill"]

    def test_exact_title_ranks_first(self):
        body = self.api(q=self.movie["title"])
        self.assertEqual(body["matches"][0]["movie_id"], self.movie["movie_id"])

    def test_case_and_spacing_do_not_matter(self):
        messy = "  " + "  ".join(self.movie["title"].upper().split()) + " "
        self.assertEqual(self.api(q=messy)["matches"][0]["movie_id"], self.movie["movie_id"])

    def test_at_most_20_and_no_duplicates(self):
        for q in ("th", "an", self.movie["title"][:4], "zzqx"):
            movies = self.all_movies(self.api(q=q))
            self.assertLessEqual(len(movies), search.MAX_RESULTS, q)
            ids = [m["movie_id"] for m in movies]
            self.assertEqual(len(ids), len(set(ids)), q)

    def test_matches_sorted_by_overlap_and_meet_minimum(self):
        q = self.movie["title"][:5]
        body = self.api(q=q)
        need = search.required_overlap(search.normalize(q))
        overlaps = [m["overlap"] for m in body["matches"]]
        self.assertTrue(overlaps)
        self.assertEqual(overlaps, sorted(overlaps, reverse=True))
        self.assertGreaterEqual(min(overlaps), max(need, search.MIN_OVERLAP))
        for m in body["matches"]:
            self.assertEqual(search.overlap(search.normalize(q), search.normalize(m["title"])), m["overlap"])

    def test_short_query_returns_nothing(self):
        body = self.api(q="a")
        self.assertEqual(body["matches"], [])
        self.assertEqual(body["fill"], [])

    def test_fill_uses_genres_of_best_match_and_is_top_rated(self):
        body = self.api(q=self.movie["title"])
        if len(body["matches"]) >= search.MAX_RESULTS:
            self.skipTest("query matched 20 titles; nothing to fill")
        self.assertEqual(len(self.all_movies(body)) <= search.MAX_RESULTS, True)
        best = body["matches"][0]["movie_id"]
        best_genres = {r["name"] for r in self.sql_all(
            "SELECT g.name FROM movie_genres mg JOIN genres g USING (genre_id) WHERE mg.movie_id = %(id)s",
            {"id": best})}
        self.assertEqual(set(body["fill_genres"]), best_genres)
        for m in body["fill"]:
            names = {r["name"] for r in self.sql_all(
                "SELECT g.name FROM movie_genres mg JOIN genres g USING (genre_id) WHERE mg.movie_id = %(id)s",
                {"id": m["movie_id"]})}
            self.assertTrue(names & best_genres, m["title"])
            self.assertGreaterEqual(m["rating_count"], search.FILL_MIN_RATINGS)
        scores = [m["avg_score"] for m in body["fill"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_no_match_fills_with_top_rated(self):
        body = self.api(q="qxzqxzqxz")
        self.assertEqual(body["matches"], [])
        self.assertLessEqual(len(body["fill"]), search.MAX_RESULTS)
        self.assertEqual(body["fill_genres"], [])

    def test_genre_filter_applies_to_matches_and_fill(self):
        gid = self.movie["genre_id"]
        body = self.api(q=self.movie["title"], genre=gid)
        self.assertEqual(body["query"]["genre"], gid)
        for m in self.all_movies(body):
            rows = self.sql_all("SELECT 1 FROM movie_genres WHERE movie_id = %(m)s AND genre_id = %(g)s",
                                {"m": m["movie_id"], "g": gid})
            self.assertTrue(rows, m["title"])

    def test_min_rating_filter(self):
        body = self.api(q=self.movie["title"][:4], min_rating="4.0")
        self.assertEqual(body["query"]["min_rating"], 4.0)
        for m in self.all_movies(body):
            self.assertGreaterEqual(m["avg_score"], 4.0, m["title"])

    def test_bad_filter_values_are_ignored(self):
        body = self.api(q="ab", genre="999999", min_rating="7")
        self.assertEqual(body["query"], {"q": "ab", "genre": None, "min_rating": None})
        body = self.api(q="ab", genre="x; DROP TABLE movies", min_rating="abc")
        self.assertEqual(body["query"]["genre"], None)

    def test_like_wildcards_are_literal(self):
        for m in self.api(q="%%%%")["matches"]:
            self.assertIn("%%", m["title"])


class SearchPagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = create_app().test_client()

    def test_nav_search_tab_on_every_page(self):
        for path in ("/", "/login", "/register", "/search"):
            html = self.client.get(path).get_data(as_text=True)
            self.assertIn('id="nav-search-input"', html, path)
            self.assertIn(">Search</button>", html, path)

    def test_search_page_renders_results_and_filters(self):
        resp = self.client.get("/search?q=the")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('class="nav-search open"', html)
        self.assertIn('value="the"', html)
        self.assertIn('name="genre"', html)
        self.assertIn('name="min_rating"', html)
        self.assertIn('Results for &#34;the&#34;', html)

    def test_fragment_is_only_the_results(self):
        html = self.client.get("/search/results?q=the").get_data(as_text=True)
        self.assertTrue(html.lstrip().startswith('<div id="search-results">'))
        self.assertNotIn("<nav>", html)

    def test_query_is_escaped(self):
        html = self.client.get("/search?q=%3Cscript%3Ex").get_data(as_text=True)
        self.assertNotIn("<script>x", html)


if __name__ == "__main__":
    unittest.main()
