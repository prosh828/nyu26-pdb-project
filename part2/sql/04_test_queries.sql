-- =====================================================================
-- Recco — Part 2: the queries of 03_queries.sql with concrete values.
-- Run top to bottom on a fresh load of 01_schema.sql + 02_sample_data.sql.
-- Statements marked "EXPECTED ERROR" are meant to fail: they prove that
-- a constraint works. (In MySQL Workbench, turn on "Continue on SQL
-- Script Error" or run those lines one by one.)
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

-- Movies a user has hidden
SELECT u.username, m.title, h.hidden_at
FROM   hidden_movies h
JOIN   users  u ON u.user_id  = h.user_id
JOIN   movies m ON m.movie_id = h.movie_id
ORDER  BY u.username, m.title;

-- Users who rated at least one movie
SELECT DISTINCT u.username
FROM   users u
JOIN   ratings r ON r.user_id = u.user_id
ORDER  BY u.username;

-- All movies in the Sci-Fi genre
SELECT m.title, m.release_year
FROM   movies m
JOIN   movie_genres mg ON mg.movie_id = m.movie_id
JOIN   genres g        ON g.genre_id  = mg.genre_id
WHERE  g.name = 'Sci-Fi'
ORDER  BY m.release_year;

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
SET @new_user_id = IF(ROW_COUNT() = 1, LAST_INSERT_ID(), NULL);
INSERT INTO user_genres (user_id, genre_id)
SELECT @new_user_id, genre_id
FROM   genres
WHERE  @new_user_id IS NOT NULL
  AND  name IN (@g1, @g2, @g3);
COMMIT;

SELECT u.user_id, u.username, u.email, u.role,
       GROUP_CONCAT(g.name ORDER BY g.name SEPARATOR ', ') AS favourite_genres
FROM   users u
JOIN   user_genres ug ON ug.user_id = u.user_id
JOIN   genres g       ON g.genre_id = ug.genre_id
WHERE  u.user_id = @new_user_id
GROUP BY u.user_id, u.username, u.email, u.role;

-- 1b: heidi picks a genre that does not exist ('Western') -> no account at all
SET @username = 'heidi', @email = 'heidi@nyu.edu',
    @g1 = 'Comedy', @g2 = 'Drama', @g3 = 'Western';
START TRANSACTION;
INSERT INTO users (username, email, password_hash, role)
SELECT @username, @email, @password_hash, 'user'
FROM   DUAL
WHERE  (SELECT COUNT(*) FROM genres WHERE name IN (@g1, @g2, @g3)) = 3;   -- exactly 3 distinct, existing genres
SET @new_user_id = IF(ROW_COUNT() = 1, LAST_INSERT_ID(), NULL);
INSERT INTO user_genres (user_id, genre_id)
SELECT @new_user_id, genre_id
FROM   genres
WHERE  @new_user_id IS NOT NULL
  AND  name IN (@g1, @g2, @g3);
COMMIT;

SELECT (SELECT COUNT(*) FROM users WHERE username = 'heidi') AS heidi_users,
       (SELECT COUNT(*) FROM user_genres ug JOIN users u ON u.user_id = ug.user_id
        WHERE u.username = 'heidi')                          AS heidi_genres;

-- EXPECTED ERROR: the same email again violates users_email_uq
INSERT INTO users (username, email, password_hash)
VALUES ('grace2', 'grace@nyu.edu', @password_hash);

-- ==== Q2: Rate, then re-rate, a movie (one statement, upsert) =========
-- bob rates The Dark Knight 3.0, then changes his mind to 4.5
SET @user_id = 3, @movie_id = 9, @score = 3.0, @review = NULL;
INSERT INTO ratings (user_id, movie_id, score, review)
VALUES (@user_id, @movie_id, @score, @review) AS new
ON DUPLICATE KEY UPDATE score    = new.score,
                        review   = new.review,
                        rated_at = CURRENT_TIMESTAMP;

SET @score = 4.5, @review = 'Better the second time.';
INSERT INTO ratings (user_id, movie_id, score, review)
VALUES (@user_id, @movie_id, @score, @review) AS new
ON DUPLICATE KEY UPDATE score    = new.score,
                        review   = new.review,
                        rated_at = CURRENT_TIMESTAMP;

SELECT user_id, movie_id, score, review
FROM   ratings
WHERE  user_id = @user_id AND movie_id = @movie_id;

-- EXPECTED ERROR: 4.3 is not on the half-star scale (ratings_score_chk)
INSERT INTO ratings (user_id, movie_id, score) VALUES (3, 1, 4.3);

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

-- EXPECTED ERROR: a second rank 1 in the same list (rec_list_rank_uq).
-- seed_movie_id is NULL here; the seed_key column is what makes this fail.
INSERT INTO recommendations
       (user_id, movie_id, strategy, seed_movie_id, rec_rank, score, generated_at)
VALUES (@user_id, 20, 'genre', NULL, 1, 1.000, @gen_at);

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

-- 8d: the three stored lists
SELECT r.strategy, r.seed_movie_id, r.rec_rank, m.title, r.score
FROM   recommendations r
JOIN   movies m ON m.movie_id = r.movie_id
WHERE  r.user_id = @user_id AND r.generated_at = @gen_at
ORDER BY r.strategy, r.rec_rank;

-- ==== Q9: Serve the latest list and mark it as shown ==================
-- The application stamps exactly the rows the page displayed (by rec_id).
-- Here a temporary table "page" stands in for that list of rec_ids.

-- After the lists were generated, alice hides Interstellar.
INSERT INTO hidden_movies (user_id, movie_id) VALUES (2, 8);

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

-- 9b: stamp the displayed rows with shown_at
UPDATE recommendations r
JOIN   page p ON p.rec_id = r.rec_id
SET    r.shown_at = NOW()
WHERE  r.shown_at IS NULL;               -- keep the first time it was shown

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

-- 9d: stamping again changes nothing: shown_at keeps the first display time
UPDATE recommendations r
JOIN   page p ON p.rec_id = r.rec_id
SET    r.shown_at = NOW()
WHERE  r.shown_at IS NULL;               -- keep the first time it was shown

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

-- ==== Q10: Admin adds a movie (only an admin may do this) =============
-- 10a: admin (user 1) adds Dune: Part Two
SET @actor_id = 1, @title = 'Dune: Part Two', @year = 2024, @runtime = 166, @tmdb_id = 693134;
START TRANSACTION;
INSERT INTO movies (title, release_year, runtime, tmdb_id)
SELECT @title, @year, @runtime, @tmdb_id
FROM   DUAL
WHERE  EXISTS (SELECT 1 FROM users WHERE user_id = @actor_id AND role = 'admin');
SET @new_movie_id = IF(ROW_COUNT() = 1, LAST_INSERT_ID(), NULL);
INSERT INTO movie_genres (movie_id, genre_id)
SELECT @new_movie_id, genre_id
FROM   genres
WHERE  @new_movie_id IS NOT NULL
  AND  name IN ('Action', 'Sci-Fi');
COMMIT;

SELECT m.movie_id, m.title, m.release_year, m.runtime, m.tmdb_id,
       GROUP_CONCAT(g.name ORDER BY g.name SEPARATOR ', ') AS genres
FROM   movies m
LEFT JOIN movie_genres mg ON mg.movie_id = m.movie_id
LEFT JOIN genres g        ON g.genre_id  = mg.genre_id
WHERE  m.title = 'Dune: Part Two'
GROUP BY m.movie_id, m.title, m.release_year, m.runtime, m.tmdb_id;

-- 10b: alice (a regular user) tries the same — nothing is inserted
SET @actor_id = 2, @title = 'Oppenheimer', @year = 2023, @runtime = 180, @tmdb_id = 872585;
START TRANSACTION;
INSERT INTO movies (title, release_year, runtime, tmdb_id)
SELECT @title, @year, @runtime, @tmdb_id
FROM   DUAL
WHERE  EXISTS (SELECT 1 FROM users WHERE user_id = @actor_id AND role = 'admin');
SET @new_movie_id = IF(ROW_COUNT() = 1, LAST_INSERT_ID(), NULL);
INSERT INTO movie_genres (movie_id, genre_id)
SELECT @new_movie_id, genre_id
FROM   genres
WHERE  @new_movie_id IS NOT NULL
  AND  name IN ('Drama');
COMMIT;

SELECT COUNT(*) AS oppenheimer_rows FROM movies WHERE title = 'Oppenheimer';

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

-- 11b: most-rated movies
SELECT m.title, COUNT(*) AS ratings, ROUND(AVG(r.score), 2) AS avg_score
FROM   ratings r
JOIN   movies m ON m.movie_id = r.movie_id
GROUP BY m.movie_id, m.title
ORDER BY ratings DESC, avg_score DESC, m.title
LIMIT 5;

-- 11c: active users in the last 7 days (rated or watched something)
SELECT COUNT(DISTINCT user_id) AS active_users_7d
FROM  (SELECT user_id FROM view_events WHERE viewed_at >= NOW() - INTERVAL 7 DAY
       UNION
       SELECT user_id FROM ratings     WHERE rated_at  >= NOW() - INTERVAL 7 DAY) AS a;
