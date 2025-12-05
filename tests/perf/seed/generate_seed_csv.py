import os

from tests.perf.seed.config import CSV_PATH, PERF_RESULT_COLUMNS, SEED_DATA_ROWS

BATCH = 200_000
def ensure_seed_csv() -> str:
    if os.path.exists(CSV_PATH):
        print(f"[seed] CSV already exists: {CSV_PATH}")
        return CSV_PATH

    print("[seed] generating CSV...")
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)

    buffer_size = 16 * 1024 * 1024

    with open(CSV_PATH, "w", buffering=buffer_size) as f:
        for start in range(1, SEED_DATA_ROWS, BATCH):
            end = min(start + BATCH, SEED_DATA_ROWS)
            for i in range(start, end):
                row = ",".join(str(col_fn(i)) for _, col_fn in PERF_RESULT_COLUMNS)
                f.write(row + "\n")

    print("[seed] CSV generated:", CSV_PATH)
    return CSV_PATH