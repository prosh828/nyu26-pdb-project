MovieLens `ml-latest-small` CSV(movies.csv, ratings.csv, links.csv, tags.csv)를 이 폴더에 넣으세요.
https://grouplens.org/datasets/movielens/latest/

- 앱 컨테이너에서는 `/data/` 경로로 보입니다 (Python으로 import 할 때).
- DB 컨테이너에서도 `/data/` 경로로 보입니다. `LOAD DATA LOCAL INFILE` 로 읽으세요:
  `docker compose exec db mysql --local-infile=1 -urecco -preccopass recco`
  → `LOAD DATA LOCAL INFILE '/data/movies.csv' INTO TABLE ...`
- 이 폴더의 CSV는 git에 올리지 않습니다 (.gitignore).
