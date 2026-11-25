# Recco — Movie Recommendation System

NYU CS-GY 6083 (Fall 2026) 팀 프로젝트 · Jonghyun Jeong, Seho Kim, Harry Song

Flask(Python 3.12) + MySQL 8.0 기반 영화 추천 웹 애플리케이션입니다.

> 🤖 **AI 에이전트(Claude Code, Codex, Cursor 등)를 쓰는 경우**
> 프로젝트 설정·스키마·규칙·실행/검증 방법을 [`AGENTS.md`](AGENTS.md) 에 정리해 두었습니다.
> 에이전트가 작업 전에 이 파일을 읽도록 되어 있습니다 (Claude Code 는 [`CLAUDE.md`](CLAUDE.md) 가 `AGENTS.md` 를 불러옵니다).
> 설정이나 규칙이 바뀌면 **`AGENTS.md` 도 같은 커밋에서 함께 수정**해 주세요. 개인용 메모는 `CLAUDE.local.md` 에 (git 제외).

---

## 개발 환경 구축

모든 팀원이 Docker로 같은 환경(MySQL 8.0, Python 3.12, 같은 라이브러리 버전)을 사용합니다.

### 1. 사전 준비

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) 설치 후 실행 (Windows / macOS / Linux 모두 가능)
- Git

### 2. 실행 전 설정 (env)

```bash
git clone https://github.com/prosh828/nyu26-pdb-project.git
cd nyu26-pdb-project
cp env/.env.example env/.env        # Windows: copy env\.env.example env\.env
```

`env/.env` 를 열어 **`TMDB_API_KEY=` 에 TMDB API 키를 넣습니다** (영화 포스터용).

1. https://www.themoviedb.org 가입 → [Settings → API](https://www.themoviedb.org/settings/api) 에서 API 키 발급 (무료, 비상업용)
2. **API Key** (32자, v3) 값을 복사해서 `TMDB_API_KEY=` 뒤에 붙여 넣기

- 키가 없어도 실행은 되지만, 포스터 없이 동작합니다. 나중에 키를 넣고 `docker compose -f env/docker-compose.yml run --rm posters` 로 채울 수 있습니다.
- `env/.env` 는 git 에 올라가지 않습니다 (.gitignore). **키를 커밋하거나 채팅·PR 에 붙여 넣지 마세요.**
- 다른 값(포트, 비밀번호 등)은 기본값 그대로 두면 됩니다.

### 3. 실행

```bash
docker compose -f env/docker-compose.yml up -d --build
```

> Docker 설정 파일은 `env/` 에 있으므로 **레포 루트에서** `-f env/docker-compose.yml` 을 붙여 실행합니다.
> 매번 붙이기 번거로우면 `export COMPOSE_FILE=env/docker-compose.yml` (Windows PowerShell: `$env:COMPOSE_FILE="env/docker-compose.yml"`) 후 `docker compose ...` 만 써도 됩니다.

이 명령 하나로 아래가 모두 자동으로 처리됩니다.

- MySQL 8.0 컨테이너 생성, `db/init/` 스키마(테이블 10개)와 샘플 데이터 적용
- **MovieLens `ml-latest-small` 자동 다운로드 및 import** (`loader` 컨테이너, 처음 한 번만, 약 10초)
- Flask 앱 이미지 빌드 및 실행 (import 가 끝난 뒤 시작)
- **TMDB 포스터 URL 채우기** (`posters` 컨테이너, 백그라운드, 처음 한 번 약 4~5분). 앱은 기다리지 않고 바로 뜨며, 포스터는 채워지는 대로 생깁니다. 진행 상황: `docker compose -f env/docker-compose.yml logs -f posters`
- 데모 계정 생성 (비밀번호 = 아이디): `admin` (관리자), `alice`, `bob`, `carol`, `david`, `eve`, `frank`
  - 샘플 데이터가 없을 때(`02_sample_data.sql` 을 지운 경우)는 앱이 `env/.env` 의 `ADMIN_*` 값(기본 `admin` / `admin1234`)으로 관리자를 만듭니다.

처음에는 이미지 다운로드와 DB 초기화로 1~2분 정도 걸립니다. 인터넷이 안 되면 MovieLens 없이 샘플 데이터만으로 앱이 뜨고, 나중에 `docker compose -f env/docker-compose.yml run --rm loader` 로 다시 넣을 수 있습니다. `docker compose -f env/docker-compose.yml ps` 에서 `recco-db` 가 `healthy` 이면 준비된 것입니다.

### 4. 접속

| 서비스 | 주소 | 비고 |
|---|---|---|
| Flask 앱 | http://localhost:5001 | `/health` 에서 DB 연결과 테이블 목록 확인 |
| Adminer (DB GUI) | http://localhost:8081 | 서버 `db`, 사용자 `recco`, 비밀번호 `reccopass`, DB `recco` |
| MySQL 직접 접속 | `localhost:3307` | DBeaver, MySQL Workbench 등 |

### 5. 들어가는 데이터

| | 샘플 데이터 (`db/init/02_sample_data.sql`) | MovieLens (`db/import/movielens.sql`) |
|---|---|---|
| 영화 | 20편 (`movie_id` 1~20) | 약 9,700편 (`movie_id` = MovieLens movieId + 1000) |
| 사용자 | 데모 계정 7명 (`user_id` 1~7) | 평점을 남긴 610명 (`ml_user_N`, `user_id` = userId + 1000, **로그인 불가**) |
| 평점 | 56개 | 약 10만 개 (1996~2018) |

- 샘플 영화 20편 중 19편은 MovieLens 에도 있어서 같은 영화로 합쳐집니다 (`tmdb_id` 로 매칭, 장르는 MovieLens 것이 추가됨).
- 제목은 `Matrix, The (1999)` → 제목 `The Matrix` + 연도 `1999` 로 나눠 저장합니다. 제목·연도가 같은 중복 영화 5쌍은 하나로 합칩니다.
- `poster_url` 과 비어 있는 `runtime` 은 TMDB 에서 채웁니다 (이미지 파일은 저장하지 않고 `https://image.tmdb.org/...` URL 만 저장). TMDB 에 없는 영화는 비어 있습니다.
- 포스터를 화면에 쓸 때는 TMDB 이용 조건에 따라 "This product uses the TMDB API but is not endorsed or certified by TMDB." 문구를 사이트에 표시해야 합니다.
- **샘플 데이터만 쓰고 싶을 때** (예: `sql/04_test_queries.sql` 결과를 Part 2 와 비교): `env/.env` 에 `LOAD_MOVIELENS=false` 를 넣고 `docker compose -f env/docker-compose.yml down -v && docker compose -f env/docker-compose.yml up -d`.

### 6. 설정 변경 (선택)

`env/.env` 값을 바꾼 뒤에는 컨테이너를 다시 만들어야 반영됩니다:

```bash
docker compose -f env/docker-compose.yml up -d
```

---

## 자주 쓰는 명령

```bash
docker compose -f env/docker-compose.yml ps                 # 상태 확인
docker compose -f env/docker-compose.yml logs -f app        # 앱 로그 보기
docker compose -f env/docker-compose.yml exec db mysql -urecco -preccopass recco   # MySQL 콘솔
docker compose -f env/docker-compose.yml down               # 중지 (데이터 유지)
docker compose -f env/docker-compose.yml down -v            # 중지 + DB 완전 초기화
docker compose -f env/docker-compose.yml up -d --build      # requirements.txt 변경 후 재빌드

# MovieLens import 다시 실행 (이미 들어 있으면 건너뜀)
docker compose -f env/docker-compose.yml run --rm loader

# 포스터 URL 채우기 다시 실행 (비어 있는 영화만 조회)
docker compose -f env/docker-compose.yml run --rm posters

# Part 2 테스트 쿼리 실행 (LOAD_MOVIELENS=false 로 새로 띄운 DB 에서, EXPECTED ERROR 3개는 의도된 것)
docker compose -f env/docker-compose.yml exec -T db mysql -urecco -preccopass --force -t recco < sql/04_test_queries.sql
```

## 팀 작업 규칙

- **스키마 변경**은 `db/init/` 의 SQL 파일로만 하고 커밋합니다. init 스크립트는 DB가 비어 있을 때만 실행되므로, 스키마가 바뀐 커밋을 pull 한 뒤에는 `docker compose -f env/docker-compose.yml down -v && docker compose -f env/docker-compose.yml up -d` 로 다시 적용합니다.
- 파일 이름 순서대로 실행되니 `03_views.sql` 처럼 번호를 붙여 추가합니다.
- `db/init/` 의 스키마·샘플 데이터와 `sql/` 의 쿼리는 `part2/sql/` 에서 복사해 온 것입니다. 이제부터는 루트 쪽 파일을 고치고, `part2/` 는 제출 당시 기록으로 그대로 둡니다.
- `app/` 코드는 컨테이너에 마운트되어 있어 저장하면 자동 리로드됩니다.
- MovieLens 는 자동으로 내려받습니다 (Docker 볼륨에 보관, git 에는 올리지 않음). 직접 받은 CSV 를 쓰려면 `data/ml-latest-small/` 에 넣으세요 (`data/README.md` 참고).
- import 규칙(제목 정리, 중복 병합, ID 매핑)을 바꾸려면 `db/import/movielens.sql` 을 고친 뒤 `down -v` 로 다시 띄웁니다.
- 모든 시간은 UTC로 저장됩니다.

## 프로젝트 구조

```
.
├── AGENTS.md              # AI 에이전트용 프로젝트 컨텍스트 (CLAUDE.md 가 불러옴)
├── CLAUDE.md
├── env/                   # Docker 환경 설정
│   ├── docker-compose.yml # db / app / adminer 서비스 정의
│   └── .env.example       # 설정 덮어쓰기용 예시 (cp 해서 env/.env 로, 선택)
├── app/                   # Flask 애플리케이션
│   ├── Dockerfile
│   ├── requirements.txt
│   └── recco/
│       ├── __init__.py    # 앱 생성, 라우트, CLI 명령
│       ├── db.py          # PyMySQL 연결
│       ├── movielens.py   # MovieLens 다운로드·import (`flask import-movielens`)
│       ├── tmdb.py        # TMDB 포스터 URL 채우기 (`flask fetch-posters`)
│       └── templates/
├── db/init/               # 컨테이너 최초 실행 시 자동 적용되는 SQL
│   ├── 01_schema.sql      # 테이블 10개, 키, 제약 조건, 인덱스
│   └── 02_sample_data.sql # 샘플 데이터 (데모 계정 포함)
├── sql/                   # 직접 실행하는 SQL
│   ├── 03_queries.sql     # 앱이 보낼 11개 쿼리 (%(name)s 플레이스홀더, 참고용)
│   └── 04_test_queries.sql# 같은 쿼리를 실제 값으로 (테스트용)
├── db/import/
│   └── movielens.sql      # MovieLens CSV → 테이블 (loader 컨테이너가 실행)
├── data/                  # 직접 받은 MovieLens CSV 를 둘 곳 (선택, git 제외)
└── part2/                 # Part 2 관계형 DB 설계 참고 자료 (다이어그램, 보고서, 제출본)
```

## 문제 해결

- **`port is already allocated`**: 해당 포트를 쓰는 프로그램이 있습니다. `env/.env` 에서 `DB_HOST_PORT`, `APP_HOST_PORT`, `ADMINER_HOST_PORT` 를 바꾸세요.
- **왜 5000이 아니라 5001?**: macOS는 AirPlay 수신 모드(ControlCenter)가 5000 포트를 사용합니다. 컨테이너 내부 포트는 그대로 5000이고, 호스트 쪽만 5001로 매핑합니다.
- **스키마를 고쳤는데 반영이 안 됨**: `docker compose -f env/docker-compose.yml down -v` 후 다시 올리세요.
- **`no configuration file provided`**: 레포 루트에서 `-f env/docker-compose.yml` 을 붙였는지 확인하세요.
- **앱이 계속 재시작됨**: `docker compose -f env/docker-compose.yml logs app` 으로 에러를 확인하세요.

## DB 백업

컨테이너가 실행 중일 때 레포 루트에서:

    bash db/backup.sh

`db/backup/recco_<날짜_시간>.sql` 이 생성됩니다 (git 에는 올라가지 않음).
복원: `docker compose -f env/docker-compose.yml exec -T db sh -c 'mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' < db/backup/<파일>.sql`
