-- =====================================================================
-- Recco — Part 2, requirement 4: SQL queries and their results.
-- Run top to bottom on a fresh load of part2_create_tables.sql + part2_insert_data.sql.
-- Statements marked "EXPECTED ERROR" are meant to fail: they prove that
-- a constraint works. (In MySQL Workbench, turn on "Continue on SQL
-- Script Error" or run those lines one by one.)
-- =====================================================================

-- =====================================================================
-- RESULTS: every statement below that returns rows or changes rows is
-- followed by its output, as comments starting with '-- | ' or '-- => '.
-- Produced by running this file top to bottom on MySQL 8.0.46, right
-- after a fresh load of part2_create_tables.sql and part2_insert_data.sql.
-- Times in the data are relative to NOW(), so timestamps in the output
-- show when it was run; every other value is the same on any run.
-- =====================================================================

USE recco;
SET time_zone = '+00:00';

-- ==== Basic listings ====
-- Simple listing queries over the sample data (requirement 4, in place of
-- the spec's airline examples).

-- All movies in the system, with their genres
SELECT m.movie_id, m.title, m.release_year, m.runtime,
       GROUP_CONCAT(g.name ORDER BY g.name SEPARATOR ', ') AS genres
FROM   movies m
JOIN   movie_genres mg ON mg.movie_id = m.movie_id
JOIN   genres g        ON g.genre_id  = mg.genre_id
GROUP  BY m.movie_id, m.title, m.release_year, m.runtime
ORDER  BY m.movie_id;
-- | +----------+--------------------+--------------+---------+------------------------+
-- | | movie_id | title              | release_year | runtime | genres                 |
-- | +----------+--------------------+--------------+---------+------------------------+
-- | | 1        | Toy Story          | 1995         | 81      | Animation, Comedy      |
-- | | 2        | Finding Nemo       | 2003         | 100     | Animation, Comedy      |
-- | | 3        | Shrek              | 2001         | 90      | Animation, Comedy      |
-- | | 4        | Up                 | 2009         | 96      | Animation, Drama       |
-- | | 5        | Spirited Away      | 2001         | 125     | Animation              |
-- | | 6        | The Matrix         | 1999         | 136     | Action, Sci-Fi         |
-- | | 7        | Inception          | 2010         | 148     | Action, Sci-Fi         |
-- | | 8        | Interstellar       | 2014         | 169     | Drama, Sci-Fi          |
-- | | 9        | The Dark Knight    | 2008         | 152     | Action, Drama          |
-- | | 10       | Mad Max: Fury Road | 2015         | 120     | Action, Sci-Fi         |
-- | | 11       | Jurassic Park      | 1993         | 127     | Action, Sci-Fi         |
-- | | 12       | Titanic            | 1997         | 194     | Drama, Romance         |
-- | | 13       | The Notebook       | 2004         | 123     | Drama, Romance         |
-- | | 14       | La La Land         | 2016         | 128     | Comedy, Romance        |
-- | | 15       | Forrest Gump       | 1994         | 142     | Comedy, Drama, Romance |
-- | | 16       | The Godfather      | 1972         | 175     | Drama                  |
-- | | 17       | Pulp Fiction       | 1994         | 154     | Drama                  |
-- | | 18       | Parasite           | 2019         | 132     | Drama                  |
-- | | 19       | Superbad           | 2007         | 113     | Comedy                 |
-- | | 20       | The Hangover       | 2009         | 100     | Comedy                 |
-- | +----------+--------------------+--------------+---------+------------------------+
-- => 20 row(s)

-- Movies a user has hidden
SELECT u.username, m.title, h.hidden_at
FROM   hidden_movies h
JOIN   users  u ON u.user_id  = h.user_id
JOIN   movies m ON m.movie_id = h.movie_id
ORDER  BY u.username, m.title;
-- | +----------+--------------------+---------------------+
-- | | username | title              | hidden_at           |
-- | +----------+--------------------+---------------------+
-- | | alice    | Mad Max: Fury Road | 2026-11-06 03:39:01 |
-- | +----------+--------------------+---------------------+
-- => 1 row(s)

-- Users who rated at least one movie
SELECT DISTINCT u.username
FROM   users u
JOIN   ratings r ON r.user_id = u.user_id
ORDER  BY u.username;
-- | +----------+
-- | | username |
-- | +----------+
-- | | admin    |
-- | | alice    |
-- | | bob      |
-- | | carol    |
-- | | david    |
-- | | eve      |
-- | +----------+
-- => 6 row(s)

-- All movies in the Sci-Fi genre
SELECT m.title, m.release_year
FROM   movies m
JOIN   movie_genres mg ON mg.movie_id = m.movie_id
JOIN   genres g        ON g.genre_id  = mg.genre_id
WHERE  g.name = 'Sci-Fi'
ORDER  BY m.release_year;
-- | +--------------------+--------------+
-- | | title              | release_year |
-- | +--------------------+--------------+
-- | | Jurassic Park      | 1993         |
-- | | The Matrix         | 1999         |
-- | | Inception          | 2010         |
-- | | Interstellar       | 2014         |
-- | | Mad Max: Fury Road | 2015         |
-- | +--------------------+--------------+
-- => 5 row(s)

-- ==== Q1: Sign up a new user with three favourite genres =============
-- 1a: grace picks three valid genres
SET @username = 'grace', @email = 'grace@nyu.edu',
    @password_hash = 'pbkdf2:sha256:600000$6fZbG8PB$4ba9e3ad7b57b34122830f242525d071bdf35196a5750df8a8d0900e1e8223ad',
    @g1 = 'Comedy', @g2 = 'Romance', @g3 = 'Animation';
START TRANSACTION;
INSERT INTO users (username, email, password_hash, role)
SELECT @username, @email, @password_hash, 'user'
FROM   DUAL
WHERE  (SELECT COUNT(*) FROM genres WHERE name IN (@g1, @g2, @g3)) = 3;   -- exactly 3 distinct, existing genres
-- => Query OK, 1 row(s) affected

SET @new_user_id = IF(ROW_COUNT() = 1, LAST_INSERT_ID(), NULL);
INSERT INTO user_genres (user_id, genre_id)
SELECT @new_user_id, genre_id
FROM   genres
WHERE  @new_user_id IS NOT NULL
  AND  name IN (@g1, @g2, @g3);
-- => Query OK, 3 row(s) affected

COMMIT;

SELECT u.user_id, u.username, u.email, u.role,
       GROUP_CONCAT(g.name ORDER BY g.name SEPARATOR ', ') AS favourite_genres
FROM   users u
JOIN   user_genres ug ON ug.user_id = u.user_id
JOIN   genres g       ON g.genre_id = ug.genre_id
WHERE  u.user_id = @new_user_id
GROUP BY u.user_id, u.username, u.email, u.role;
-- | +---------+----------+---------------+------+----------------------------+
-- | | user_id | username | email         | role | favourite_genres           |
-- | +---------+----------+---------------+------+----------------------------+
-- | | 8       | grace    | grace@nyu.edu | user | Animation, Comedy, Romance |
-- | +---------+----------+---------------+------+----------------------------+
-- => 1 row(s)

-- 1b: heidi picks a genre that does not exist ('Western') -> no account at all
SET @username = 'heidi', @email = 'heidi@nyu.edu',
    @g1 = 'Comedy', @g2 = 'Drama', @g3 = 'Western';
START TRANSACTION;
INSERT INTO users (username, email, password_hash, role)
SELECT @username, @email, @password_hash, 'user'
FROM   DUAL
WHERE  (SELECT COUNT(*) FROM genres WHERE name IN (@g1, @g2, @g3)) = 3;   -- exactly 3 distinct, existing genres
-- => Query OK, 0 row(s) affected

SET @new_user_id = IF(ROW_COUNT() = 1, LAST_INSERT_ID(), NULL);
INSERT INTO user_genres (user_id, genre_id)
SELECT @new_user_id, genre_id
FROM   genres
WHERE  @new_user_id IS NOT NULL
  AND  name IN (@g1, @g2, @g3);
-- => Query OK, 0 row(s) affected

COMMIT;

SELECT (SELECT COUNT(*) FROM users WHERE username = 'heidi') AS heidi_users,
       (SELECT COUNT(*) FROM user_genres ug JOIN users u ON u.user_id = ug.user_id
        WHERE u.username = 'heidi')                          AS heidi_genres;
-- | +-------------+--------------+
-- | | heidi_users | heidi_genres |
-- | +-------------+--------------+
-- | | 0           | 0            |
-- | +-------------+--------------+
-- => 1 row(s)

-- EXPECTED ERROR: the same email again violates users_email_uq
INSERT INTO users (username, email, password_hash)
VALUES ('grace2', 'grace@nyu.edu', @password_hash);
-- => ERROR 1062: Duplicate entry 'grace@nyu.edu' for key 'users.users_email_uq'

-- ==== Q2: Rate, then re-rate, a movie (one statement, upsert) =========
-- bob rates The Dark Knight 3.0, then changes his mind to 4.5
SET @user_id = 3, @movie_id = 9, @score = 3.0, @review = NULL;
INSERT INTO ratings (user_id, movie_id, score, review)
VALUES (@user_id, @movie_id, @score, @review) AS new
ON DUPLICATE KEY UPDATE score    = new.score,
                        review   = new.review,
                        rated_at = CURRENT_TIMESTAMP;
-- => Query OK, 1 row(s) affected

SET @score = 4.5, @review = 'Better the second time.';
INSERT INTO ratings (user_id, movie_id, score, review)
VALUES (@user_id, @movie_id, @score, @review) AS new
ON DUPLICATE KEY UPDATE score    = new.score,
                        review   = new.review,
                        rated_at = CURRENT_TIMESTAMP;
-- => Query OK, 2 row(s) affected

SELECT user_id, movie_id, score, review
FROM   ratings
WHERE  user_id = @user_id AND movie_id = @movie_id;
-- | +---------+----------+-------+-------------------------+
-- | | user_id | movie_id | score | review                  |
-- | +---------+----------+-------+-------------------------+
-- | | 3       | 9        | 4.5   | Better the second time. |
-- | +---------+----------+-------+-------------------------+
-- => 1 row(s)

-- EXPECTED ERROR: 4.3 is not on the half-star scale (ratings_score_chk)
INSERT INTO ratings (user_id, movie_id, score) VALUES (3, 1, 4.3);
-- => ERROR 3819: Check constraint 'ratings_score_chk' is violated.

-- ==== Q3: Continue watching (alice) ===================================
SET @user_id = 2;
SELECT m.movie_id, m.title, lv.progress, lv.viewed_at AS last_viewed
FROM  (SELECT ve.movie_id, ve.progress, ve.viewed_at,
              ROW_NUMBER() OVER (PARTITION BY ve.movie_id
                                 ORDER BY ve.viewed_at DESC, ve.event_id DESC) AS rn
       FROM   view_events ve
       WHERE  ve.user_id = @user_id) AS lv
JOIN   movies m ON m.movie_id = lv.movie_id
WHERE  lv.rn = 1
  AND  lv.progress < 90
ORDER BY lv.viewed_at DESC;
-- | +----------+----------+----------+---------------------+
-- | | movie_id | title    | progress | last_viewed         |
-- | +----------+----------+----------+---------------------+
-- | | 19       | Superbad | 35       | 2026-11-07 03:39:01 |
-- | | 3        | Shrek    | 70       | 2026-11-06 03:39:01 |
-- | +----------+----------+----------+---------------------+
-- => 2 row(s)

-- ==== Q4: Trending this week ==========================================
SELECT m.movie_id, m.title,
       COUNT(DISTINCT ve.user_id) AS viewers,
       COUNT(*)                   AS views
FROM   view_events ve
JOIN   movies m ON m.movie_id = ve.movie_id
WHERE  ve.viewed_at >= NOW() - INTERVAL 7 DAY
GROUP BY m.movie_id, m.title
ORDER BY viewers DESC, views DESC, m.title
LIMIT 10;
-- | +----------+---------------+---------+-------+
-- | | movie_id | title         | viewers | views |
-- | +----------+---------------+---------+-------+
-- | | 8        | Interstellar  | 3       | 3     |
-- | | 15       | Forrest Gump  | 2       | 2     |
-- | | 12       | Titanic       | 2       | 2     |
-- | | 3        | Shrek         | 1       | 2     |
-- | | 11       | Jurassic Park | 1       | 1     |
-- | | 14       | La La Land    | 1       | 1     |
-- | | 19       | Superbad      | 1       | 1     |
-- | | 16       | The Godfather | 1       | 1     |
-- | | 4        | Up            | 1       | 1     |
-- | +----------+---------------+---------+-------+
-- => 9 row(s)

-- ==== Q5: Top-rated movies per genre (at least 3 ratings) =============
WITH movie_stats AS (
    SELECT movie_id, AVG(score) AS avg_score, COUNT(*) AS n_ratings
    FROM   ratings
    GROUP BY movie_id
    HAVING COUNT(*) >= 3
), ranked AS (
    SELECT g.name AS genre, m.title, ms.avg_score, ms.n_ratings,
           ROW_NUMBER() OVER (PARTITION BY g.genre_id
                              ORDER BY ms.avg_score DESC, ms.n_ratings DESC, m.title) AS pos
    FROM   movie_stats ms
    JOIN   movies m        ON m.movie_id  = ms.movie_id
    JOIN   movie_genres mg ON mg.movie_id = ms.movie_id
    JOIN   genres g        ON g.genre_id  = mg.genre_id
)
SELECT genre, pos, title, ROUND(avg_score, 2) AS avg_score, n_ratings
FROM   ranked
WHERE  pos <= 3
ORDER BY genre, pos;
-- | +-----------+-----+---------------+-----------+-----------+
-- | | genre     | pos | title         | avg_score | n_ratings |
-- | +-----------+-----+---------------+-----------+-----------+
-- | | Action    | 1   | Inception     | 4.33      | 3         |
-- | | Action    | 2   | The Matrix    | 4.25      | 4         |
-- | | Action    | 3   | Jurassic Park | 4.17      | 3         |
-- | | Animation | 1   | Spirited Away | 4.50      | 3         |
-- | | Animation | 2   | Up            | 4.50      | 3         |
-- | | Animation | 3   | Shrek         | 4.00      | 3         |
-- | | Comedy    | 1   | Forrest Gump  | 4.50      | 4         |
-- | | Comedy    | 2   | La La Land    | 4.00      | 3         |
-- | | Comedy    | 3   | Shrek         | 4.00      | 3         |
-- | | Drama     | 1   | The Godfather | 4.67      | 3         |
-- | | Drama     | 2   | Forrest Gump  | 4.50      | 4         |
-- | | Drama     | 3   | Interstellar  | 4.50      | 3         |
-- | | Romance   | 1   | Forrest Gump  | 4.50      | 4         |
-- | | Romance   | 2   | La La Land    | 4.00      | 3         |
-- | | Romance   | 3   | The Notebook  | 4.00      | 3         |
-- | | Sci-Fi    | 1   | Interstellar  | 4.50      | 3         |
-- | | Sci-Fi    | 2   | Inception     | 4.33      | 3         |
-- | | Sci-Fi    | 3   | The Matrix    | 4.25      | 4         |
-- | +-----------+-----+---------------+-----------+-----------+
-- => 18 row(s)

-- ==== Q6: Genre-based picks for a user ================================
-- 6a: alice (has history)
SET @user_id = 2;
WITH taste AS (            -- favourite genres + genres of movies rated 4.0 or higher
    SELECT ug.genre_id FROM user_genres ug WHERE ug.user_id = @user_id
    UNION
    SELECT mg.genre_id
    FROM   ratings r
    JOIN   movie_genres mg ON mg.movie_id = r.movie_id
    WHERE  r.user_id = @user_id AND r.score >= 4.0
), movie_stats AS (        -- same minimum of 3 ratings as Q5
    SELECT movie_id, AVG(score) AS avg_score, COUNT(*) AS n_ratings
    FROM   ratings
    GROUP BY movie_id
    HAVING COUNT(*) >= 3
)
SELECT m.movie_id, m.title, ROUND(s.avg_score, 2) AS avg_score, s.n_ratings
FROM   movies m
JOIN   movie_stats s ON s.movie_id = m.movie_id
WHERE  EXISTS (SELECT 1 FROM movie_genres mg
               JOIN   taste t ON t.genre_id = mg.genre_id
               WHERE  mg.movie_id = m.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM ratings r                       -- already rated
                   WHERE r.user_id = @user_id AND r.movie_id = m.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM view_events ve                  -- already finished
                   WHERE ve.user_id = @user_id AND ve.movie_id = m.movie_id
                     AND ve.progress >= 90)
  AND  NOT EXISTS (SELECT 1 FROM hidden_movies h                 -- hidden
                   WHERE h.user_id = @user_id AND h.movie_id = m.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM recommendations rc              -- shown in last 24 h
                   WHERE rc.user_id = @user_id AND rc.movie_id = m.movie_id
                     AND rc.strategy <> 'popular'       -- chart displays do not count
                     AND rc.shown_at >= NOW() - INTERVAL 1 DAY)
ORDER BY s.avg_score DESC, s.n_ratings DESC, m.title
LIMIT 10;
-- | +----------+--------------+-----------+-----------+
-- | | movie_id | title        | avg_score | n_ratings |
-- | +----------+--------------+-----------+-----------+
-- | | 15       | Forrest Gump | 4.50      | 4         |
-- | | 8        | Interstellar | 4.50      | 3         |
-- | | 4        | Up           | 4.50      | 3         |
-- | | 17       | Pulp Fiction | 4.00      | 3         |
-- | | 13       | The Notebook | 4.00      | 3         |
-- | | 12       | Titanic      | 4.00      | 3         |
-- | +----------+--------------+-----------+-----------+
-- => 6 row(s)

-- 6b: frank (brand-new user, favourite genres only)
SET @user_id = 7;
WITH taste AS (            -- favourite genres + genres of movies rated 4.0 or higher
    SELECT ug.genre_id FROM user_genres ug WHERE ug.user_id = @user_id
    UNION
    SELECT mg.genre_id
    FROM   ratings r
    JOIN   movie_genres mg ON mg.movie_id = r.movie_id
    WHERE  r.user_id = @user_id AND r.score >= 4.0
), movie_stats AS (        -- same minimum of 3 ratings as Q5
    SELECT movie_id, AVG(score) AS avg_score, COUNT(*) AS n_ratings
    FROM   ratings
    GROUP BY movie_id
    HAVING COUNT(*) >= 3
)
SELECT m.movie_id, m.title, ROUND(s.avg_score, 2) AS avg_score, s.n_ratings
FROM   movies m
JOIN   movie_stats s ON s.movie_id = m.movie_id
WHERE  EXISTS (SELECT 1 FROM movie_genres mg
               JOIN   taste t ON t.genre_id = mg.genre_id
               WHERE  mg.movie_id = m.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM ratings r                       -- already rated
                   WHERE r.user_id = @user_id AND r.movie_id = m.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM view_events ve                  -- already finished
                   WHERE ve.user_id = @user_id AND ve.movie_id = m.movie_id
                     AND ve.progress >= 90)
  AND  NOT EXISTS (SELECT 1 FROM hidden_movies h                 -- hidden
                   WHERE h.user_id = @user_id AND h.movie_id = m.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM recommendations rc              -- shown in last 24 h
                   WHERE rc.user_id = @user_id AND rc.movie_id = m.movie_id
                     AND rc.strategy <> 'popular'       -- chart displays do not count
                     AND rc.shown_at >= NOW() - INTERVAL 1 DAY)
ORDER BY s.avg_score DESC, s.n_ratings DESC, m.title
LIMIT 10;
-- | +----------+---------------+-----------+-----------+
-- | | movie_id | title         | avg_score | n_ratings |
-- | +----------+---------------+-----------+-----------+
-- | | 15       | Forrest Gump  | 4.50      | 4         |
-- | | 5        | Spirited Away | 4.50      | 3         |
-- | | 4        | Up            | 4.50      | 3         |
-- | | 14       | La La Land    | 4.00      | 3         |
-- | | 3        | Shrek         | 4.00      | 3         |
-- | | 13       | The Notebook  | 4.00      | 3         |
-- | | 12       | Titanic       | 4.00      | 3         |
-- | | 1        | Toy Story     | 3.50      | 3         |
-- | +----------+---------------+-----------+-----------+
-- => 8 row(s)

-- ==== Q7: "Because you liked X" — item-to-item (alice, X = The Matrix) =
SET @user_id = 2, @seed_movie_id = 6;
SELECT m.movie_id, m.title,
       COUNT(*)             AS co_raters,
       ROUND(AVG(r.score), 2) AS avg_co_score
FROM   ratings r
JOIN   movies  m ON m.movie_id = r.movie_id
WHERE  r.user_id IN (SELECT x.user_id FROM ratings x            -- people who liked X
                     WHERE x.movie_id = @seed_movie_id
                       AND x.score   >= 4.0
                       AND x.user_id <> @user_id)
  AND  r.score    >= 4.0                                        -- ... and also liked this
  AND  r.movie_id <> @seed_movie_id
  AND  NOT EXISTS (SELECT 1 FROM ratings r2
                   WHERE r2.user_id = @user_id AND r2.movie_id = m.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM view_events ve
                   WHERE ve.user_id = @user_id AND ve.movie_id = m.movie_id
                     AND ve.progress >= 90)
  AND  NOT EXISTS (SELECT 1 FROM hidden_movies h
                   WHERE h.user_id = @user_id AND h.movie_id = m.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM recommendations rc
                   WHERE rc.user_id = @user_id AND rc.movie_id = m.movie_id
                     AND rc.strategy <> 'popular'       -- chart displays do not count
                     AND rc.shown_at >= NOW() - INTERVAL 1 DAY)
GROUP BY m.movie_id, m.title
ORDER BY co_raters DESC, avg_co_score DESC, m.title
LIMIT 10;
-- | +----------+--------------+-----------+--------------+
-- | | movie_id | title        | co_raters | avg_co_score |
-- | +----------+--------------+-----------+--------------+
-- | | 8        | Interstellar | 2         | 4.75         |
-- | | 15       | Forrest Gump | 2         | 4.50         |
-- | | 17       | Pulp Fiction | 2         | 4.25         |
-- | | 2        | Finding Nemo | 1         | 4.50         |
-- | | 4        | Up           | 1         | 4.50         |
-- | | 13       | The Notebook | 1         | 4.00         |
-- | +----------+--------------+-----------+--------------+
-- => 6 row(s)

-- ==== Q8: Regenerate alice's three lists in one run ===================
-- One generated_at for the whole run; each strategy is its own list.
SET @user_id = 2, @gen_at = NOW();

-- 8a: genre-based list
INSERT INTO recommendations
       (user_id, movie_id, strategy, seed_movie_id, rec_rank, score, generated_at)
WITH taste AS (            -- favourite genres + genres of movies rated 4.0 or higher
    SELECT ug.genre_id FROM user_genres ug WHERE ug.user_id = @user_id
    UNION
    SELECT mg.genre_id
    FROM   ratings r
    JOIN   movie_genres mg ON mg.movie_id = r.movie_id
    WHERE  r.user_id = @user_id AND r.score >= 4.0
), movie_stats AS (        -- same minimum of 3 ratings as Q5
    SELECT movie_id, AVG(score) AS avg_score, COUNT(*) AS n_ratings
    FROM   ratings
    GROUP BY movie_id
    HAVING COUNT(*) >= 3
), candidates AS (
    SELECT m.movie_id, m.title, s.avg_score, s.n_ratings
    FROM   movies m
    JOIN   movie_stats s ON s.movie_id = m.movie_id
    WHERE  EXISTS (SELECT 1 FROM movie_genres mg
                   JOIN   taste t ON t.genre_id = mg.genre_id
                   WHERE  mg.movie_id = m.movie_id)
      AND  NOT EXISTS (SELECT 1 FROM ratings r                       -- already rated
                       WHERE r.user_id = @user_id AND r.movie_id = m.movie_id)
      AND  NOT EXISTS (SELECT 1 FROM view_events ve                  -- already finished
                       WHERE ve.user_id = @user_id AND ve.movie_id = m.movie_id
                         AND ve.progress >= 90)
      AND  NOT EXISTS (SELECT 1 FROM hidden_movies h                 -- hidden
                       WHERE h.user_id = @user_id AND h.movie_id = m.movie_id)
      AND  NOT EXISTS (SELECT 1 FROM recommendations rc              -- shown in last 24 h
                       WHERE rc.user_id = @user_id AND rc.movie_id = m.movie_id
                         AND rc.strategy <> 'popular'       -- chart displays do not count
                         AND rc.shown_at >= NOW() - INTERVAL 1 DAY)
    ORDER BY s.avg_score DESC, s.n_ratings DESC, m.title
    LIMIT 10
)
SELECT @user_id, c.movie_id, 'genre', NULL,
       ROW_NUMBER() OVER (ORDER BY c.avg_score DESC, c.n_ratings DESC, c.title),
       ROUND(c.avg_score, 3), @gen_at
FROM   candidates c;
-- => Query OK, 6 row(s) affected

-- EXPECTED ERROR: a second rank 1 in the same list (rec_list_rank_uq).
-- seed_movie_id is NULL here; the seed_key column is what makes this fail.
INSERT INTO recommendations
       (user_id, movie_id, strategy, seed_movie_id, rec_rank, score, generated_at)
VALUES (@user_id, 20, 'genre', NULL, 1, 1.000, @gen_at);
-- => ERROR 1062: Duplicate entry '2-genre-0-2026-11-08 03:39:01-1' for key 'recommendations.rec_list_rank_uq'

-- 8b: popular list
INSERT INTO recommendations
       (user_id, movie_id, strategy, seed_movie_id, rec_rank, score, generated_at)
WITH trending AS (         -- Q4: distinct viewers in the last 7 days
    SELECT ve.movie_id, COUNT(DISTINCT ve.user_id) AS viewers, COUNT(*) AS views
    FROM   view_events ve
    WHERE  ve.viewed_at >= NOW() - INTERVAL 7 DAY
    GROUP BY ve.movie_id
), candidates AS (         -- a chart: no 24-hour rule, but skip what the user has seen
    SELECT t.movie_id, m.title, t.viewers, t.views
    FROM   trending t
    JOIN   movies m ON m.movie_id = t.movie_id
    WHERE  TRUE
      AND  NOT EXISTS (SELECT 1 FROM ratings r
                       WHERE r.user_id = @user_id AND r.movie_id = m.movie_id)
      AND  NOT EXISTS (SELECT 1 FROM view_events ve
                       WHERE ve.user_id = @user_id AND ve.movie_id = m.movie_id
                         AND ve.progress >= 90)
      AND  NOT EXISTS (SELECT 1 FROM hidden_movies h
                       WHERE h.user_id = @user_id AND h.movie_id = m.movie_id)
    ORDER BY t.viewers DESC, t.views DESC, m.title
    LIMIT 10
)
SELECT @user_id, c.movie_id, 'popular', NULL,
       ROW_NUMBER() OVER (ORDER BY c.viewers DESC, c.views DESC, c.title),
       c.viewers, @gen_at
FROM   candidates c;
-- => Query OK, 7 row(s) affected

-- 8c: "Because you liked The Matrix" list (seed_movie_id is set)
SET @seed_movie_id = 6;
INSERT INTO recommendations
       (user_id, movie_id, strategy, seed_movie_id, rec_rank, score, generated_at)
WITH candidates AS (       -- Q7 for the seed movie
    SELECT m.movie_id, m.title,
           COUNT(*)     AS co_raters,
           AVG(r.score) AS avg_co_score
    FROM   ratings r
    JOIN   movies  m ON m.movie_id = r.movie_id
    WHERE  r.user_id IN (SELECT x.user_id FROM ratings x
                         WHERE x.movie_id = @seed_movie_id
                           AND x.score   >= 4.0
                           AND x.user_id <> @user_id)
      AND  r.score    >= 4.0
      AND  r.movie_id <> @seed_movie_id
      AND  NOT EXISTS (SELECT 1 FROM ratings r
                       WHERE r.user_id = @user_id AND r.movie_id = m.movie_id)
      AND  NOT EXISTS (SELECT 1 FROM view_events ve
                       WHERE ve.user_id = @user_id AND ve.movie_id = m.movie_id
                         AND ve.progress >= 90)
      AND  NOT EXISTS (SELECT 1 FROM hidden_movies h
                       WHERE h.user_id = @user_id AND h.movie_id = m.movie_id)
      AND  NOT EXISTS (SELECT 1 FROM recommendations rc
                       WHERE rc.user_id = @user_id AND rc.movie_id = m.movie_id
                         AND rc.strategy <> 'popular'       -- chart displays do not count
                         AND rc.shown_at >= NOW() - INTERVAL 1 DAY)
    GROUP BY m.movie_id, m.title
    ORDER BY co_raters DESC, avg_co_score DESC, m.title
    LIMIT 10
)
SELECT @user_id, c.movie_id, 'item_cf', @seed_movie_id,
       ROW_NUMBER() OVER (ORDER BY c.co_raters DESC, c.avg_co_score DESC, c.title),
       c.co_raters, @gen_at
FROM   candidates c;
-- => Query OK, 6 row(s) affected

-- 8d: the three stored lists
SELECT r.strategy, r.seed_movie_id, r.rec_rank, m.title, r.score
FROM   recommendations r
JOIN   movies m ON m.movie_id = r.movie_id
WHERE  r.user_id = @user_id AND r.generated_at = @gen_at
ORDER BY r.strategy, r.rec_rank;
-- | +----------+---------------+----------+---------------+-------+
-- | | strategy | seed_movie_id | rec_rank | title         | score |
-- | +----------+---------------+----------+---------------+-------+
-- | | genre    | NULL          | 1        | Forrest Gump  | 4.500 |
-- | | genre    | NULL          | 2        | Interstellar  | 4.500 |
-- | | genre    | NULL          | 3        | Up            | 4.500 |
-- | | genre    | NULL          | 4        | Pulp Fiction  | 4.000 |
-- | | genre    | NULL          | 5        | The Notebook  | 4.000 |
-- | | genre    | NULL          | 6        | Titanic       | 4.000 |
-- | | item_cf  | 6             | 1        | Interstellar  | 2.000 |
-- | | item_cf  | 6             | 2        | Forrest Gump  | 2.000 |
-- | | item_cf  | 6             | 3        | Pulp Fiction  | 2.000 |
-- | | item_cf  | 6             | 4        | Finding Nemo  | 1.000 |
-- | | item_cf  | 6             | 5        | Up            | 1.000 |
-- | | item_cf  | 6             | 6        | The Notebook  | 1.000 |
-- | | popular  | NULL          | 1        | Interstellar  | 3.000 |
-- | | popular  | NULL          | 2        | Forrest Gump  | 2.000 |
-- | | popular  | NULL          | 3        | Titanic       | 2.000 |
-- | | popular  | NULL          | 4        | Shrek         | 1.000 |
-- | | popular  | NULL          | 5        | Superbad      | 1.000 |
-- | | popular  | NULL          | 6        | The Godfather | 1.000 |
-- | | popular  | NULL          | 7        | Up            | 1.000 |
-- | +----------+---------------+----------+---------------+-------+
-- => 19 row(s)

-- ==== Q9: Serve the latest list and mark it as shown ==================
-- The application stamps exactly the rows the page displayed (by rec_id).
-- Here a temporary table "page" stands in for that list of rec_ids.

-- After the lists were generated, alice hides Interstellar.
INSERT INTO hidden_movies (user_id, movie_id) VALUES (2, 8);
-- => Query OK, 1 row(s) affected

SET @user_id = 2, @strategy = 'genre', @seed_movie_id = NULL;
-- 9a: show the genre list
DROP TEMPORARY TABLE IF EXISTS page;
CREATE TEMPORARY TABLE page AS
SELECT r.rec_id, r.rec_rank, m.movie_id, m.title, r.score
FROM   recommendations r
JOIN   movies m ON m.movie_id = r.movie_id
JOIN  (SELECT MAX(generated_at) AS generated_at
       FROM   recommendations
       WHERE  user_id = @user_id AND strategy = @strategy
         AND  seed_key = COALESCE(@seed_movie_id, 0)) AS latest
       ON latest.generated_at = r.generated_at
WHERE  r.user_id  = @user_id
  AND  r.strategy = @strategy
  AND  r.seed_key = COALESCE(@seed_movie_id, 0)
  AND  NOT EXISTS (SELECT 1 FROM ratings x                       -- rated since generation
                   WHERE x.user_id = r.user_id AND x.movie_id = r.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM hidden_movies h                 -- hidden since generation
                   WHERE h.user_id = r.user_id AND h.movie_id = r.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM view_events ve                  -- finished since generation
                   WHERE ve.user_id = r.user_id AND ve.movie_id = r.movie_id
                     AND ve.progress >= 90)
  AND  (r.strategy = 'popular'                                   -- charts are exempt
        OR NOT EXISTS (SELECT 1 FROM recommendations o           -- shown in ANOTHER personal list
                       WHERE o.user_id = r.user_id AND o.movie_id = r.movie_id
                         AND o.rec_id <> r.rec_id                -- own row does not count, so a
                         AND o.strategy <> 'popular'             -- refresh shows the same list
                         AND o.shown_at >= NOW() - INTERVAL 1 DAY))
ORDER BY r.rec_rank;
SELECT rec_rank, movie_id, title, score FROM page ORDER BY rec_rank;
-- | +----------+----------+--------------+-------+
-- | | rec_rank | movie_id | title        | score |
-- | +----------+----------+--------------+-------+
-- | | 1        | 15       | Forrest Gump | 4.500 |
-- | | 3        | 4        | Up           | 4.500 |
-- | | 4        | 17       | Pulp Fiction | 4.000 |
-- | | 5        | 13       | The Notebook | 4.000 |
-- | | 6        | 12       | Titanic      | 4.000 |
-- | +----------+----------+--------------+-------+
-- => 5 row(s)

-- 9b: stamp the displayed rows with shown_at
UPDATE recommendations r
JOIN   page p ON p.rec_id = r.rec_id
SET    r.shown_at = NOW()
WHERE  r.shown_at IS NULL;               -- keep the first time it was shown
-- => Query OK, 5 row(s) affected

-- 9c: refresh the page: the same list comes back
DROP TEMPORARY TABLE IF EXISTS page;
CREATE TEMPORARY TABLE page AS
SELECT r.rec_id, r.rec_rank, m.movie_id, m.title, r.score
FROM   recommendations r
JOIN   movies m ON m.movie_id = r.movie_id
JOIN  (SELECT MAX(generated_at) AS generated_at
       FROM   recommendations
       WHERE  user_id = @user_id AND strategy = @strategy
         AND  seed_key = COALESCE(@seed_movie_id, 0)) AS latest
       ON latest.generated_at = r.generated_at
WHERE  r.user_id  = @user_id
  AND  r.strategy = @strategy
  AND  r.seed_key = COALESCE(@seed_movie_id, 0)
  AND  NOT EXISTS (SELECT 1 FROM ratings x                       -- rated since generation
                   WHERE x.user_id = r.user_id AND x.movie_id = r.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM hidden_movies h                 -- hidden since generation
                   WHERE h.user_id = r.user_id AND h.movie_id = r.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM view_events ve                  -- finished since generation
                   WHERE ve.user_id = r.user_id AND ve.movie_id = r.movie_id
                     AND ve.progress >= 90)
  AND  (r.strategy = 'popular'                                   -- charts are exempt
        OR NOT EXISTS (SELECT 1 FROM recommendations o           -- shown in ANOTHER personal list
                       WHERE o.user_id = r.user_id AND o.movie_id = r.movie_id
                         AND o.rec_id <> r.rec_id                -- own row does not count, so a
                         AND o.strategy <> 'popular'             -- refresh shows the same list
                         AND o.shown_at >= NOW() - INTERVAL 1 DAY))
ORDER BY r.rec_rank;
SELECT rec_rank, movie_id, title, score FROM page ORDER BY rec_rank;
-- | +----------+----------+--------------+-------+
-- | | rec_rank | movie_id | title        | score |
-- | +----------+----------+--------------+-------+
-- | | 1        | 15       | Forrest Gump | 4.500 |
-- | | 3        | 4        | Up           | 4.500 |
-- | | 4        | 17       | Pulp Fiction | 4.000 |
-- | | 5        | 13       | The Notebook | 4.000 |
-- | | 6        | 12       | Titanic      | 4.000 |
-- | +----------+----------+--------------+-------+
-- => 5 row(s)

-- 9d: stamping again changes nothing: shown_at keeps the first display time
UPDATE recommendations r
JOIN   page p ON p.rec_id = r.rec_id
SET    r.shown_at = NOW()
WHERE  r.shown_at IS NULL;               -- keep the first time it was shown
-- => Query OK, 0 row(s) affected

SET @strategy = 'item_cf', @seed_movie_id = 6;
-- 9e: show the "Because you liked The Matrix" list
DROP TEMPORARY TABLE IF EXISTS page;
CREATE TEMPORARY TABLE page AS
SELECT r.rec_id, r.rec_rank, m.movie_id, m.title, r.score
FROM   recommendations r
JOIN   movies m ON m.movie_id = r.movie_id
JOIN  (SELECT MAX(generated_at) AS generated_at
       FROM   recommendations
       WHERE  user_id = @user_id AND strategy = @strategy
         AND  seed_key = COALESCE(@seed_movie_id, 0)) AS latest
       ON latest.generated_at = r.generated_at
WHERE  r.user_id  = @user_id
  AND  r.strategy = @strategy
  AND  r.seed_key = COALESCE(@seed_movie_id, 0)
  AND  NOT EXISTS (SELECT 1 FROM ratings x                       -- rated since generation
                   WHERE x.user_id = r.user_id AND x.movie_id = r.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM hidden_movies h                 -- hidden since generation
                   WHERE h.user_id = r.user_id AND h.movie_id = r.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM view_events ve                  -- finished since generation
                   WHERE ve.user_id = r.user_id AND ve.movie_id = r.movie_id
                     AND ve.progress >= 90)
  AND  (r.strategy = 'popular'                                   -- charts are exempt
        OR NOT EXISTS (SELECT 1 FROM recommendations o           -- shown in ANOTHER personal list
                       WHERE o.user_id = r.user_id AND o.movie_id = r.movie_id
                         AND o.rec_id <> r.rec_id                -- own row does not count, so a
                         AND o.strategy <> 'popular'             -- refresh shows the same list
                         AND o.shown_at >= NOW() - INTERVAL 1 DAY))
ORDER BY r.rec_rank;
SELECT rec_rank, movie_id, title, score FROM page ORDER BY rec_rank;
-- | +----------+----------+--------------+-------+
-- | | rec_rank | movie_id | title        | score |
-- | +----------+----------+--------------+-------+
-- | | 4        | 2        | Finding Nemo | 1.000 |
-- | +----------+----------+--------------+-------+
-- => 1 row(s)

-- 9f: run Q6 for alice again: everything just shown is held back
SET @user_id = 2;
WITH taste AS (            -- favourite genres + genres of movies rated 4.0 or higher
    SELECT ug.genre_id FROM user_genres ug WHERE ug.user_id = @user_id
    UNION
    SELECT mg.genre_id
    FROM   ratings r
    JOIN   movie_genres mg ON mg.movie_id = r.movie_id
    WHERE  r.user_id = @user_id AND r.score >= 4.0
), movie_stats AS (        -- same minimum of 3 ratings as Q5
    SELECT movie_id, AVG(score) AS avg_score, COUNT(*) AS n_ratings
    FROM   ratings
    GROUP BY movie_id
    HAVING COUNT(*) >= 3
)
SELECT m.movie_id, m.title, ROUND(s.avg_score, 2) AS avg_score, s.n_ratings
FROM   movies m
JOIN   movie_stats s ON s.movie_id = m.movie_id
WHERE  EXISTS (SELECT 1 FROM movie_genres mg
               JOIN   taste t ON t.genre_id = mg.genre_id
               WHERE  mg.movie_id = m.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM ratings r                       -- already rated
                   WHERE r.user_id = @user_id AND r.movie_id = m.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM view_events ve                  -- already finished
                   WHERE ve.user_id = @user_id AND ve.movie_id = m.movie_id
                     AND ve.progress >= 90)
  AND  NOT EXISTS (SELECT 1 FROM hidden_movies h                 -- hidden
                   WHERE h.user_id = @user_id AND h.movie_id = m.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM recommendations rc              -- shown in last 24 h
                   WHERE rc.user_id = @user_id AND rc.movie_id = m.movie_id
                     AND rc.strategy <> 'popular'       -- chart displays do not count
                     AND rc.shown_at >= NOW() - INTERVAL 1 DAY)
ORDER BY s.avg_score DESC, s.n_ratings DESC, m.title
LIMIT 10;
-- => Empty set (0 rows)

SET @strategy = 'popular', @seed_movie_id = NULL;
-- 9g: the popular list is a chart: The Godfather stays although it was shown
--     in a personal list 3 hours ago (only hidden Interstellar is dropped)
DROP TEMPORARY TABLE IF EXISTS page;
CREATE TEMPORARY TABLE page AS
SELECT r.rec_id, r.rec_rank, m.movie_id, m.title, r.score
FROM   recommendations r
JOIN   movies m ON m.movie_id = r.movie_id
JOIN  (SELECT MAX(generated_at) AS generated_at
       FROM   recommendations
       WHERE  user_id = @user_id AND strategy = @strategy
         AND  seed_key = COALESCE(@seed_movie_id, 0)) AS latest
       ON latest.generated_at = r.generated_at
WHERE  r.user_id  = @user_id
  AND  r.strategy = @strategy
  AND  r.seed_key = COALESCE(@seed_movie_id, 0)
  AND  NOT EXISTS (SELECT 1 FROM ratings x                       -- rated since generation
                   WHERE x.user_id = r.user_id AND x.movie_id = r.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM hidden_movies h                 -- hidden since generation
                   WHERE h.user_id = r.user_id AND h.movie_id = r.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM view_events ve                  -- finished since generation
                   WHERE ve.user_id = r.user_id AND ve.movie_id = r.movie_id
                     AND ve.progress >= 90)
  AND  (r.strategy = 'popular'                                   -- charts are exempt
        OR NOT EXISTS (SELECT 1 FROM recommendations o           -- shown in ANOTHER personal list
                       WHERE o.user_id = r.user_id AND o.movie_id = r.movie_id
                         AND o.rec_id <> r.rec_id                -- own row does not count, so a
                         AND o.strategy <> 'popular'             -- refresh shows the same list
                         AND o.shown_at >= NOW() - INTERVAL 1 DAY))
ORDER BY r.rec_rank;
SELECT rec_rank, movie_id, title, score FROM page ORDER BY rec_rank;
-- | +----------+----------+---------------+-------+
-- | | rec_rank | movie_id | title         | score |
-- | +----------+----------+---------------+-------+
-- | | 2        | 15       | Forrest Gump  | 2.000 |
-- | | 3        | 12       | Titanic       | 2.000 |
-- | | 4        | 3        | Shrek         | 1.000 |
-- | | 5        | 19       | Superbad      | 1.000 |
-- | | 6        | 16       | The Godfather | 1.000 |
-- | | 7        | 4        | Up            | 1.000 |
-- | +----------+----------+---------------+-------+
-- => 6 row(s)

-- ==== Q10: Admin adds a movie (only an admin may do this) =============
-- 10a: admin (user 1) adds Dune: Part Two
SET @actor_id = 1, @title = 'Dune: Part Two', @year = 2024, @runtime = 166, @tmdb_id = 693134;
START TRANSACTION;
INSERT INTO movies (title, release_year, runtime, tmdb_id)
SELECT @title, @year, @runtime, @tmdb_id
FROM   DUAL
WHERE  EXISTS (SELECT 1 FROM users WHERE user_id = @actor_id AND role = 'admin');
-- => Query OK, 1 row(s) affected

SET @new_movie_id = IF(ROW_COUNT() = 1, LAST_INSERT_ID(), NULL);
INSERT INTO movie_genres (movie_id, genre_id)
SELECT @new_movie_id, genre_id
FROM   genres
WHERE  @new_movie_id IS NOT NULL
  AND  name IN ('Action', 'Sci-Fi');
-- => Query OK, 2 row(s) affected

COMMIT;

SELECT m.movie_id, m.title, m.release_year, m.runtime, m.tmdb_id,
       GROUP_CONCAT(g.name ORDER BY g.name SEPARATOR ', ') AS genres
FROM   movies m
LEFT JOIN movie_genres mg ON mg.movie_id = m.movie_id
LEFT JOIN genres g        ON g.genre_id  = mg.genre_id
WHERE  m.title = 'Dune: Part Two'
GROUP BY m.movie_id, m.title, m.release_year, m.runtime, m.tmdb_id;
-- | +----------+----------------+--------------+---------+---------+----------------+
-- | | movie_id | title          | release_year | runtime | tmdb_id | genres         |
-- | +----------+----------------+--------------+---------+---------+----------------+
-- | | 21       | Dune: Part Two | 2024         | 166     | 693134  | Action, Sci-Fi |
-- | +----------+----------------+--------------+---------+---------+----------------+
-- => 1 row(s)

-- 10b: alice (a regular user) tries the same — nothing is inserted
SET @actor_id = 2, @title = 'Oppenheimer', @year = 2023, @runtime = 180, @tmdb_id = 872585;
START TRANSACTION;
INSERT INTO movies (title, release_year, runtime, tmdb_id)
SELECT @title, @year, @runtime, @tmdb_id
FROM   DUAL
WHERE  EXISTS (SELECT 1 FROM users WHERE user_id = @actor_id AND role = 'admin');
-- => Query OK, 0 row(s) affected

SET @new_movie_id = IF(ROW_COUNT() = 1, LAST_INSERT_ID(), NULL);
INSERT INTO movie_genres (movie_id, genre_id)
SELECT @new_movie_id, genre_id
FROM   genres
WHERE  @new_movie_id IS NOT NULL
  AND  name IN ('Drama');
-- => Query OK, 0 row(s) affected

COMMIT;

SELECT COUNT(*) AS oppenheimer_rows FROM movies WHERE title = 'Oppenheimer';
-- | +------------------+
-- | | oppenheimer_rows |
-- | +------------------+
-- | | 0                |
-- | +------------------+
-- => 1 row(s)

-- ==== Q11: Statistics for the admin dashboard =========================
-- 11a: average rating per genre
SELECT g.name                         AS genre,
       COUNT(DISTINCT mg.movie_id)    AS movies,
       COUNT(r.score)                 AS ratings,
       ROUND(AVG(r.score), 2)         AS avg_score
FROM   genres g
LEFT JOIN movie_genres mg ON mg.genre_id = g.genre_id
LEFT JOIN ratings r       ON r.movie_id  = mg.movie_id
GROUP BY g.genre_id, g.name
ORDER BY avg_score DESC, g.name;
-- | +-----------+--------+---------+-----------+
-- | | genre     | movies | ratings | avg_score |
-- | +-----------+--------+---------+-----------+
-- | | Drama     | 9      | 26      | 4.31      |
-- | | Sci-Fi    | 6      | 16      | 4.16      |
-- | | Romance   | 4      | 13      | 4.15      |
-- | | Animation | 5      | 14      | 4.14      |
-- | | Action    | 6      | 16      | 4.06      |
-- | | Comedy    | 7      | 19      | 4.00      |
-- | +-----------+--------+---------+-----------+
-- => 6 row(s)

-- 11b: most-rated movies
SELECT m.title, COUNT(*) AS ratings, ROUND(AVG(r.score), 2) AS avg_score
FROM   ratings r
JOIN   movies m ON m.movie_id = r.movie_id
GROUP BY m.movie_id, m.title
ORDER BY ratings DESC, avg_score DESC, m.title
LIMIT 5;
-- | +---------------+---------+-----------+
-- | | title         | ratings | avg_score |
-- | +---------------+---------+-----------+
-- | | Forrest Gump  | 4       | 4.50      |
-- | | The Matrix    | 4       | 4.25      |
-- | | The Godfather | 3       | 4.67      |
-- | | Interstellar  | 3       | 4.50      |
-- | | Spirited Away | 3       | 4.50      |
-- | +---------------+---------+-----------+
-- => 5 row(s)

-- 11c: active users in the last 7 days (rated or watched something)
SELECT COUNT(DISTINCT user_id) AS active_users_7d
FROM  (SELECT user_id FROM view_events WHERE viewed_at >= NOW() - INTERVAL 7 DAY
       UNION
       SELECT user_id FROM ratings     WHERE rated_at  >= NOW() - INTERVAL 7 DAY) AS a;
-- | +-----------------+
-- | | active_users_7d |
-- | +-----------------+
-- | | 5               |
-- | +-----------------+
-- => 1 row(s)
