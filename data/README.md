MovieLens `ml-latest-small` 은 **자동으로** 내려받아 DB 에 들어갑니다 (`loader` 서비스, README 참고).
이 폴더는 비워 둬도 됩니다.

직접 받은 CSV 를 쓰고 싶을 때만 (예: 오프라인 환경) 아래처럼 넣으세요. 다운로드 대신 이 파일을 사용합니다.

```
data/ml-latest-small/movies.csv
data/ml-latest-small/links.csv
data/ml-latest-small/ratings.csv
```

https://grouplens.org/datasets/movielens/latest/ (ml-latest-small.zip)

- 컨테이너 안에서는 `/data/` 경로로 보입니다 (`app`, `loader`, `db` 모두, 읽기 전용).
- DB 에서 직접 CSV 를 읽을 때는 `LOAD DATA LOCAL INFILE` 을 사용합니다:
  `docker compose -f env/docker-compose.yml exec db mysql --local-infile=1 -urecco -preccopass recco`
  → `LOAD DATA LOCAL INFILE '/data/ml-latest-small/movies.csv' INTO TABLE ...`
- 이 폴더의 CSV 는 git 에 올리지 않습니다 (.gitignore). MovieLens 라이선스상 상업적 이용은 금지입니다.
