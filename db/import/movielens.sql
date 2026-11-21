-- =====================================================================
-- Recco — import MovieLens ml-latest-small into the Recco tables.
-- Run by `flask import-movielens` (the `loader` service in env/docker-compose.yml),
-- which replaces {{ML_DIR}} with the folder holding the CSV files and runs
-- every statement in ONE transaction (all or nothing).
--
-- ID mapping
--   MovieLens userId  N -> users.user_id   1000 + N   (username ml_user_N)
--   MovieLens movieId N -> movies.movie_id 1000 + N,
--     unless the movie already exists (e.g. sample data): matched by
--     tmdb_id first, then by (title, release_year).
--
-- Clean-up rules
--   "Matrix, The (1999)"  -> title "The Matrix", release_year 1999
--   no "(YYYY)" at the end -> release_year NULL
--   duplicate (title, release_year) -> merged into the lowest movieId;
--     if a user rated both copies, the later rating wins
--   tmdbId used by two movies -> kept on the first one only
--   "(no genres listed)" -> no movie_genres row
--
-- Format rules for this file (the runner is a simple splitter):
-- comments only on their own lines, every statement ends with ";" at
-- the end of a line, and no ";" inside statements.
-- =====================================================================

SET time_zone = '+00:00';

-- ---------------------------------------------------------------------
-- 1. Staging tables. TEMPORARY: only this connection sees them, they
--    are dropped automatically, and the schema stays at 10 tables.
-- ---------------------------------------------------------------------
CREATE TEMPORARY TABLE stg_movies (
    ml_movie_id  INT          NOT NULL PRIMARY KEY,
    raw_title    VARCHAR(300) NOT NULL,
    raw_genres   VARCHAR(300) NOT NULL
);

CREATE TEMPORARY TABLE stg_links (
    ml_movie_id  INT NOT NULL PRIMARY KEY,
    tmdb_id      INT NULL
);

CREATE TEMPORARY TABLE stg_ratings (
    ml_user_id   INT          NOT NULL,
    ml_movie_id  INT          NOT NULL,
    score        DECIMAL(2,1) NOT NULL,
    ts           BIGINT       NOT NULL,
    PRIMARY KEY (ml_user_id, ml_movie_id)
);

-- The CSVs use CRLF line endings: split on \n and strip a trailing \r
-- from the last column, so LF-only files work too.
LOAD DATA LOCAL INFILE '{{ML_DIR}}/movies.csv' INTO TABLE stg_movies
    CHARACTER SET utf8mb4
    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY ''
    LINES TERMINATED BY '\n'
    IGNORE 1 LINES
    (ml_movie_id, raw_title, @genres)
    SET raw_genres = TRIM(TRAILING '\r' FROM @genres);

LOAD DATA LOCAL INFILE '{{ML_DIR}}/links.csv' INTO TABLE stg_links
    CHARACTER SET utf8mb4
    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY ''
    LINES TERMINATED BY '\n'
    IGNORE 1 LINES
    (ml_movie_id, @imdb_id, @tmdb_id)
    SET tmdb_id = NULLIF(TRIM(TRAILING '\r' FROM @tmdb_id), '');

LOAD DATA LOCAL INFILE '{{ML_DIR}}/ratings.csv' INTO TABLE stg_ratings
    CHARACTER SET utf8mb4
    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY ''
    LINES TERMINATED BY '\n'
    IGNORE 1 LINES
    (ml_user_id, ml_movie_id, score, @ts)
    SET ts = TRIM(TRAILING '\r' FROM @ts);

-- ---------------------------------------------------------------------
-- 2. Split "Title, The (1999)" into title + release_year.
--    REGEXP_REPLACE in MySQL 8 (ICU) supports $1-style back-references.
--    Match type 'c' = case-sensitive, so ", the" inside a title is kept.
-- ---------------------------------------------------------------------
CREATE TEMPORARY TABLE stg_movie_clean (
    ml_movie_id   INT          NOT NULL PRIMARY KEY,
    title         VARCHAR(255) NOT NULL,
    release_year  SMALLINT     NULL,
    tmdb_id       INT          NULL
);

INSERT INTO stg_movie_clean (ml_movie_id, title, release_year, tmdb_id)
SELECT p.ml_movie_id,
       REGEXP_REPLACE(p.base,
                      '^(.+), (The|A|An|Le|La|Les|El|Das)( \\(.+\\))?$',
                      '$2 $1$3', 1, 0, 'c'),
       p.release_year,
       l.tmdb_id
FROM  (SELECT ml_movie_id,
              TRIM(REGEXP_REPLACE(TRIM(raw_title), ' *\\([0-9]{4}\\)$', '')) AS base,
              CAST(SUBSTRING(REGEXP_SUBSTR(TRIM(raw_title), '\\([0-9]{4}\\)$'), 2, 4)
                   AS UNSIGNED) AS release_year
       FROM   stg_movies) AS p
LEFT JOIN stg_links l ON l.ml_movie_id = p.ml_movie_id;

-- ---------------------------------------------------------------------
-- 3. Decide the Recco movie_id for every MovieLens movie.
--    existing_id: a movie already in Recco (tmdb_id match preferred).
--    Within a duplicate (title, release_year) group every copy gets the
--    same target. GROUP/PARTITION BY use the column collation
--    (utf8mb4_0900_ai_ci), the same rule UNIQUE(title, release_year)
--    uses, so "duplicate" here means exactly what the constraint means.
--    (A TEMPORARY table may appear only once per statement, hence the
--    window functions instead of self-joins.)
-- ---------------------------------------------------------------------
CREATE TEMPORARY TABLE stg_movie_map AS
SELECT x.ml_movie_id,
       x.title,
       x.release_year,
       COALESCE(MAX(x.existing_id) OVER grp,
                1000 + FIRST_VALUE(x.ml_movie_id) OVER grp_ordered) AS target_id,
       (MAX(x.existing_id) OVER grp IS NULL
        AND ROW_NUMBER() OVER grp_ordered = 1)                   AS is_new,
       CASE WHEN x.tmdb_id IS NOT NULL
             AND ROW_NUMBER() OVER (PARTITION BY x.tmdb_id ORDER BY x.ml_movie_id) = 1
            THEN x.tmdb_id END                                  AS tmdb_id
FROM  (SELECT s.*,
              (SELECT m.movie_id
               FROM   movies m
               WHERE  m.tmdb_id = s.tmdb_id
                  OR (m.title = s.title AND m.release_year <=> s.release_year)
               ORDER  BY (m.tmdb_id <=> s.tmdb_id) DESC, m.movie_id
               LIMIT  1) AS existing_id
       FROM   stg_movie_clean s) AS x
WINDOW grp         AS (PARTITION BY x.title, x.release_year),
       grp_ordered AS (PARTITION BY x.title, x.release_year ORDER BY x.ml_movie_id);

-- ---------------------------------------------------------------------
-- 4. genres: add the MovieLens genres that do not exist yet.
--    JSON_TABLE turns "Action|Sci-Fi" into one row per genre.
-- ---------------------------------------------------------------------
INSERT INTO genres (name)
SELECT DISTINCT jt.name
FROM   stg_movies s
CROSS JOIN JSON_TABLE(CONCAT('["', REPLACE(s.raw_genres, '|', '","'), '"]'),
                      '$[*]' COLUMNS (name VARCHAR(50) PATH '$')) AS jt
WHERE  jt.name <> '(no genres listed)'
  AND  NOT EXISTS (SELECT 1 FROM genres g WHERE g.name = jt.name)
ORDER  BY jt.name;

-- ---------------------------------------------------------------------
-- 5. movies: one row per new movie (runtime and poster_url stay NULL).
-- ---------------------------------------------------------------------
INSERT INTO movies (movie_id, title, release_year, tmdb_id)
SELECT target_id, title, release_year, tmdb_id
FROM   stg_movie_map
WHERE  is_new
ORDER  BY target_id;

-- ---------------------------------------------------------------------
-- 6. movie_genres: genres of every MovieLens movie, also for movies that
--    already existed (they may gain genres such as Adventure, Children).
-- ---------------------------------------------------------------------
INSERT INTO movie_genres (movie_id, genre_id)
SELECT DISTINCT mm.target_id, g.genre_id
FROM   stg_movies s
JOIN   stg_movie_map mm ON mm.ml_movie_id = s.ml_movie_id
CROSS JOIN JSON_TABLE(CONCAT('["', REPLACE(s.raw_genres, '|', '","'), '"]'),
                      '$[*]' COLUMNS (name VARCHAR(50) PATH '$')) AS jt
JOIN   genres g ON g.name = jt.name
WHERE  NOT EXISTS (SELECT 1 FROM movie_genres x
                   WHERE  x.movie_id = mm.target_id AND x.genre_id = g.genre_id);

-- ---------------------------------------------------------------------
-- 7. users: one placeholder account per MovieLens rater. The password
--    hash '!' never matches any password, so nobody can log in as them.
--    The .invalid domain is reserved, so the e-mails can never be real.
-- ---------------------------------------------------------------------
INSERT INTO users (user_id, username, email, password_hash, role)
SELECT DISTINCT 1000 + ml_user_id,
       CONCAT('ml_user_', ml_user_id),
       CONCAT('ml_user_', ml_user_id, '@movielens.invalid'),
       '!',
       'user'
FROM   stg_ratings
ORDER  BY 1;

-- ---------------------------------------------------------------------
-- 8. ratings: timestamps are Unix seconds (UTC). When duplicates were
--    merged and a user rated both copies, keep the later rating.
-- ---------------------------------------------------------------------
INSERT INTO ratings (user_id, movie_id, score, rated_at)
SELECT user_id, movie_id, score, rated_at
FROM  (SELECT 1000 + r.ml_user_id     AS user_id,
              mm.target_id            AS movie_id,
              r.score,
              FROM_UNIXTIME(r.ts)     AS rated_at,
              ROW_NUMBER() OVER (PARTITION BY r.ml_user_id, mm.target_id
                                 ORDER BY r.ts DESC, r.ml_movie_id) AS rn
       FROM   stg_ratings r
       JOIN   stg_movie_map mm ON mm.ml_movie_id = r.ml_movie_id) AS x
WHERE  rn = 1;
