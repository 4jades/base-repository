CSV_PATH = "tests/perf/seed/perf_seed.csv"
SEED_DATA_ROWS = 10000000


# perf_result 테이블용 CSV 컬럼 정의
# 순서가 LOAD DATA 구문과 완전히 동일해야 한다
PERF_RESULT_COLUMNS = [
    ("category",  lambda i: f"cat{i % 10}"),
    ("status",    lambda i: f"status{i % 3}"),
    ("tag",       lambda i: f"tag{i % 5}"),
    ("group_no",  lambda i: i % 20),                 # int
    ("payload",   lambda i: f"row-{i}"),
    ("value",     lambda i: i),                      # int
    ("value2",    lambda i: i * 2),                  # int
    ("flag",      lambda i: 1 if i % 2 == 0 else 0), # int
    ("extra",     lambda i: f"extra-{i % 7}"),
]

# LOAD DATA 대상 테이블명
PERF_RESULT_TABLE = "perf_result"