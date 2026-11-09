-- =====================================================================
-- Recco — Part 2: hand-crafted sample data (MySQL 8.0)
-- Small on purpose: every corner case the queries must handle appears
-- at least once. All times are relative to NOW(), so results stay the
-- same whenever the script is run. Run after 01_schema.sql.
-- Demo passwords equal the username (hashed with werkzeug pbkdf2).
-- =====================================================================

USE recco;
SET time_zone = '+00:00';

START TRANSACTION;

-- ---------------------------------------------------------------------
-- Users: 1 admin, 5 regular users with history, 1 brand-new user
-- ---------------------------------------------------------------------
INSERT INTO users (user_id, username, email, password_hash, role) VALUES
 (1, 'admin', 'admin@recco.dev', 'pbkdf2:sha256:600000$GVDVkj2D$7a3645edf10e5d204e603b6b5b4e7b808d1c2b8e8f06fac9d7e50f05ee6ccf55', 'admin'),
 (2, 'alice', 'alice@nyu.edu',   'pbkdf2:sha256:600000$n24z4dOC$3b1176ca2d04f8f4d0d70354deb3e847759fda549178c7fd4efbe28c4f3cf38e', 'user'),
 (3, 'bob',   'bob@nyu.edu',     'pbkdf2:sha256:600000$DC54vZse$e65b895f33678753582ac9f13ea62f51243832b827616a926b49f9aec1f98be5', 'user'),
 (4, 'carol', 'carol@nyu.edu',   'pbkdf2:sha256:600000$mSKB0rUG$a43d6ba75bfbae6f47cef7ed037be6ba9eebf43eb97ec023420c6d8a43ff8b4a', 'user'),
 (5, 'david', 'david@nyu.edu',   'pbkdf2:sha256:600000$fL8bZJu9$1fb635e1a38616598f96880aa8b7292b82e25611dc0401d00ed3c7f2865a41ce', 'user'),
 (6, 'eve',   'eve@nyu.edu',     'pbkdf2:sha256:600000$o51JLUZa$258492d5d1edd64c9fa33c6fc915976b402fad033b32859f8ad81419bba1e983', 'user'),
 (7, 'frank', 'frank@nyu.edu',   'pbkdf2:sha256:600000$9fiHzkqg$a1ee399ac02761117ca3e1e846b528c5768c68b34a19861f82ad59097d26d78b', 'user');

-- ---------------------------------------------------------------------
-- Genres
-- ---------------------------------------------------------------------
INSERT INTO genres (genre_id, name) VALUES
 (1, 'Action'), (2, 'Animation'), (3, 'Comedy'),
 (4, 'Drama'),  (5, 'Romance'),   (6, 'Sci-Fi');

-- ---------------------------------------------------------------------
-- Movies (poster_url is filled from the TMDB API in Part 3)
-- ---------------------------------------------------------------------
INSERT INTO movies (movie_id, title, release_year, runtime, tmdb_id) VALUES
 ( 1, 'Toy Story',          1995,  81,    862),
 ( 2, 'Finding Nemo',       2003, 100,     12),
 ( 3, 'Shrek',              2001,  90,    808),
 ( 4, 'Up',                 2009,  96,  14160),
 ( 5, 'Spirited Away',      2001, 125,    129),
 ( 6, 'The Matrix',         1999, 136,    603),
 ( 7, 'Inception',          2010, 148,  27205),
 ( 8, 'Interstellar',       2014, 169, 157336),
 ( 9, 'The Dark Knight',    2008, 152,    155),
 (10, 'Mad Max: Fury Road', 2015, 120,  76341),
 (11, 'Jurassic Park',      1993, 127,    329),
 (12, 'Titanic',            1997, 194,    597),
 (13, 'The Notebook',       2004, 123,  11036),
 (14, 'La La Land',         2016, 128, 313369),
 (15, 'Forrest Gump',       1994, 142,     13),
 (16, 'The Godfather',      1972, 175,    238),
 (17, 'Pulp Fiction',       1994, 154,    680),
 (18, 'Parasite',           2019, 132, 496243),
 (19, 'Superbad',           2007, 113,   8363),
 (20, 'The Hangover',       2009, 100,  18785);

-- 1 Action, 2 Animation, 3 Comedy, 4 Drama, 5 Romance, 6 Sci-Fi
INSERT INTO movie_genres (movie_id, genre_id) VALUES
 ( 1,2),( 1,3),  ( 2,2),( 2,3),  ( 3,2),( 3,3),  ( 4,2),( 4,4),  ( 5,2),
 ( 6,1),( 6,6),  ( 7,1),( 7,6),  ( 8,6),( 8,4),  ( 9,1),( 9,4),
 (10,1),(10,6),  (11,1),(11,6),  (12,4),(12,5),  (13,4),(13,5),
 (14,3),(14,5),  (15,3),(15,4),(15,5),  (16,4),  (17,4),  (18,4),
 (19,3),  (20,3);

-- ---------------------------------------------------------------------
-- Favourite genres picked at sign-up (admin picked none)
-- ---------------------------------------------------------------------
INSERT INTO user_genres (user_id, genre_id) VALUES
 (2,1),(2,6),(2,4),        -- alice: Action, Sci-Fi, Drama
 (3,6),(3,4),(3,1),        -- bob:   Sci-Fi, Drama, Action
 (4,2),(4,3),(4,5),        -- carol: Animation, Comedy, Romance
 (5,4),(5,5),(5,2),        -- david: Drama, Romance, Animation
 (6,1),(6,4),(6,3),        -- eve:   Action, Drama, Comedy
 (7,2),(7,3),(7,5);        -- frank: Animation, Comedy, Romance (no history)

-- ---------------------------------------------------------------------
-- Ratings (half-star scale)
--   * carol gives The Matrix 3.5 — just below the 4.0 "liked" line.
--   * Parasite has a single 5.0 vote — must not top the charts.
-- ---------------------------------------------------------------------
INSERT INTO ratings (user_id, movie_id, score, review, rated_at) VALUES
 -- alice
 (2, 6, 5.0, 'Still the best.',          NOW() - INTERVAL 30 DAY),
 (2, 7, 4.5, NULL,                       NOW() - INTERVAL 28 DAY),
 (2, 9, 3.5, 'Good, a bit long.',        NOW() - INTERVAL 25 DAY),
 (2, 1, 2.0, NULL,                       NOW() - INTERVAL 20 DAY),
 -- bob
 (3, 6, 4.5, NULL, NOW() - INTERVAL 40 DAY),
 (3, 7, 4.5, NULL, NOW() - INTERVAL 39 DAY),
 (3, 8, 5.0, 'Loved the score.', NOW() - INTERVAL 38 DAY),
 (3,16, 5.0, NULL, NOW() - INTERVAL 37 DAY),
 (3,15, 4.0, NULL, NOW() - INTERVAL 36 DAY),
 (3,17, 4.0, NULL, NOW() - INTERVAL 35 DAY),
 (3,10, 4.0, NULL, NOW() - INTERVAL 34 DAY),
 (3,11, 3.5, NULL, NOW() - INTERVAL 33 DAY),
 -- carol
 (4, 6, 3.5, NULL, NOW() - INTERVAL 45 DAY),
 (4,11, 5.0, NULL, NOW() - INTERVAL 44 DAY),
 (4, 5, 5.0, 'A masterpiece.', NOW() - INTERVAL 43 DAY),
 (4, 1, 4.5, NULL, NOW() - INTERVAL 42 DAY),
 (4, 2, 4.0, NULL, NOW() - INTERVAL 41 DAY),
 (4, 3, 4.5, NULL, NOW() - INTERVAL 40 DAY),
 (4, 4, 5.0, NULL, NOW() - INTERVAL 39 DAY),
 (4,12, 4.0, NULL, NOW() - INTERVAL 38 DAY),
 (4,13, 3.0, NULL, NOW() - INTERVAL 37 DAY),
 (4,14, 4.0, NULL, NOW() - INTERVAL 36 DAY),
 (4,15, 4.5, NULL, NOW() - INTERVAL 35 DAY),
 (4,19, 3.5, NULL, NOW() - INTERVAL 34 DAY),
 (4,10, 3.0, NULL, NOW() - INTERVAL 33 DAY),
 -- david
 (5, 8, 4.0, NULL, NOW() - INTERVAL 50 DAY),
 (5,12, 4.5, NULL, NOW() - INTERVAL 49 DAY),
 (5,13, 5.0, NULL, NOW() - INTERVAL 48 DAY),
 (5,15, 4.5, NULL, NOW() - INTERVAL 47 DAY),
 (5,16, 4.5, NULL, NOW() - INTERVAL 46 DAY),
 (5,17, 3.5, NULL, NOW() - INTERVAL 45 DAY),
 (5,18, 5.0, 'Brilliant.', NOW() - INTERVAL 44 DAY),
 (5, 4, 4.0, NULL, NOW() - INTERVAL 43 DAY),
 (5, 5, 4.0, NULL, NOW() - INTERVAL 42 DAY),
 (5,14, 4.5, NULL, NOW() - INTERVAL 41 DAY),
 (5, 1, 4.0, NULL, NOW() - INTERVAL 40 DAY),
 -- eve
 (6, 6, 4.0, NULL, NOW() - INTERVAL 60 DAY),
 (6, 7, 4.0, NULL, NOW() - INTERVAL 59 DAY),
 (6, 8, 4.5, NULL, NOW() - INTERVAL 58 DAY),
 (6, 9, 4.0, NULL, NOW() - INTERVAL 57 DAY),
 (6,11, 4.0, NULL, NOW() - INTERVAL 56 DAY),
 (6,12, 3.5, NULL, NOW() - INTERVAL 55 DAY),
 (6,13, 4.0, NULL, NOW() - INTERVAL 54 DAY),
 (6,15, 5.0, NULL, NOW() - INTERVAL 53 DAY),
 (6,16, 4.5, NULL, NOW() - INTERVAL 52 DAY),
 (6,17, 4.5, NULL, NOW() - INTERVAL 51 DAY),
 (6, 4, 4.5, NULL, NOW() - INTERVAL 50 DAY),
 (6,10, 3.5, NULL, NOW() - INTERVAL 49 DAY),
 (6,20, 3.5, NULL, NOW() - INTERVAL 48 DAY),
 (6, 2, 4.5, NULL, NOW() - INTERVAL 47 DAY),
 (6, 3, 3.5, NULL, NOW() - INTERVAL 46 DAY),
 -- admin (administrators are users too)
 (1, 5, 4.5, NULL, NOW() - INTERVAL 70 DAY),
 (1,20, 4.0, NULL, NOW() - INTERVAL 69 DAY),
 (1,19, 4.0, NULL, NOW() - INTERVAL 68 DAY),
 (1, 3, 4.0, NULL, NOW() - INTERVAL 67 DAY),
 (1,14, 3.5, NULL, NOW() - INTERVAL 66 DAY);

-- ---------------------------------------------------------------------
-- Viewing log
--   * alice: Jurassic Park finished (95%), Shrek 20% -> 70%,
--     Superbad 35%, La La Land 50% -> 92% (finished on the latest view)
--   * The Godfather has two views older than 7 days and one inside.
--   * Parasite was only watched 20 days ago.
-- ---------------------------------------------------------------------
INSERT INTO view_events (user_id, movie_id, progress, viewed_at) VALUES
 (2,11,  95, NOW() - INTERVAL 5 DAY),
 (2, 3,  20, NOW() - INTERVAL 3 DAY),
 (2, 3,  70, NOW() - INTERVAL 2 DAY),
 (2,19,  35, NOW() - INTERVAL 1 DAY),
 (2,14,  50, NOW() - INTERVAL 8 DAY),
 (2,14,  92, NOW() - INTERVAL 6 HOUR),
 (3, 8, 100, NOW() - INTERVAL 2 DAY),
 (6, 8, 100, NOW() - INTERVAL 1 DAY),
 (5, 8, 100, NOW() - INTERVAL 3 DAY),
 (3,16, 100, NOW() - INTERVAL 10 DAY),
 (6,16, 100, NOW() - INTERVAL 9 DAY),
 (5,16, 100, NOW() - INTERVAL 2 DAY),
 (4,15, 100, NOW() - INTERVAL 4 DAY),
 (6,15, 100, NOW() - INTERVAL 6 DAY),
 (4, 4,  60, NOW() - INTERVAL 1 DAY),
 (3,11, 100, NOW() - INTERVAL 12 DAY),
 (5,12, 100, NOW() - INTERVAL 5 DAY),
 (4,12,  80, NOW() - INTERVAL 2 DAY),
 (5,18, 100, NOW() - INTERVAL 20 DAY);

-- ---------------------------------------------------------------------
-- Watchlist and "not interested"
-- ---------------------------------------------------------------------
INSERT INTO watchlist (user_id, movie_id, added_at) VALUES
 (2, 8, NOW() - INTERVAL 4 DAY),
 (2,12, NOW() - INTERVAL 4 DAY),
 (7, 4, NOW() - INTERVAL 1 HOUR);

INSERT INTO hidden_movies (user_id, movie_id, hidden_at) VALUES
 (2,10, NOW() - INTERVAL 2 DAY);          -- alice hides Mad Max: Fury Road

-- ---------------------------------------------------------------------
-- Earlier recommendation lists
--   A: alice, genre list, shown 2 days ago   (outside the 24-hour rule)
--   B: alice, "Because you liked The Matrix", shown 3 hours ago (inside)
--   C: bob, popular list, never shown
-- ---------------------------------------------------------------------
INSERT INTO recommendations
       (user_id, movie_id, strategy, seed_movie_id, rec_rank, score, generated_at, shown_at)
VALUES
 (2, 8, 'genre',   NULL, 1, 4.500, NOW() - INTERVAL 3 DAY, NOW() - INTERVAL 2 DAY),
 (2,17, 'genre',   NULL, 2, 4.000, NOW() - INTERVAL 3 DAY, NOW() - INTERVAL 2 DAY),
 (2,16, 'item_cf',    6, 1, 2.000, NOW() - INTERVAL 1 DAY, NOW() - INTERVAL 3 HOUR),
 (3,16, 'popular', NULL, 1, 3.000, NOW() - INTERVAL 1 DAY, NULL),
 (3, 8, 'popular', NULL, 2, 3.000, NOW() - INTERVAL 1 DAY, NULL);

COMMIT;

-- Quick check: rows per table
SELECT 'users' AS tbl, COUNT(*) AS n FROM users
UNION ALL SELECT 'genres',          COUNT(*) FROM genres
UNION ALL SELECT 'movies',          COUNT(*) FROM movies
UNION ALL SELECT 'movie_genres',    COUNT(*) FROM movie_genres
UNION ALL SELECT 'user_genres',     COUNT(*) FROM user_genres
UNION ALL SELECT 'ratings',         COUNT(*) FROM ratings
UNION ALL SELECT 'view_events',     COUNT(*) FROM view_events
UNION ALL SELECT 'watchlist',       COUNT(*) FROM watchlist
UNION ALL SELECT 'hidden_movies',   COUNT(*) FROM hidden_movies
UNION ALL SELECT 'recommendations', COUNT(*) FROM recommendations;
