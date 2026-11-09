# Recco — Part 2: Relational Database Design

CS-GY 6083 · Team: Jonghyun Jeong (jj4335), Seho Kim (sk13811), Harry Song (cs8293)

## Contents

```
part2/
├── sql/
│   ├── 01_schema.sql        # DDL: 10 tables, keys, constraints, indexes
│   ├── 02_sample_data.sql   # Hand-crafted sample data
│   ├── 03_queries.sql       # 11 queries as the app sends them (%(name)s placeholders)
│   └── 04_test_queries.sql  # Same queries with concrete values
├── results/
│   ├── sample_data_load.txt # Row counts after loading the sample data
│   └── test_results.txt     # Full output of 04_test_queries.sql
├── diagrams/                # ER diagram, relational schema (textbook + crow's foot): draw.io + PNG
└── report/                  # report.md and Recco_Part2_Report.pdf
```

## Run it (MySQL 8.0)

```bash
mysql -u root -p < sql/01_schema.sql
mysql -u root -p < sql/02_sample_data.sql
mysql -u root -p --force < sql/04_test_queries.sql
```

`--force` keeps going past the three statements marked **EXPECTED ERROR**
(they prove the UNIQUE and CHECK constraints work). In MySQL Workbench,
turn on *Query → Continue on SQL Script Error* instead.

Run 04 on a **fresh** load: it inserts rows (a new user, a stored list, a new
movie), so running it twice gives duplicate-key errors on purpose.

All times are relative to `NOW()`, so results match the report whenever you run it.

## Demo accounts

Password = username: `admin` (admin), `alice`, `bob`, `carol`, `david`, `eve`, `frank` (brand-new user).
