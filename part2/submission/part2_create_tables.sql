-- =====================================================================
-- Recco — Part 2, requirement 2: CREATE TABLE statements (MySQL 8.0)
-- Creates the 10 tables, their keys, constraints and indexes.
-- Safe to re-run: existing tables are dropped first.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS recco
    CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE recco;

-- All TIMESTAMP values are read and written in UTC.
SET time_zone = '+00:00';

-- Drop in reverse dependency order (children first).
DROP TABLE IF EXISTS recommendations;
DROP TABLE IF EXISTS hidden_movies;
DROP TABLE IF EXISTS watchlist;
DROP TABLE IF EXISTS view_events;
DROP TABLE IF EXISTS ratings;
DROP TABLE IF EXISTS user_genres;
DROP TABLE IF EXISTS movie_genres;
DROP TABLE IF EXISTS movies;
DROP TABLE IF EXISTS genres;
DROP TABLE IF EXISTS users;

-- ---------------------------------------------------------------------
-- 1. users — regular users and administrators share one table
-- ---------------------------------------------------------------------
CREATE TABLE users (
    user_id        INT           NOT NULL AUTO_INCREMENT,
    username       VARCHAR(50)   NOT NULL,
    email          VARCHAR(254)  NOT NULL,
    password_hash  VARCHAR(255)  NOT NULL,
    role           VARCHAR(10)   NOT NULL DEFAULT 'user',
    PRIMARY KEY (user_id),
    CONSTRAINT users_username_uq UNIQUE (username),
    CONSTRAINT users_email_uq    UNIQUE (email),
    CONSTRAINT users_role_chk    CHECK (role IN ('user', 'admin')),
    CONSTRAINT users_email_chk   CHECK (email LIKE '%_@_%._%')
);

-- ---------------------------------------------------------------------
-- 2. genres
-- ---------------------------------------------------------------------
CREATE TABLE genres (
    genre_id  INT          NOT NULL AUTO_INCREMENT,
    name      VARCHAR(50)  NOT NULL,
    PRIMARY KEY (genre_id),
    CONSTRAINT genres_name_uq UNIQUE (name)
);

-- ---------------------------------------------------------------------
-- 3. movies — release_year and runtime are optional because some
--    MovieLens titles have no year and MovieLens has no runtimes.
-- ---------------------------------------------------------------------
CREATE TABLE movies (
    movie_id      INT           NOT NULL AUTO_INCREMENT,
    title         VARCHAR(255)  NOT NULL,
    release_year  SMALLINT      NULL,
    runtime       SMALLINT      NULL,                 -- minutes
    tmdb_id       INT           NULL,                 -- from MovieLens links.csv
    poster_url    VARCHAR(500)  NULL,                 -- filled from the TMDB API
    PRIMARY KEY (movie_id),
    CONSTRAINT movies_title_year_uq UNIQUE (title, release_year),
    CONSTRAINT movies_tmdb_uq       UNIQUE (tmdb_id),
    CONSTRAINT movies_year_chk      CHECK (release_year BETWEEN 1870 AND 2100),
    CONSTRAINT movies_runtime_chk   CHECK (runtime > 0)
);

-- ---------------------------------------------------------------------
-- 4. movie_genres — N:M between movies and genres (has_genre)
-- ---------------------------------------------------------------------
CREATE TABLE movie_genres (
    movie_id  INT NOT NULL,
    genre_id  INT NOT NULL,
    PRIMARY KEY (movie_id, genre_id),
    INDEX mg_genre_idx (genre_id),
    CONSTRAINT mg_movie_fk FOREIGN KEY (movie_id) REFERENCES movies (movie_id)
        ON DELETE CASCADE,
    -- A genre still used by a movie cannot be deleted.
    CONSTRAINT mg_genre_fk FOREIGN KEY (genre_id) REFERENCES genres (genre_id)
        ON DELETE RESTRICT
);

-- ---------------------------------------------------------------------
-- 5. user_genres — favourite genres picked at sign-up (prefers)
-- ---------------------------------------------------------------------
CREATE TABLE user_genres (
    user_id   INT NOT NULL,
    genre_id  INT NOT NULL,
    PRIMARY KEY (user_id, genre_id),
    INDEX ug_genre_idx (genre_id),
    CONSTRAINT ug_user_fk  FOREIGN KEY (user_id)  REFERENCES users (user_id)
        ON DELETE CASCADE,
    CONSTRAINT ug_genre_fk FOREIGN KEY (genre_id) REFERENCES genres (genre_id)
        ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- 6. ratings — one current rating per (user, movie) (rates)
--    Half-star scale: 0.5, 1.0, ..., 5.0
-- ---------------------------------------------------------------------
CREATE TABLE ratings (
    user_id   INT           NOT NULL,
    movie_id  INT           NOT NULL,
    score     DECIMAL(2,1)  NOT NULL,
    review    TEXT          NULL,
    rated_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, movie_id),
    INDEX ratings_movie_score_idx (movie_id, score),
    CONSTRAINT ratings_score_chk
        CHECK (score BETWEEN 0.5 AND 5.0 AND score * 2 = FLOOR(score * 2)),
    CONSTRAINT ratings_user_fk  FOREIGN KEY (user_id)  REFERENCES users (user_id)
        ON DELETE CASCADE,
    CONSTRAINT ratings_movie_fk FOREIGN KEY (movie_id) REFERENCES movies (movie_id)
        ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- 7. view_events — append-only viewing log (viewed_by, event_of)
--    progress >= 90 means the movie counts as finished.
-- ---------------------------------------------------------------------
CREATE TABLE view_events (
    event_id   BIGINT    NOT NULL AUTO_INCREMENT,
    user_id    INT       NOT NULL,
    movie_id   INT       NOT NULL,
    progress   TINYINT   NOT NULL,
    viewed_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id),
    INDEX ve_user_time_idx  (user_id, viewed_at),
    INDEX ve_movie_time_idx (movie_id, viewed_at),
    CONSTRAINT ve_progress_chk CHECK (progress BETWEEN 0 AND 100),
    CONSTRAINT ve_user_fk  FOREIGN KEY (user_id)  REFERENCES users (user_id)
        ON DELETE CASCADE,
    CONSTRAINT ve_movie_fk FOREIGN KEY (movie_id) REFERENCES movies (movie_id)
        ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- 8. watchlist (watchlist)
-- ---------------------------------------------------------------------
CREATE TABLE watchlist (
    user_id   INT       NOT NULL,
    movie_id  INT       NOT NULL,
    added_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, movie_id),
    INDEX wl_movie_idx (movie_id),
    CONSTRAINT wl_user_fk  FOREIGN KEY (user_id)  REFERENCES users (user_id)
        ON DELETE CASCADE,
    CONSTRAINT wl_movie_fk FOREIGN KEY (movie_id) REFERENCES movies (movie_id)
        ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- 9. hidden_movies — "not interested" (hides)
-- ---------------------------------------------------------------------
CREATE TABLE hidden_movies (
    user_id    INT       NOT NULL,
    movie_id   INT       NOT NULL,
    hidden_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, movie_id),
    INDEX hm_movie_idx (movie_id),
    CONSTRAINT hm_user_fk  FOREIGN KEY (user_id)  REFERENCES users (user_id)
        ON DELETE CASCADE,
    CONSTRAINT hm_movie_fk FOREIGN KEY (movie_id) REFERENCES movies (movie_id)
        ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- 10. recommendations — one row per movie in a stored, ranked list
--     (rec_for, rec_movie, based_on).
--     A list = (user_id, strategy, seed_movie_id, generated_at).
--     seed_movie_id is set only for 'item_cf' ("Because you liked X").
--     seed_key turns NULL into 0, because MySQL treats NULLs as
--     distinct in UNIQUE indexes; without it, lists that have no
--     seed movie could hold two rows with the same rank.
-- ---------------------------------------------------------------------
CREATE TABLE recommendations (
    rec_id         BIGINT        NOT NULL AUTO_INCREMENT,
    user_id        INT           NOT NULL,
    movie_id       INT           NOT NULL,
    strategy       VARCHAR(10)   NOT NULL,
    seed_movie_id  INT           NULL,
    rec_rank       SMALLINT      NOT NULL,
    score          DECIMAL(7,3)  NOT NULL,
    generated_at   TIMESTAMP     NOT NULL,
    shown_at       TIMESTAMP     NULL,
    seed_key       INT AS (COALESCE(seed_movie_id, 0)) VIRTUAL,
    PRIMARY KEY (rec_id),
    CONSTRAINT rec_list_rank_uq
        UNIQUE (user_id, strategy, seed_key, generated_at, rec_rank),
    CONSTRAINT rec_list_movie_uq
        UNIQUE (user_id, strategy, seed_key, generated_at, movie_id),
    INDEX rec_user_shown_idx (user_id, shown_at),
    INDEX rec_movie_idx (movie_id),
    INDEX rec_seed_idx (seed_movie_id),
    CONSTRAINT rec_strategy_chk CHECK (strategy IN ('popular', 'genre', 'item_cf')),
    CONSTRAINT rec_rank_chk     CHECK (rec_rank >= 1),
    CONSTRAINT rec_user_fk  FOREIGN KEY (user_id)  REFERENCES users (user_id)
        ON DELETE CASCADE,
    CONSTRAINT rec_movie_fk FOREIGN KEY (movie_id) REFERENCES movies (movie_id)
        ON DELETE CASCADE,
    -- A "Because you liked X" list is meaningless without X.
    CONSTRAINT rec_seed_fk  FOREIGN KEY (seed_movie_id) REFERENCES movies (movie_id)
        ON DELETE CASCADE
);
