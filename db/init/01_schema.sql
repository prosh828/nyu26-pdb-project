-- Recco schema (draft, based on Project Proposal §8)
-- Runs once, automatically, the first time the db container starts with an empty volume.
-- To apply changes: docker compose down -v && docker compose up -d

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- ---------- Core entities ----------
CREATE TABLE users (
    user_id        INT AUTO_INCREMENT PRIMARY KEY,
    username       VARCHAR(50)  NOT NULL,
    email          VARCHAR(255) NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    role           VARCHAR(10)  NOT NULL DEFAULT 'user',
    created_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_users_email    UNIQUE (email),
    CONSTRAINT uq_users_username UNIQUE (username),
    CONSTRAINT ck_users_role     CHECK (role IN ('user', 'admin'))
) ENGINE=InnoDB;

CREATE TABLE genres (
    genre_id  INT AUTO_INCREMENT PRIMARY KEY,
    name      VARCHAR(50) NOT NULL,
    CONSTRAINT uq_genres_name UNIQUE (name)
) ENGINE=InnoDB;

CREATE TABLE movies (
    movie_id      INT AUTO_INCREMENT PRIMARY KEY,   -- MovieLens movieId 그대로 넣어도 됨
    title         VARCHAR(255) NOT NULL,
    release_year  SMALLINT     NULL,
    runtime       SMALLINT     NULL,
    tmdb_id       INT          NULL,
    imdb_id       VARCHAR(16)  NULL,
    poster_url    VARCHAR(500) NULL,
    CONSTRAINT uq_movies_title_year UNIQUE (title, release_year),
    CONSTRAINT uq_movies_tmdb       UNIQUE (tmdb_id),
    CONSTRAINT ck_movies_runtime    CHECK (runtime > 0)
) ENGINE=InnoDB;

-- ---------- N:M links to genres ----------
CREATE TABLE movie_genres (
    movie_id  INT NOT NULL,
    genre_id  INT NOT NULL,
    PRIMARY KEY (movie_id, genre_id),
    KEY idx_mg_genre (genre_id),
    CONSTRAINT fk_mg_movie FOREIGN KEY (movie_id) REFERENCES movies(movie_id) ON DELETE CASCADE,
    -- 제안서 Key decisions: 영화에 연결된 장르 삭제는 RESTRICT
    CONSTRAINT fk_mg_genre FOREIGN KEY (genre_id) REFERENCES genres(genre_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE user_genres (
    user_id   INT NOT NULL,
    genre_id  INT NOT NULL,
    PRIMARY KEY (user_id, genre_id),
    CONSTRAINT fk_ug_user  FOREIGN KEY (user_id)  REFERENCES users(user_id)   ON DELETE CASCADE,
    CONSTRAINT fk_ug_genre FOREIGN KEY (genre_id) REFERENCES genres(genre_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------- User–movie interactions ----------
CREATE TABLE ratings (
    user_id   INT NOT NULL,
    movie_id  INT NOT NULL,
    score     DECIMAL(2,1) NOT NULL,
    review    TEXT NULL,
    rated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, movie_id),
    KEY idx_ratings_movie_score (movie_id, score),
    CONSTRAINT ck_ratings_score CHECK (score BETWEEN 0.5 AND 5.0 AND score * 2 = FLOOR(score * 2)),
    CONSTRAINT fk_r_user  FOREIGN KEY (user_id)  REFERENCES users(user_id)   ON DELETE CASCADE,
    CONSTRAINT fk_r_movie FOREIGN KEY (movie_id) REFERENCES movies(movie_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE view_events (
    event_id   BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    movie_id   INT NOT NULL,
    progress   TINYINT UNSIGNED NOT NULL,
    viewed_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ve_user_time  (user_id, viewed_at),
    KEY idx_ve_time_movie (viewed_at, movie_id),     -- trending (최근 7일)
    CONSTRAINT ck_ve_progress CHECK (progress BETWEEN 0 AND 100),
    CONSTRAINT fk_ve_user  FOREIGN KEY (user_id)  REFERENCES users(user_id)   ON DELETE CASCADE,
    CONSTRAINT fk_ve_movie FOREIGN KEY (movie_id) REFERENCES movies(movie_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE watchlist (
    user_id   INT NOT NULL,
    movie_id  INT NOT NULL,
    added_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, movie_id),
    CONSTRAINT fk_w_user  FOREIGN KEY (user_id)  REFERENCES users(user_id)   ON DELETE CASCADE,
    CONSTRAINT fk_w_movie FOREIGN KEY (movie_id) REFERENCES movies(movie_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE hidden_movies (
    user_id    INT NOT NULL,
    movie_id   INT NOT NULL,
    hidden_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, movie_id),
    CONSTRAINT fk_h_user  FOREIGN KEY (user_id)  REFERENCES users(user_id)   ON DELETE CASCADE,
    CONSTRAINT fk_h_movie FOREIGN KEY (movie_id) REFERENCES movies(movie_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------- Stored ranked recommendation lists ----------
CREATE TABLE recommendations (
    rec_id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id        INT NOT NULL,
    strategy       VARCHAR(10) NOT NULL,
    seed_movie_id  INT NULL,                          -- "Because you liked X" 의 X
    movie_id       INT NOT NULL,
    rec_rank       INT NOT NULL,                      -- RANK 는 MySQL 8 예약어라 rec_rank 사용
    score          DECIMAL(10,4) NULL,
    generated_at   TIMESTAMP NOT NULL,
    shown_at       TIMESTAMP NULL,
    -- NULL seed 도 UNIQUE 로 보호하기 위한 생성 컬럼.
    -- seed_movie_id 의 FK 가 CASCADE 라서 STORED 는 불가 → VIRTUAL 사용
    seed_key       INT AS (COALESCE(seed_movie_id, 0)) VIRTUAL,
    CONSTRAINT uq_rec_list_rank  UNIQUE (user_id, strategy, seed_key, generated_at, rec_rank),
    CONSTRAINT uq_rec_list_movie UNIQUE (user_id, strategy, seed_key, generated_at, movie_id),
    KEY idx_rec_user_shown (user_id, shown_at),
    CONSTRAINT ck_rec_strategy CHECK (strategy IN ('popular', 'genre', 'item_cf')),
    CONSTRAINT ck_rec_rank     CHECK (rec_rank >= 1),
    CONSTRAINT fk_rec_user  FOREIGN KEY (user_id)       REFERENCES users(user_id)   ON DELETE CASCADE,
    CONSTRAINT fk_rec_movie FOREIGN KEY (movie_id)      REFERENCES movies(movie_id) ON DELETE CASCADE,
    CONSTRAINT fk_rec_seed  FOREIGN KEY (seed_movie_id) REFERENCES movies(movie_id) ON DELETE CASCADE
) ENGINE=InnoDB;
