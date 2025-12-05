from __future__ import annotations

import csv
import os
import sqlite3
from typing import Sequence

from tests.perf.db_config import PerfDBKind, get_perf_engine, get_perf_settings
from tests.perf.seed.config import CSV_PATH, PERF_RESULT_COLUMNS, PERF_RESULT_TABLE


BATCH = 200_000


async def bulk_seed_load() -> None:
    """
    < 선택된 perf DB 종류에 맞게 CSV 시드를 로딩합니다 >
    1. get_perf_settings()로 현재 DB 종류를 확인합니다.
    2. mysql이면 LOAD DATA INFILE로 로딩합니다.
    3. postgres이면 COPY FROM으로 로딩합니다.
    4. sqlite이면 로컬에서 CSV를 읽고 executemany로 insert 합니다.
    """
    settings = get_perf_settings()

    if settings.kind == PerfDBKind.MYSQL:
        await _bulk_seed_load_mysql()
        return

    if settings.kind == PerfDBKind.POSTGRES:
        await _bulk_seed_load_postgres()
        return

    if settings.kind == PerfDBKind.SQLITE:
        _bulk_seed_load_sqlite(settings.dsn)
        return

    raise RuntimeError(f"Unsupported perf DB kind: {settings.kind}")



async def _bulk_seed_load_mysql() -> None:
    """
    < MySQL: LOAD DATA INFILE 로 CSV를 로딩합니다 >
    1. MySQL 컨테이너 내부 경로(/var/lib/mysql-files/perf_seed.csv)를 사용합니다.
    2. 컬럼 순서는 PERF_RESULT_COLUMNS 순서와 일치해야 합니다.
    """
    engine = get_perf_engine()

    column_names = ", ".join(name for name, _ in PERF_RESULT_COLUMNS)

    query = f"""
        LOAD DATA INFILE '/var/lib/mysql-files/perf_seed.csv'
        INTO TABLE {PERF_RESULT_TABLE}
        FIELDS TERMINATED BY ','
        ({column_names});
    """

    async with engine.begin() as conn:
        await conn.exec_driver_sql(query)



async def _bulk_seed_load_postgres() -> None:
    """
    < Postgres: COPY FROM 로 CSV를 로딩합니다 >
    1. Postgres 컨테이너에 seed dir을 /var/lib/postgresql-files 로 마운트해야 합니다.
    2. COPY는 서버가 파일을 직접 읽습니다.
    3. 파일 지정 COPY는 superuser 권한이 필요합니다(테스트 컨테이너에서는 통상 OK).
    """
    engine = get_perf_engine()

    column_names = ", ".join(name for name, _ in PERF_RESULT_COLUMNS)

    query = f"""
        COPY {PERF_RESULT_TABLE} ({column_names})
        FROM '/var/lib/postgresql-files/perf_seed.csv'
        WITH (FORMAT csv, DELIMITER ',', HEADER false);
    """

    async with engine.begin() as conn:
        await conn.exec_driver_sql(query)



def _bulk_seed_load_sqlite(dsn: str) -> None:
    """
    < SQLite: CSV를 읽어 executemany로 insert 합니다 >
    1. sqlite+aiosqlite:///... 형태의 DSN에서 파일 경로를 추출합니다.
    2. CSV_PATH를 읽어서 BATCH 단위로 executemany 합니다.
    3. 트랜잭션을 한 번만 열고 commit 합니다.
    """
    db_path = _sqlite_path_from_dsn(dsn)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    col_names = [name for name, _ in PERF_RESULT_COLUMNS]
    placeholders = ", ".join(["?"] * len(col_names))
    insert_sql = f"INSERT INTO {PERF_RESULT_TABLE} ({', '.join(col_names)}) VALUES ({placeholders})"

    con = sqlite3.connect(db_path)
    try:
        con.execute("BEGIN")

        with open(CSV_PATH, newline="") as f:
            reader = csv.reader(f)

            buf: list[Sequence[str]] = []
            for row in reader:
                buf.append(row)
                if len(buf) >= BATCH:
                    con.executemany(insert_sql, buf)
                    buf.clear()

            if buf:
                con.executemany(insert_sql, buf)

        con.commit()
    finally:
        con.close()



def _sqlite_path_from_dsn(dsn: str) -> str:
    """
    < sqlite DSN에서 파일 경로를 뽑아냅니다 >
    1. sqlite+aiosqlite:///abs/path.db 형태를 지원합니다.
    2. sqlite+aiosqlite:///<rel/path.db> 형태도 그대로 반환합니다.
    """
    prefix = "sqlite+aiosqlite:///"
    if not dsn.startswith(prefix):
        raise ValueError(f"Unexpected sqlite dsn: {dsn}")

    return dsn[len(prefix):]
