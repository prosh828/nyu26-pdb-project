-- =====================================================================
-- Recco — Part 2: the 11 queries, as the application will send them.
-- Placeholders use PyMySQL's %(name)s style; the driver escapes every
-- value, so no user input is ever pasted into SQL text.
-- 04_test_queries.sql runs the same queries with concrete values.
--
-- 24-hour rule: a movie shown in a PERSONAL list (genre, item_cf) is not
-- put in or shown from another personal list for 24 hours. Refreshing the
-- same list shows the same list. Popular charts are exempt both ways.
-- =====================================================================


-- ---------------------------------------------------------------------
-- (1) Sign up with exactly three favourite genres (use case 1)
-- ---------------------------------------------------------------------
START TRANSACTION;
INSERT INTO users (username, email, password_hash, role)
SELECT %(username)s, %(email)s, %(password_hash)s, 'user'
FROM   DUAL
WHERE  (SELECT COUNT(*) FROM genres WHERE genre_id IN %(genre_ids)s) = 3;   -- exactly 3 distinct, existing genres
-- if cursor.rowcount == 0: ROLLBACK and ask for three valid genres
-- new_user_id = cursor.lastrowid
INSERT INTO user_genres (user_id, genre_id)
SELECT %(new_user_id)s, genre_id
FROM   genres
WHERE  genre_id IN %(genre_ids)s;
COMMIT;

-- ---------------------------------------------------------------------
-- (2) Rate or re-rate a movie in one statement (use case 3)
-- ---------------------------------------------------------------------
INSERT INTO ratings (user_id, movie_id, score, review)
VALUES (%(user_id)s, %(movie_id)s, %(score)s, %(review)s) AS new
ON DUPLICATE KEY UPDATE score    = new.score,
                        review   = new.review,
                        rated_at = CURRENT_TIMESTAMP;

-- ---------------------------------------------------------------------
-- (3) Continue watching (use case 7)
-- ---------------------------------------------------------------------
SELECT m.movie_id, m.title, lv.progress, lv.viewed_at AS last_viewed
FROM  (SELECT ve.movie_id, ve.progress, ve.viewed_at,
              ROW_NUMBER() OVER (PARTITION BY ve.movie_id
                                 ORDER BY ve.viewed_at DESC, ve.event_id DESC) AS rn
       FROM   view_events ve
       WHERE  ve.user_id = %(user_id)s) AS lv
JOIN   movies m ON m.movie_id = lv.movie_id
WHERE  lv.rn = 1
  AND  lv.progress < 90
ORDER BY lv.viewed_at DESC;

-- ---------------------------------------------------------------------
-- (4) Trending this week (use case 9)
-- ---------------------------------------------------------------------
SELECT m.movie_id, m.title,
       COUNT(DISTINCT ve.user_id) AS viewers,
       COUNT(*)                   AS views
FROM   view_events ve
JOIN   movies m ON m.movie_id = ve.movie_id
WHERE  ve.viewed_at >= NOW() - INTERVAL 7 DAY
GROUP BY m.movie_id, m.title
ORDER BY viewers DESC, views DESC, m.title
LIMIT 10;

-- ---------------------------------------------------------------------
-- (5) Top-rated movies per genre, at least 3 ratings (use case 9)
-- ---------------------------------------------------------------------
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

-- ---------------------------------------------------------------------
-- (6) Genre-based picks for a user (use case 8)
-- ---------------------------------------------------------------------
WITH taste AS (            -- favourite genres + genres of movies rated 4.0 or higher
    SELECT ug.genre_id FROM user_genres ug WHERE ug.user_id = %(user_id)s
    UNION
    SELECT mg.genre_id
    FROM   ratings r
    JOIN   movie_genres mg ON mg.movie_id = r.movie_id
    WHERE  r.user_id = %(user_id)s AND r.score >= 4.0
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
                   WHERE r.user_id = %(user_id)s AND r.movie_id = m.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM view_events ve                  -- already finished
                   WHERE ve.user_id = %(user_id)s AND ve.movie_id = m.movie_id
                     AND ve.progress >= 90)
  AND  NOT EXISTS (SELECT 1 FROM hidden_movies h                 -- hidden
                   WHERE h.user_id = %(user_id)s AND h.movie_id = m.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM recommendations rc              -- shown in last 24 h
                   WHERE rc.user_id = %(user_id)s AND rc.movie_id = m.movie_id
                     AND rc.strategy <> 'popular'       -- chart displays do not count
                     AND rc.shown_at >= NOW() - INTERVAL 1 DAY)
ORDER BY s.avg_score DESC, s.n_ratings DESC, m.title
LIMIT 10;

-- ---------------------------------------------------------------------
-- (7) "Because you liked X" — item-to-item (use case 8)
-- ---------------------------------------------------------------------
SELECT m.movie_id, m.title,
       COUNT(*)             AS co_raters,
       ROUND(AVG(r.score), 2) AS avg_co_score
FROM   ratings r
JOIN   movies  m ON m.movie_id = r.movie_id
WHERE  r.user_id IN (SELECT x.user_id FROM ratings x            -- people who liked X
                     WHERE x.movie_id = %(seed_movie_id)s
                       AND x.score   >= 4.0
                       AND x.user_id <> %(user_id)s)
  AND  r.score    >= 4.0                                        -- ... and also liked this
  AND  r.movie_id <> %(seed_movie_id)s
  AND  NOT EXISTS (SELECT 1 FROM ratings r2
                   WHERE r2.user_id = %(user_id)s AND r2.movie_id = m.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM view_events ve
                   WHERE ve.user_id = %(user_id)s AND ve.movie_id = m.movie_id
                     AND ve.progress >= 90)
  AND  NOT EXISTS (SELECT 1 FROM hidden_movies h
                   WHERE h.user_id = %(user_id)s AND h.movie_id = m.movie_id)
  AND  NOT EXISTS (SELECT 1 FROM recommendations rc
                   WHERE rc.user_id = %(user_id)s AND rc.movie_id = m.movie_id
                     AND rc.strategy <> 'popular'       -- chart displays do not count
                     AND rc.shown_at >= NOW() - INTERVAL 1 DAY)
GROUP BY m.movie_id, m.title
ORDER BY co_raters DESC, avg_co_score DESC, m.title
LIMIT 10;

-- ---------------------------------------------------------------------
-- (8) Regenerate a user's three ranked lists (use case 12)
-- ---------------------------------------------------------------------
-- gen_at: one timestamp for the whole run, e.g. datetime.now(timezone.utc)

-- 8a: genre-based list
INSERT INTO recommendations
       (user_id, movie_id, strategy, seed_movie_id, rec_rank, score, generated_at)
WITH taste AS (            -- favourite genres + genres of movies rated 4.0 or higher
    SELECT ug.genre_id FROM user_genres ug WHERE ug.user_id = %(user_id)s
    UNION
    SELECT mg.genre_id
    FROM   ratings r
    JOIN   movie_genres mg ON mg.movie_id = r.movie_id
    WHERE  r.user_id = %(user_id)s AND r.score >= 4.0
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
                       WHERE r.user_id = %(user_id)s AND r.movie_id = m.movie_id)
      AND  NOT EXISTS (SELECT 1 FROM view_events ve                  -- already finished
                       WHERE ve.user_id = %(user_id)s AND ve.movie_id = m.movie_id
                         AND ve.progress >= 90)
      AND  NOT EXISTS (SELECT 1 FROM hidden_movies h                 -- hidden
                       WHERE h.user_id = %(user_id)s AND h.movie_id = m.movie_id)
      AND  NOT EXISTS (SELECT 1 FROM recommendations rc              -- shown in last 24 h
                       WHERE rc.user_id = %(user_id)s AND rc.movie_id = m.movie_id
                         AND rc.strategy <> 'popular'       -- chart displays do not count
                         AND rc.shown_at >= NOW() - INTERVAL 1 DAY)
    ORDER BY s.avg_score DESC, s.n_ratings DESC, m.title
    LIMIT 10
)
SELECT %(user_id)s, c.movie_id, 'genre', NULL,
       ROW_NUMBER() OVER (ORDER BY c.avg_score DESC, c.n_ratings DESC, c.title),
       ROUND(c.avg_score, 3), %(gen_at)s
FROM   candidates c;

-- 8b: popular list (a chart: no 24-hour rule)
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
                       WHERE r.user_id = %(user_id)s AND r.movie_id = m.movie_id)
      AND  NOT EXISTS (SELECT 1 FROM view_events ve
                       WHERE ve.user_id = %(user_id)s AND ve.movie_id = m.movie_id
                         AND ve.progress >= 90)
      AND  NOT EXISTS (SELECT 1 FROM hidden_movies h
                       WHERE h.user_id = %(user_id)s AND h.movie_id = m.movie_id)
    ORDER BY t.viewers DESC, t.views DESC, m.title
    LIMIT 10
)
SELECT %(user_id)s, c.movie_id, 'popular', NULL,
       ROW_NUMBER() OVER (ORDER BY c.viewers DESC, c.views DESC, c.title),
       c.viewers, %(gen_at)s
FROM   candidates c;

-- 8c: "Because you liked X" list, one per seed movie X
INSERT INTO recommendations
       (user_id, movie_id, strategy, seed_movie_id, rec_rank, score, generated_at)
WITH candidates AS (       -- Q7 for the seed movie
    SELECT m.movie_id, m.title,
           COUNT(*)     AS co_raters,
           AVG(r.score) AS avg_co_score
    FROM   ratings r
    JOIN   movies  m ON m.movie_id = r.movie_id
    WHERE  r.user_id IN (SELECT x.user_id FROM ratings x
                         WHERE x.movie_id = %(seed_movie_id)s
                           AND x.score   >= 4.0
                           AND x.user_id <> %(user_id)s)
      AND  r.score    >= 4.0
      AND  r.movie_id <> %(seed_movie_id)s
      AND  NOT EXISTS (SELECT 1 FROM ratings r
                       WHERE r.user_id = %(user_id)s AND r.movie_id = m.movie_id)
      AND  NOT EXISTS (SELECT 1 FROM view_events ve
                       WHERE ve.user_id = %(user_id)s AND ve.movie_id = m.movie_id
                         AND ve.progress >= 90)
      AND  NOT EXISTS (SELECT 1 FROM hidden_movies h
                       WHERE h.user_id = %(user_id)s AND h.movie_id = m.movie_id)
      AND  NOT EXISTS (SELECT 1 FROM recommendations rc
                       WHERE rc.user_id = %(user_id)s AND rc.movie_id = m.movie_id
                         AND rc.strategy <> 'popular'       -- chart displays do not count
                         AND rc.shown_at >= NOW() - INTERVAL 1 DAY)
    GROUP BY m.movie_id, m.title
    ORDER BY co_raters DESC, avg_co_score DESC, m.title
    LIMIT 10
)
SELECT %(user_id)s, c.movie_id, 'item_cf', %(seed_movie_id)s,
       ROW_NUMBER() OVER (ORDER BY c.co_raters DESC, c.avg_co_score DESC, c.title),
       c.co_raters, %(gen_at)s
FROM   candidates c;

-- ---------------------------------------------------------------------
-- (9) Serve the latest list and mark it as shown (use case 8)
-- ---------------------------------------------------------------------
-- 9a: rows to display (seed_movie_id is NULL except for item_cf lists)
SELECT r.rec_id, r.rec_rank, m.movie_id, m.title, r.score
FROM   recommendations r
JOIN   movies m ON m.movie_id = r.movie_id
JOIN  (SELECT MAX(generated_at) AS generated_at
       FROM   recommendations
       WHERE  user_id = %(user_id)s AND strategy = %(strategy)s
         AND  seed_key = COALESCE(%(seed_movie_id)s, 0)) AS latest
       ON latest.generated_at = r.generated_at
WHERE  r.user_id  = %(user_id)s
  AND  r.strategy = %(strategy)s
  AND  r.seed_key = COALESCE(%(seed_movie_id)s, 0)
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

-- 9b: stamp exactly the rows the page displayed (rec_ids from 9a).
--     Rows already stamped keep their first shown_at, so a refresh does
--     not extend the 24-hour window.
UPDATE recommendations
SET    shown_at = NOW()
WHERE  rec_id IN %(displayed_rec_ids)s
  AND  shown_at IS NULL;

-- ---------------------------------------------------------------------
-- (10) Admin adds a movie; non-admins insert nothing (use case 10)
-- ---------------------------------------------------------------------
START TRANSACTION;
INSERT INTO movies (title, release_year, runtime, tmdb_id)
SELECT %(title)s, %(year)s, %(runtime)s, %(tmdb_id)s
FROM   DUAL
WHERE  EXISTS (SELECT 1 FROM users WHERE user_id = %(actor_id)s AND role = 'admin');
-- new_movie_id = cursor.lastrowid if the INSERT affected 1 row, else stop here
INSERT INTO movie_genres (movie_id, genre_id)
SELECT %(new_movie_id)s, genre_id
FROM   genres
WHERE  genre_id IN %(genre_ids)s;
COMMIT;

-- ---------------------------------------------------------------------
-- (11) Statistics for the admin dashboard (use case 13)
-- ---------------------------------------------------------------------
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
