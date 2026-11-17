# Recco — Movie Recommendation System

NYU CS-GY 6083 (Fall 2026) 팀 프로젝트 · Jonghyun Jeong, Seho Kim, Harry Song

Flask(Python 3.12) + MySQL 8.0 기반 영화 추천 웹 애플리케이션입니다.

---

## 개발 환경 구축

모든 팀원이 Docker로 같은 환경(MySQL 8.0, Python 3.12, 같은 라이브러리 버전)을 사용합니다.

### 1. 사전 준비

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) 설치 후 실행 (Windows / macOS / Linux 모두 가능)
- Git

### 2. 실행

```bash
git clone https://github.com/prosh828/nyu26-pdb-project.git
cd nyu26-pdb-project
docker compose -f env/docker-compose.yml up -d --build
```

> Docker 설정 파일은 `env/` 에 있으므로 **레포 루트에서** `-f env/docker-compose.yml` 을 붙여 실행합니다.
> 매번 붙이기 번거로우면 `export COMPOSE_FILE=env/docker-compose.yml` (Windows PowerShell: `$env:COMPOSE_FILE="env/docker-compose.yml"`) 후 `docker compose ...` 만 써도 됩니다.

이 명령 하나로 아래가 모두 자동으로 처리됩니다.

- MySQL 8.0 컨테이너 생성, `db/init/` 스키마(테이블 10개)와 샘플 데이터 적용
- Flask 앱 이미지 빌드 및 실행
- 데모 계정 생성 (비밀번호 = 아이디): `admin` (관리자), `alice`, `bob`, `carol`, `david`, `eve`, `frank`
  - 샘플 데이터가 없을 때(`02_sample_data.sql` 을 지운 경우)는 앱이 `env/.env` 의 `ADMIN_*` 값(기본 `admin` / `admin1234`)으로 관리자를 만듭니다.

처음에는 이미지 다운로드와 DB 초기화로 1~2분 정도 걸립니다. `docker compose -f env/docker-compose.yml ps` 에서 `recco-db` 가 `healthy` 이면 준비된 것입니다.

### 3. 접속

| 서비스 | 주소 | 비고 |
|---|---|---|
| Flask 앱 | http://localhost:5001 | `/health` 에서 DB 연결과 테이블 목록 확인 |
| Adminer (DB GUI) | http://localhost:8081 | 서버 `db`, 사용자 `recco`, 비밀번호 `reccopass`, DB `recco` |
| MySQL 직접 접속 | `localhost:3307` | DBeaver, MySQL Workbench 등 |

### 4. 설정 변경 (선택)

기본값으로 바로 동작하므로 보통은 필요 없습니다. 포트가 겹치거나 TMDB API 키를 넣어야 할 때만:

```bash
cp env/.env.example env/.env    # 바꾸고 싶은 값만 수정
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

# Part 2 테스트 쿼리 실행 (DB 를 새로 띄운 직후에, EXPECTED ERROR 3개는 의도된 것)
docker compose -f env/docker-compose.yml exec -T db mysql -urecco -preccopass --force -t recco < sql/04_test_queries.sql
```

## 팀 작업 규칙

- **스키마 변경**은 `db/init/` 의 SQL 파일로만 하고 커밋합니다. init 스크립트는 DB가 비어 있을 때만 실행되므로, 스키마가 바뀐 커밋을 pull 한 뒤에는 `docker compose -f env/docker-compose.yml down -v && docker compose -f env/docker-compose.yml up -d` 로 다시 적용합니다.
- 파일 이름 순서대로 실행되니 `03_views.sql` 처럼 번호를 붙여 추가합니다.
- `db/init/` 의 스키마·샘플 데이터와 `sql/` 의 쿼리는 `part2/sql/` 에서 복사해 온 것입니다. 이제부터는 루트 쪽 파일을 고치고, `part2/` 는 제출 당시 기록으로 그대로 둡니다.
- `app/` 코드는 컨테이너에 마운트되어 있어 저장하면 자동 리로드됩니다.
- MovieLens CSV는 `data/` 에 넣습니다 (git에는 올리지 않음, `data/README.md` 참고).
- 모든 시간은 UTC로 저장됩니다.

## 프로젝트 구조

```
.
├── env/                   # Docker 환경 설정
│   ├── docker-compose.yml # db / app / adminer 서비스 정의
│   └── .env.example       # 설정 덮어쓰기용 예시 (cp 해서 env/.env 로, 선택)
├── app/                   # Flask 애플리케이션
│   ├── Dockerfile
│   ├── requirements.txt
│   └── recco/
│       ├── __init__.py    # 앱 생성, 라우트, CLI 명령
│       ├── db.py          # PyMySQL 연결
│       └── templates/
├── db/init/               # 컨테이너 최초 실행 시 자동 적용되는 SQL
│   ├── 01_schema.sql      # 테이블 10개, 키, 제약 조건, 인덱스
│   └── 02_sample_data.sql # 샘플 데이터 (데모 계정 포함)
├── sql/                   # 직접 실행하는 SQL
│   ├── 03_queries.sql     # 앱이 보낼 11개 쿼리 (%(name)s 플레이스홀더, 참고용)
│   └── 04_test_queries.sql# 같은 쿼리를 실제 값으로 (테스트용)
├── data/                  # MovieLens CSV (git 제외)
└── part2/                 # Part 2 관계형 DB 설계 참고 자료 (다이어그램, 보고서, 제출본)
```

## 문제 해결

- **`port is already allocated`**: 해당 포트를 쓰는 프로그램이 있습니다. `env/.env` 에서 `DB_HOST_PORT`, `APP_HOST_PORT`, `ADMINER_HOST_PORT` 를 바꾸세요.
- **왜 5000이 아니라 5001?**: macOS는 AirPlay 수신 모드(ControlCenter)가 5000 포트를 사용합니다. 컨테이너 내부 포트는 그대로 5000이고, 호스트 쪽만 5001로 매핑합니다.
- **스키마를 고쳤는데 반영이 안 됨**: `docker compose -f env/docker-compose.yml down -v` 후 다시 올리세요.
- **`no configuration file provided`**: 레포 루트에서 `-f env/docker-compose.yml` 을 붙였는지 확인하세요.
- **앱이 계속 재시작됨**: `docker compose -f env/docker-compose.yml logs app` 으로 에러를 확인하세요.
