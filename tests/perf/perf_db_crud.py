from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Any, Awaitable, Callable, Mapping, Protocol, cast

from collections.abc import Sequence
import statistics
import time

from pydantic import BaseModel, ConfigDict
import pytest
from sqlalchemy import (
    Integer,
    String,
    Table,
    column,
    delete,
    func,
    select,
)
from sqlalchemy import func as sa_func
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from sqlmodel import SQLModel, Field, select as sqlm_select

from base_repository.base_filter import BaseRepoFilter
from base_repository.repository.base_repo import BaseRepository
from tests.perf.perf_reporter import record_one, record_table
from tests.perf.seed.config import PERF_RESULT_COLUMNS, SEED_DATA_ROWS
from .db_config import get_perf_engine, perf_session_provider


pytestmark = pytest.mark.asyncio(loop_scope="session")


INSERT_ROW_VALUES = [100, 500, 1_000, 5_000]
OFFSET_PAGES = [1, 10, 1_00, 5_00]
READ_ROW_VALUES = [100, 500, 1_000, 5_000]
PAGE_SIZE_FOR_PAGE_BENCH = 1_000
UPDATE_ROW_VALUES = [100, 500, 1_000, 5_000]
ITERATIONS = 100


# ===================================================================
# SQLAlchemy 모델 / Repo 정의
# ===================================================================
class PerfBase(DeclarativeBase):
    pass


class PerfResult(PerfBase):
    """
    10필드짜리 벤치마크용 테이블.

    id, category, status, tag, group_no, payload, value, value2, flag, extra
    seed data와 동일해야함.
    """
    __tablename__ = "perf_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    tag: Mapped[str] = mapped_column(String(20), nullable=False)
    group_no: Mapped[int] = mapped_column(Integer, nullable=False)

    payload: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    value2: Mapped[int] = mapped_column(Integer, nullable=False)

    flag: Mapped[int] = mapped_column(Integer, nullable=False)
    extra: Mapped[str] = mapped_column(String(50), nullable=False)


# SQLModel 버전 (동일 테이블 이름)
class PerfResultSQLModel(SQLModel, table=True):
    __tablename__ = "perf_result"

    id: int | None = Field(default=None, primary_key=True)

    category: str
    status: str
    tag: str
    group_no: int

    payload: str
    value: int
    value2: int

    flag: int
    extra: str

class HasTable(Protocol):
    __table__: Table

def _table_of(model: type[Any]) -> Table:
    return cast(HasTable, cast(Any, model)).__table__



class CommonModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PerfResultSchema(CommonModel):
    id: int | None
    category: str
    status: str
    tag: str
    group_no: int

    payload: str
    value: int
    value2: int

    flag: int
    extra: str


@dataclass
class PerfResultFilter(BaseRepoFilter):
    """
    BaseRepoFilter 규칙에 따라:
    - None → 조건 없음
    - bool → is_(val)
    - Sequence → in_(seq)
    - 기타 → ==
    """
    id: int | Sequence[int] | None = None
    category: str | Sequence[str] | None = None
    status: str | Sequence[str] | None = None
    tag: str | Sequence[str] | None = None
    group_no: int | Sequence[int] | None = None

    payload: str | Sequence[str] | None = None
    value: int | Sequence[int] | None = None
    value2: int | Sequence[int] | None = None

    flag: int | Sequence[int] | None = None
    extra: str | Sequence[str] | None = None


@dataclass
class PerfResultRangeFilter(BaseRepoFilter):
    """
    UPDATE 벤치마크용 범위 필터.
    """
    min_id: int | None = None
    max_id: int | None = None

    def where_criteria(self, model):
        crit = []
        if self.min_id is not None:
            crit.append(model.id >= self.min_id)
        if self.max_id is not None:
            crit.append(model.id <= self.max_id)
        return crit


class PerfResultRepo(BaseRepository[PerfResult]):
    filter_class = PerfResultFilter
    mapping_schema = PerfResultSchema


# ===================================================================
# 공통 유틸
# ===================================================================
async def get_max_id(session: AsyncSession) -> int:
    result = await session.scalar(select(func.max(PerfResult.id)))
    return result or 0


async def ensure_perf_tables() -> None:
    """
    perf_result 테이블이 없으면 생성.
    """
    engine = get_perf_engine()
    async with engine.begin() as conn:
        await conn.run_sync(PerfBase.metadata.create_all)


async def run_benchmark_create_or_update(
    func: Callable[[int], Awaitable[float]],
    row_values: list[int],
    *,
    iterations: int,
) -> dict[int, dict[str, float]]:
    results: dict[int, dict[str, float]] = {}

    for row in row_values:
        samples: list[float] = []
        for _ in range(iterations):
            sec = await func(row)
            samples.append(sec)

        samples_ms = [s * 1000 for s in samples]
        samples_sorted = sorted(samples_ms)
        p95 = samples_sorted[int(len(samples_sorted) * 0.95)]
        p99 = samples_sorted[int(len(samples_sorted) * 0.99)]

        results[row] = {
            "avg": statistics.mean(samples_ms),
            "p95": p95,
            "p99": p99,
        }

    return results


async def run_benchmark_pages(
    func: Callable[[int], Awaitable[float]],
    pages: list[int],
    *,
    iterations: int,
) -> dict[int, dict[str, float]]:
    """
    페이지 번호를 늘려가며 성능을 측정하는 벤치마크 헬퍼.
    func(page) -> seconds
    """
    results: dict[int, dict[str, float]] = {}

    for page in pages:
        samples: list[float] = []
        for _ in range(iterations):
            sec = await func(page)
            samples.append(sec)

        samples_ms = [s * 1000 for s in samples]
        samples_sorted = sorted(samples_ms)
        p95 = samples_sorted[int(len(samples_sorted) * 0.95)]
        p99 = samples_sorted[int(len(samples_sorted) * 0.99)]

        results[page] = {
            "avg": statistics.mean(samples_ms),
            "p95": p95,
            "p99": p99,
        }

    return results


async def run_benchmark_noarg(
    func: Callable[[], Awaitable[float]],
    *,
    iterations: int,
) -> dict[str, float]:
    """
    인자 없는 시나리오용 벤치마크 (복잡 WHERE/ORDER).
    """
    samples: list[float] = []
    for _ in range(iterations):
        sec = await func()
        samples.append(sec)

    samples_ms = [s * 1000 for s in samples]
    samples_sorted = sorted(samples_ms)
    p95 = samples_sorted[int(len(samples_sorted) * 0.95)]
    p99 = samples_sorted[int(len(samples_sorted) * 0.99)]

    return {
        "avg": statistics.mean(samples_ms),
        "p95": p95,
        "p99": p99,
    }


def print_table(
    title: str,
    rows: Mapping[int, Mapping[str, float]],
    iter: int,
    *,
    key_label: str = "ROW",
) -> None:
    print()
    print(f"=== {title} ===")
    print(f"{key_label:>8} | {'AVG(ms)':>10} | {'P95(ms)':>10} | {'P99(ms)':>10}")
    print("-" * 50)

    for key, metrics in rows.items():
        print(
            f"{key:>8} | "
            f"{metrics['avg']:>10.4f} | "
            f"{metrics['p95']:>10.4f} | "
            f"{metrics['p99']:>10.4f}"
        )

    print()
    metrics_items: dict[int, dict[str, float]] = {k: dict(v) for k, v in rows.items()}
    record_table(
        suite="db",
        source="tests/perf/perf_db_crud.py",
        scenario=title,
        key_label=key_label,
        metrics=metrics_items,
        iter=iter,
        seed_data_rows_cnt=SEED_DATA_ROWS,
    )


def print_one(title: str, metrics: dict[str, float], iter: int) -> None:
    print()
    print(f"=== {title} ===")
    print(f"AVG(ms): {metrics['avg']:.4f}, P95(ms): {metrics['p95']:.4f}, P99(ms): {metrics['p99']:.4f}")
    record_one(
        suite="db",
        source="tests/perf/perf_db_crud.py",
        scenario=title,
        metrics=metrics,
        iter=iter,
        seed_data_rows_cnt=SEED_DATA_ROWS
    )


def cleanup_inserted_rows(model):
    """
    CREATE 벤치마크 후에 새로 들어간 row들만 정리.
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(n: int):
            session: AsyncSession = perf_session_provider.get_session()
            before_max_id = await session.scalar(select(sa_func.max(model.id)))
            before_max_id = before_max_id or 0

            duration = await fn(n, session)

            after_max_id = await session.scalar(select(sa_func.max(model.id)))
            after_max_id = after_max_id or before_max_id
            if after_max_id > before_max_id:
                await session.execute(
                    delete(model).where(
                        model.id > before_max_id,
                        model.id <= after_max_id,
                    )
                )
                await session.commit()

            await session.close()
            return duration

        return wrapper
    return decorator


def with_read_session():
    """
    읽기/UPDATE 벤치마크용 데코레이터.
    - wrapper가 직접 session을 생성
    - 함수는 session을 받아 작업 수행
    - cleanup 없음
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            session: AsyncSession = perf_session_provider.get_session()

            try:
                duration = await fn(*args, session=session, **kwargs)
            finally:
                await session.close()

            return duration

        return wrapper
    return decorator


def delete_and_restore_row(model):
    """
    < DELETE 벤치 후 동일 row를 즉시 복구합니다 >
    1. target_id row를 먼저 SELECT로 읽어서 dict로 보관합니다.
    2. 벤치 함수(fn)가 target_id를 삭제합니다.
    3. 삭제 후 보관한 dict로 row를 다시 INSERT 합니다.
    4. 커밋하고 세션을 닫습니다.
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(target_id: int):
            session: AsyncSession = perf_session_provider.get_session()
            try:
                # 1) 삭제 대상 row 스냅샷 (id 제외)
                row = (await session.execute(select(model).where(model.id == target_id))).scalar_one()
                payload = {c.key: getattr(row, c.key) for c in model.__table__.columns if c.key != "id"}

                # 2) delete timing
                duration = await fn(target_id, session=session)

                # 3) restore
                session.add(model(id=target_id, **payload))
                await session.commit()
                return duration
            finally:
                await session.close()

        return wrapper
    return decorator


def make_row_values(i: int) -> dict[str, object]:
    """
    config.py의 PERF_RESULT_COLUMNS 정의만 보고 row dict를 만든다.
    """
    row: dict[str, object] = {}
    for col_name, col_fn in PERF_RESULT_COLUMNS:
        row[col_name] = col_fn(i)
    return row


def validate_perf_schema_consistency():
    # config.py 기준 컬럼명
    config_cols = {name for name, _ in PERF_RESULT_COLUMNS}

    # SQLAlchemy 모델 기준 컬럼명 (id 제외)
    sa_cols = {c.key for c in PerfResult.__table__.columns if c.key != "id"}

    # SQLModel 기준
    sqlm_cols = {field for field in PerfResultSQLModel.model_fields if field != "id"}

    # Pydantic Schema 기준
    schema_cols = {f for f in PerfResultSchema.model_fields if f != "id"}

    assert config_cols == sa_cols, f"Config vs SQLAlchemy mismatch:\nconfig={config_cols}\nmodel={sa_cols}"
    assert config_cols == sqlm_cols, f"Config vs SQLModel mismatch:\nconfig={config_cols}\nmodel={sqlm_cols}"
    assert config_cols == schema_cols, f"Config vs Schema mismatch:\nconfig={config_cols}\nmodel={schema_cols}"


# ===================================================================
# GET ONE: pk(id) 단건 조회
# ===================================================================
@with_read_session()
async def GET__sa_plain(target_id: int, session: AsyncSession) -> float:
    t0 = time.perf_counter()
    row = (await session.execute(select(PerfResult).where(PerfResult.id == target_id))).scalar_one_or_none()
    _ = row is not None
    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def GET__repo_get(target_id: int, session: AsyncSession) -> float:
    repo = PerfResultRepo()
    flt = PerfResultFilter(id=target_id)

    t0 = time.perf_counter()
    row = await repo.get(
        flt=flt,
        session=session,
        convert_domain=False,
    )
    _ = row is not None
    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def GET__sqlmodel_get(target_id: int, session: AsyncSession) -> float:
    t0 = time.perf_counter()
    row = await session.get(PerfResultSQLModel, target_id)
    _ = row is not None
    t1 = time.perf_counter()
    return t1 - t0


# ===================================================================
# CREATE MANY (SA / BaseRepo / SQLModel)
# ===================================================================
@cleanup_inserted_rows(PerfResult)
async def CREATE_MANY__sa_plain(n: int, session: AsyncSession) -> float:
    t0 = time.perf_counter()

    objs = [PerfResult(**make_row_values(i)) for i in range(n)]
    session.add_all(objs)
    await session.commit()

    t1 = time.perf_counter()
    return t1 - t0


@cleanup_inserted_rows(PerfResult)
async def CREATE_MANY__repo_create_many(n: int, session: AsyncSession) -> float:
    repo = PerfResultRepo()

    t0 = time.perf_counter()

    schemas = [
        PerfResultSchema(id=None, **cast(dict[str, Any], make_row_values(i)))
        for i in range(n)
    ]
    await repo.create_many(
        items=schemas,
        session=session,
        skip_convert=True,
    )
    await session.commit()

    t1 = time.perf_counter()
    return t1 - t0


@cleanup_inserted_rows(PerfResult)
async def CREATE_MANY__sqlmodel(n: int, session: AsyncSession) -> float:
    t0 = time.perf_counter()

    objs = [
        PerfResultSQLModel(id=None, **make_row_values(i))
        for i in range(n)
    ]
    session.add_all(objs)
    await session.commit()

    t1 = time.perf_counter()
    return t1 - t0


# ===================================================================
# CREATE (SA / BaseRepo / SQLModel)
# ===================================================================
@cleanup_inserted_rows(PerfResult)
async def CREATE__sa_plain(n: int, session: AsyncSession) -> float:
    t0 = time.perf_counter()

    objs = PerfResult(**make_row_values(0))
    session.add(objs)
    await session.commit()

    t1 = time.perf_counter()
    return t1 - t0


@cleanup_inserted_rows(PerfResult)
async def CREATE__repo_create(n: int, session: AsyncSession) -> float:
    repo = PerfResultRepo()

    t0 = time.perf_counter()

    schema = PerfResultSchema(id=None, **cast(dict[str, Any], make_row_values(0)))
    await repo.create(
        data=schema,
        session=session,
    )
    await session.commit()

    t1 = time.perf_counter()
    return t1 - t0


@cleanup_inserted_rows(PerfResult)
async def CREATE__sqlmodel(n: int, session: AsyncSession) -> float:
    t0 = time.perf_counter()

    obj = PerfResultSQLModel(id=None, **make_row_values(0))
    session.add(obj)
    await session.commit()

    t1 = time.perf_counter()
    return t1 - t0



# ===================================================================
# UPDATE MANY (같은 범위를 SA / BaseRepo / SQLModel로 갱신)
# ===================================================================
@with_read_session()
async def UPDATE_MANY__sa_plain(n: int, session: AsyncSession) -> float:
    """
    SQLAlchemy Core update:
    - id <= n 인 row의 value2를 999로 업데이트
    """
    t0 = time.perf_counter()

    stmt = (
        sa_update(PerfResult)
        .where(PerfResult.id <= n)
        .values(value2=999)
    )
    await session.execute(stmt)
    await session.commit()

    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def UPDATE_MANY__repo_update(n: int, session: AsyncSession) -> float:
    """
    BaseRepository.update 사용.
    """
    repo = PerfResultRepo()
    flt = PerfResultRangeFilter(max_id=n)

    t0 = time.perf_counter()

    _rowcount = await repo.update(
        flt=flt,
        update={"value2": 999},
        session=session,
    )
    await session.commit()

    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def UPDATE_MANY__sqlmodel_dirty(n: int, session: AsyncSession) -> float:
    """
    SQLModel 스타일:
    - 대상 row들을 SELECT로 불러와서 value2만 수정 → dirty checking.
    - SQL 한 방 UPDATE가 아니라 row 단위 갱신 성능을 보고 싶은 경우.
    """
    tbl = _table_of(PerfResultSQLModel)
    c = tbl.c
    t0 = time.perf_counter()

    stmt = (
        sqlm_select(PerfResultSQLModel)
        .where(c.id <= n)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    for obj in rows:
        obj.value2 = 999

    await session.commit()

    t1 = time.perf_counter()
    return t1 - t0


# ===================================================================
# READ MANY: offset / keyset (단순 id 정렬)
# ===================================================================
@with_read_session()
async def READ_PAGE__sa_offset(page: int, session: AsyncSession) -> float:
    offset = (page - 1) * PAGE_SIZE_FOR_PAGE_BENCH

    stmt = (
        select(PerfResult)
        .order_by(PerfResult.id.asc())
        .offset(offset)
        .limit(PAGE_SIZE_FOR_PAGE_BENCH)
    )

    t0 = time.perf_counter()
    rows = (await session.execute(stmt)).scalars().all()
    _ = len(rows)
    t1 = time.perf_counter()

    return t1 - t0


@with_read_session()
async def READ_PAGE__repo_offset(page: int, session: AsyncSession) -> float:
    repo = PerfResultRepo()

    t0 = time.perf_counter()
    rows = await repo.get_list(
        order_by=[PerfResult.id.asc()],
        page=page,
        size=PAGE_SIZE_FOR_PAGE_BENCH,
        session=session,
        convert_domain=False,
    )
    _ = len(rows)
    t1 = time.perf_counter()

    return t1 - t0


@with_read_session()
async def READ_PAGE__sa_keyset(page: int, session: AsyncSession) -> float:
    """
    keyset: id가 연속이라고 가정하고 page 기준으로 start_id 계산.
    """
    start_id = (page - 1) * PAGE_SIZE_FOR_PAGE_BENCH

    stmt = (
        select(PerfResult)
        .where(PerfResult.id > start_id)
        .order_by(PerfResult.id.asc())
        .limit(PAGE_SIZE_FOR_PAGE_BENCH)
    )

    t0 = time.perf_counter()
    rows = (await session.execute(stmt)).scalars().all()
    _ = len(rows)
    t1 = time.perf_counter()

    return t1 - t0


@with_read_session()
async def READ_PAGE__repo_keyset(page: int, session: AsyncSession) -> float:
    """
    BaseRepository.get_list keyset:
    - cursor는 {'id': start_id}만 사용 (단일 정렬 컬럼).
    """
    repo = PerfResultRepo()

    start_id = (page - 1) * PAGE_SIZE_FOR_PAGE_BENCH
    cursor = {} if start_id == 0 else {"id": start_id}

    t0 = time.perf_counter()
    rows = await repo.get_list(
        order_by=[PerfResult.id.asc()],
        cursor=cursor,
        size=PAGE_SIZE_FOR_PAGE_BENCH,
        session=session,
        convert_domain=False,
    )
    _ = len(rows)
    t1 = time.perf_counter()

    return t1 - t0


@with_read_session()
async def READ_PAGE__sqlmodel_offset(page: int, session: AsyncSession) -> float:
    """
    SQLModel select + offset.
    """
    tbl = _table_of(PerfResultSQLModel)
    c = tbl.c

    offset = (page - 1) * PAGE_SIZE_FOR_PAGE_BENCH

    stmt = (
        sqlm_select(PerfResultSQLModel)
        .order_by(c.id.asc())
        .offset(offset)
        .limit(PAGE_SIZE_FOR_PAGE_BENCH)
    )

    t0 = time.perf_counter()
    rows = (await session.execute(stmt)).scalars().all()
    _ = len(rows)
    t1 = time.perf_counter()

    return t1 - t0


# ===================================================================
# 복잡 WHERE / ORDER 전용 시나리오
# ===================================================================
@with_read_session()
async def COMPLEX_WHERE8__sa(session: AsyncSession) -> float:
    """
    WHERE 조건 8개 (IN / EQ 혼합), ORDER 단순(id).
    """
    stmt = (
        select(PerfResult)
        .where(
            PerfResult.id.in_([1, 2, 3, 4]),
            PerfResult.category.in_(["cat-1", "cat-2"]),
            PerfResult.status.in_(["status-1", "status-2"]),
            PerfResult.tag.in_(["tag-0", "tag-1"]),
            PerfResult.group_no.in_([10, 11, 12]),
            PerfResult.value == 100,
            PerfResult.value2 == 1_000_000,
            PerfResult.flag.in_([0, 1]),
        )
        .order_by(PerfResult.id.asc())
        .limit(1_000)
        .offset(0)
    )

    t0 = time.perf_counter()
    rows = (await session.execute(stmt)).scalars().all()
    _ = len(rows)
    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def COMPLEX_WHERE8__repo(session: AsyncSession) -> float:
    repo = PerfResultRepo()

    flt = PerfResultFilter(
        id=[1, 2, 3, 4],
        category=["cat-1", "cat-2"],
        status=["status-1", "status-2"],
        tag=["tag-0", "tag-1"],
        group_no=[10, 11, 12],
        value=100,           
        value2=1_000_000,
        flag=[0, 1],
    )

    t0 = time.perf_counter()
    rows = await repo.get_list(
        flt=flt,
        order_by=[PerfResult.id.asc()],
        page=1,
        size=1_000,
        session=session,
        convert_domain=False,
    )
    _ = len(rows)
    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def COMPLEX_WHERE8__sqlmodel(session: AsyncSession) -> float:
    tbl = _table_of(PerfResultSQLModel)
    c = tbl.c
    stmt = (
        sqlm_select(PerfResultSQLModel)
        .where(
            c.id.in_([1, 2, 3, 4]),
            c.category.in_(["cat-1", "cat-2"]),
            c.status.in_(["status-1", "status-2"]),
            c.tag.in_(["tag-0", "tag-1"]),
            c.group_no.in_([10, 11, 12]),
            c.value == 100,
            c.value2 == 1_000_000,
            c.flag.in_([0, 1]),
        )
        .order_by(c.id.asc())
        .limit(1_000)
        .offset(0)
    )

    t0 = time.perf_counter()
    rows = (await session.execute(stmt)).scalars().all()
    _ = len(rows)
    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def COMPLEX_WHERE3_ORDER3__sa(session: AsyncSession) -> float:
    stmt = (
        select(PerfResult)
        .where(
            PerfResult.category == "cat-1",
            PerfResult.status == "status-1",
            PerfResult.flag == 1,
        )
        .order_by(
            PerfResult.category.asc(),
            PerfResult.value2.desc(),
            PerfResult.id.asc(),
        )
        .limit(1_000)
        .offset(0)
    )

    t0 = time.perf_counter()
    rows = (await session.execute(stmt)).scalars().all()
    _ = len(rows)
    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def COMPLEX_WHERE3_ORDER3__repo(session: AsyncSession) -> float:
    repo = PerfResultRepo()

    flt = PerfResultFilter(
        category="cat-1",
        status="status-1",
        flag=1,
    )

    t0 = time.perf_counter()
    rows = await repo.get_list(
        flt=flt,
        order_by=[
            PerfResult.category.asc(),
            PerfResult.value2.desc(),
            PerfResult.id.asc(),
        ],
        page=1,
        size=1_000,
        session=session,
        convert_domain=False,
    )
    _ = len(rows)
    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def COMPLEX_WHERE3_ORDER3__sqlmodel(session: AsyncSession) -> float:
    tbl = _table_of(PerfResultSQLModel)
    c = tbl.c
    stmt = (
        sqlm_select(PerfResultSQLModel)
        .where(
            c.category == "cat-1",
            c.status == "status-1",
            c.flag == 1,
        )
        .order_by(
            c.category.asc(),
            c.value2.desc(),
            c.id.asc(),
        )
        .limit(1_000)
        .offset(0)
    )

    t0 = time.perf_counter()
    rows = (await session.execute(stmt)).scalars().all()
    _ = len(rows)
    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def COMPLEX_ORDER8__sa(session: AsyncSession) -> float:
    stmt = (
        select(PerfResult)
        .order_by(
            PerfResult.category.asc(),
            PerfResult.status.asc(),
            PerfResult.tag.asc(),
            PerfResult.group_no.asc(),
            PerfResult.flag.desc(),
            PerfResult.value.desc(),
            PerfResult.value2.desc(),
            PerfResult.id.asc(),
        )
        .limit(1_000)
        .offset(0)
    )

    t0 = time.perf_counter()
    rows = (await session.execute(stmt)).scalars().all()
    _ = len(rows)
    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def COMPLEX_ORDER8__repo(session: AsyncSession) -> float:
    repo = PerfResultRepo()

    t0 = time.perf_counter()
    rows = await repo.get_list(
        order_by=[
            PerfResult.category.asc(),
            PerfResult.status.asc(),
            PerfResult.tag.asc(),
            PerfResult.group_no.asc(),
            PerfResult.flag.desc(),
            PerfResult.value.desc(),
            PerfResult.value2.desc(),
            PerfResult.id.asc(),
        ],
        page=1,
        size=1_000,
        session=session,
        convert_domain=False,
    )
    _ = len(rows)
    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def COMPLEX_ORDER8__sqlmodel(session: AsyncSession) -> float:
    tbl = _table_of(PerfResultSQLModel)
    c = tbl.c

    # 2
    stmt = (
        sqlm_select(PerfResultSQLModel)
        .order_by(
            c.category.asc(),
            c.status.asc(),
            c.tag.asc(),
            c.group_no.asc(),
            c.flag.desc(),
            c.value.desc(),
            c.value2.desc(),
            c.id.asc(),
        )
        .limit(1_000)
        .offset(0)
    )

    t0 = time.perf_counter()
    rows = (await session.execute(stmt)).scalars().all()
    _ = len(rows)
    t1 = time.perf_counter()
    return t1 - t0


# ===================================================================
# COUNT: 전체 / 조건부
# ===================================================================
@with_read_session()
async def COUNT_ALL__sa(session: AsyncSession) -> float:
    t0 = time.perf_counter()
    cnt = await session.scalar(select(func.count()).select_from(PerfResult))
    _ = int(cnt or 0)
    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def COUNT_ALL__repo(session: AsyncSession) -> float:
    repo = PerfResultRepo()

    t0 = time.perf_counter()
    cnt = await repo.count(session=session)
    _ = int(cnt)
    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def COUNT_ALL__sqlmodel(session: AsyncSession) -> float:
    t0 = time.perf_counter()
    cnt = await session.scalar(select(func.count()).select_from(PerfResultSQLModel))
    _ = int(cnt or 0)
    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def COUNT_WHERE3__sa(session: AsyncSession) -> float:
    stmt = (
        select(func.count())
        .select_from(PerfResult)
        .where(
            PerfResult.category == "cat-1",
            PerfResult.status == "status-1",
            PerfResult.flag == 1,
        )
    )

    t0 = time.perf_counter()
    cnt = await session.scalar(stmt)
    _ = int(cnt or 0)
    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def COUNT_WHERE3__repo(session: AsyncSession) -> float:
    repo = PerfResultRepo()
    flt = PerfResultFilter(category="cat-1", status="status-1", flag=1)

    t0 = time.perf_counter()
    cnt = await repo.count(flt=flt, session=session)
    _ = int(cnt)
    t1 = time.perf_counter()
    return t1 - t0


@with_read_session()
async def COUNT_WHERE3__sqlmodel(session: AsyncSession) -> float:
    stmt = (
        select(func.count())
        .select_from(PerfResultSQLModel)
        .where(
            column("category") == "cat-1",
            column("status") == "status-1",
            column("flag") == 1,
        )
    )

    t0 = time.perf_counter()
    cnt = await session.scalar(stmt)
    _ = int(cnt or 0)
    t1 = time.perf_counter()
    return t1 - t0


# ===================================================================
# DELETE ONE (SA / BaseRepo / SQLModel)
# ===================================================================
@delete_and_restore_row(PerfResult)
async def DELETE__sa_plain(target_id: int, *, session: AsyncSession) -> float:
    t0 = time.perf_counter()
    res = await session.execute(delete(PerfResult).where(PerfResult.id == target_id))
    _ = res.rowcount or 0 # type: ignore[attr-defined]
    await session.commit()
    t1 = time.perf_counter()
    return t1 - t0


@delete_and_restore_row(PerfResult)
async def DELETE__repo_delete(target_id: int, *, session: AsyncSession) -> float:
    repo = PerfResultRepo()
    flt = PerfResultFilter(id=target_id)

    t0 = time.perf_counter()
    _rowcount = await repo.delete(flt=flt, session=session)
    await session.commit()
    t1 = time.perf_counter()
    return t1 - t0


@delete_and_restore_row(PerfResult)
async def DELETE__sqlmodel(target_id: int, *, session: AsyncSession) -> float:
    t0 = time.perf_counter()
    obj = await session.get(PerfResultSQLModel, target_id)
    if obj is not None:
        await session.delete(obj)
        await session.commit()
    t1 = time.perf_counter()
    return t1 - t0


# ===================================================================
# 실제 테스트
# ===================================================================
@pytest.mark.asyncio
@pytest.mark.perf_db
async def test_perf_db_create_many() -> None:
    create_sa = await run_benchmark_create_or_update(
        CREATE_MANY__sa_plain,
        INSERT_ROW_VALUES,
        iterations=ITERATIONS,
    )
    print_table("[TEST bulk create from schemas] sqlalchemy", create_sa, ITERATIONS)

    create_repo = await run_benchmark_create_or_update(
        CREATE_MANY__repo_create_many,
        INSERT_ROW_VALUES,
        iterations=ITERATIONS,
    )
    print_table("[TEST bulk create from schemas] baserepo", create_repo, ITERATIONS)

    create_sqlm = await run_benchmark_create_or_update(
        CREATE_MANY__sqlmodel,
        INSERT_ROW_VALUES,
        iterations=ITERATIONS,
    )
    print_table("[TEST bulk create from schemas] sqlmodel", create_sqlm, ITERATIONS)


@pytest.mark.asyncio
@pytest.mark.perf_db
async def test_perf_db_create() -> None:
    create_sa = await run_benchmark_create_or_update(
        CREATE__sa_plain,
        INSERT_ROW_VALUES,
        iterations=ITERATIONS,
    )
    print_table("[TEST create from schemas] sqlalchemy", create_sa, ITERATIONS)

    create_repo = await run_benchmark_create_or_update(
        CREATE__repo_create,
        INSERT_ROW_VALUES,
        iterations=ITERATIONS,
    )
    print_table("[TEST create from schemas] baserepo", create_repo, ITERATIONS)

    create_sqlm = await run_benchmark_create_or_update(
        CREATE__sqlmodel,
        INSERT_ROW_VALUES,
        iterations=ITERATIONS,
    )
    print_table("[TEST create from schemas] sqlmodel", create_sqlm, ITERATIONS)


@pytest.mark.asyncio
@pytest.mark.perf_db
async def test_perf_db_page_scaling_offset_vs_keyset() -> None:
    # SA offset
    sa_offset = await run_benchmark_pages(
        READ_PAGE__sa_offset,
        OFFSET_PAGES,
        iterations=ITERATIONS,
    )
    print_table(f"[TEST paging (page size:{PAGE_SIZE_FOR_PAGE_BENCH}) with ORDER BY ID- offset] sqlalchemy offset", sa_offset, iter=ITERATIONS, key_label="PAGE")

    # Repo offset
    repo_offset = await run_benchmark_pages(
        READ_PAGE__repo_offset,
        OFFSET_PAGES,
        iterations=ITERATIONS,
    )
    print_table(f"[TEST paging (page size:{PAGE_SIZE_FOR_PAGE_BENCH}) with ORDER BY ID- offset] baserepo offset", repo_offset, iter=ITERATIONS, key_label="PAGE")

    # SQLModel offset
    sqlm_offset = await run_benchmark_pages(
        READ_PAGE__sqlmodel_offset,
        OFFSET_PAGES,
        iterations=ITERATIONS,
    )
    print_table(f"[TEST paging (page size:{PAGE_SIZE_FOR_PAGE_BENCH}) with ORDER BY ID- offset] sqlmodel offset", sqlm_offset, iter=ITERATIONS, key_label="PAGE")

    # SA keyset
    sa_keyset = await run_benchmark_pages(
        READ_PAGE__sa_keyset,
        OFFSET_PAGES,
        iterations=ITERATIONS,
    )
    print_table(f"[TEST paging (page size:{PAGE_SIZE_FOR_PAGE_BENCH}) with ORDER BY ID- keyset] sqlalchemy keyset(id)", sa_keyset, iter=ITERATIONS, key_label="PAGE")

    # Repo keyset
    repo_keyset = await run_benchmark_pages(
        READ_PAGE__repo_keyset,
        OFFSET_PAGES,
        iterations=ITERATIONS,
    )
    print_table(f"[TEST paging (page size:{PAGE_SIZE_FOR_PAGE_BENCH}) with ORDER BY ID- keyset] baserepo keyset(id)", repo_keyset, iter=ITERATIONS, key_label="PAGE")


@pytest.mark.asyncio
@pytest.mark.perf_db
async def test_perf_db_update_many() -> None:
    "update 테스트입니다."
    update_sa = await run_benchmark_create_or_update(
        UPDATE_MANY__sa_plain,
        UPDATE_ROW_VALUES,
        iterations=ITERATIONS,
    )
    print_table("[TEST bulk update from dict] sqlalchemy", update_sa, iter=ITERATIONS)

    update_repo = await run_benchmark_create_or_update(
        UPDATE_MANY__repo_update,
        UPDATE_ROW_VALUES,
        iterations=ITERATIONS,
    )
    print_table("[TEST bulk update from dict] baserepo", update_repo, iter=ITERATIONS)

    update_sqlm = await run_benchmark_create_or_update(
        UPDATE_MANY__sqlmodel_dirty,
        UPDATE_ROW_VALUES,
        iterations=ITERATIONS,
    )
    print_table("[TEST bulk update from dict] sqlmodel-dirty-check", update_sqlm, iter=ITERATIONS)


@pytest.mark.asyncio
@pytest.mark.perf_db
async def test_perf_db_complex_where_and_multi_order() -> None:
    """
    복잡 조건 / 정렬 조합에 대한 라이브러리별 비교.
    """

    # WHERE 8개
    sa_where8 = await run_benchmark_noarg(COMPLEX_WHERE8__sa, iterations=ITERATIONS)
    repo_where8 = await run_benchmark_noarg(COMPLEX_WHERE8__repo, iterations=ITERATIONS)
    sqlm_where8 = await run_benchmark_noarg(COMPLEX_WHERE8__sqlmodel, iterations=ITERATIONS)

    print_one("[TEST fetch with 8 WHERE Conditions] - sqlalchemy", sa_where8, iter=ITERATIONS)
    print_one("[TEST fetch with 8 WHERE Conditions] - baserepo", repo_where8, iter=ITERATIONS)
    print_one("[TEST fetch with 8 WHERE Conditions] - sqlmodel", sqlm_where8, iter=ITERATIONS)

    # WHERE 3개 + ORDER 3개
    sa_w3_o3 = await run_benchmark_noarg(COMPLEX_WHERE3_ORDER3__sa, iterations=ITERATIONS)
    repo_w3_o3 = await run_benchmark_noarg(COMPLEX_WHERE3_ORDER3__repo, iterations=ITERATIONS)
    sqlm_w3_o3 = await run_benchmark_noarg(COMPLEX_WHERE3_ORDER3__sqlmodel, iterations=ITERATIONS)

    print_one("[TEST fetch with 3 WHERE and 3 ORDER BY Conditions] - sqlalchemy", sa_w3_o3, iter=ITERATIONS)
    print_one("[TEST fetch with 3 WHERE and 3 ORDER BY Conditions] - baserepo", repo_w3_o3, iter=ITERATIONS)
    print_one("[TEST fetch with 3 WHERE and 3 ORDER BY Conditions] - sqlmodel", sqlm_w3_o3, iter=ITERATIONS)

    # ORDER 8개
    sa_o8 = await run_benchmark_noarg(COMPLEX_ORDER8__sa, iterations=ITERATIONS)
    repo_o8 = await run_benchmark_noarg(COMPLEX_ORDER8__repo, iterations=ITERATIONS)
    sqlm_o8 = await run_benchmark_noarg(COMPLEX_ORDER8__sqlmodel, iterations=ITERATIONS)

    print_one("[TEST fetch with 8 ORDER By Conditions] - sqlalchemy", sa_o8, iter=ITERATIONS)
    print_one("[TEST fetch with 8 ORDER By Conditions] - baserepo", repo_o8, iter=ITERATIONS)
    print_one("[TEST fetch with 8 ORDER By Conditions] - sqlmodel", sqlm_o8, iter=ITERATIONS)


@pytest.mark.asyncio
@pytest.mark.perf_db
async def test_perf_db_get() -> None:
    """ 단건 get 비교 테스트"""
    session: AsyncSession = perf_session_provider.get_session()
    try:
        max_id = await get_max_id(session)
    finally:
        await session.close()

    if max_id <= 0:
        pytest.skip("perf_result 테이블에 seed 데이터가 없습니다.")

    target_ids = [min(v, max_id) for v in READ_ROW_VALUES]

    get_sa = await run_benchmark_create_or_update(
        GET__sa_plain,
        target_ids,
        iterations=ITERATIONS,
    )
    print_table("[TEST get one by pk(id)] sqlalchemy", get_sa, iter=ITERATIONS)

    get_repo = await run_benchmark_create_or_update(
        GET__repo_get,
        target_ids,
        iterations=ITERATIONS,
    )
    print_table("[TEST get one by pk(id)] baserepo", get_repo, iter=ITERATIONS)

    get_sqlm = await run_benchmark_create_or_update(
        GET__sqlmodel_get,
        target_ids,
        iterations=ITERATIONS,
    )
    print_table("[TEST get one by pk(id)] sqlmodel", get_sqlm, iter=ITERATIONS)


@pytest.mark.asyncio
@pytest.mark.perf_db
async def test_perf_db_count() -> None:
    """count 테스트를 진행합니다."""
    session: AsyncSession = perf_session_provider.get_session()
    try:
        max_id = await get_max_id(session)
    finally:
        await session.close()

    if max_id <= 0:
        pytest.skip("perf_result 테이블에 seed 데이터가 없습니다.")

    # COUNT ALL
    sa_all = await run_benchmark_noarg(COUNT_ALL__sa, iterations=ITERATIONS)
    repo_all = await run_benchmark_noarg(COUNT_ALL__repo, iterations=ITERATIONS)
    sqlm_all = await run_benchmark_noarg(COUNT_ALL__sqlmodel, iterations=ITERATIONS)

    print_one("[TEST count(*)] - sqlalchemy", sa_all, iter=ITERATIONS)
    print_one("[TEST count(*)] - baserepo", repo_all, iter=ITERATIONS)
    print_one("[TEST count(*)] - sqlmodel", sqlm_all, iter=ITERATIONS)

    # COUNT WHERE 3
    sa_w3 = await run_benchmark_noarg(COUNT_WHERE3__sa, iterations=ITERATIONS)
    repo_w3 = await run_benchmark_noarg(COUNT_WHERE3__repo, iterations=ITERATIONS)
    sqlm_w3 = await run_benchmark_noarg(COUNT_WHERE3__sqlmodel, iterations=ITERATIONS)

    print_one("[TEST count(*) with 3 WHERE] - sqlalchemy", sa_w3, iter=ITERATIONS)
    print_one("[TEST count(*) with 3 WHERE] - baserepo", repo_w3, iter=ITERATIONS)
    print_one("[TEST count(*) with 3 WHERE] - sqlmodel", sqlm_w3, iter=ITERATIONS)


@pytest.mark.asyncio
@pytest.mark.perf_db
async def test_perf_db_delete_one() -> None:
    session: AsyncSession = perf_session_provider.get_session()
    try:
        max_id = await get_max_id(session)
    finally:
        await session.close()

    if max_id <= 0:
        pytest.skip("perf_result 테이블에 seed 데이터가 없습니다.")

    target_ids = [min(v, max_id) for v in READ_ROW_VALUES]

    del_sa = await run_benchmark_create_or_update(
        DELETE__sa_plain,
        target_ids,
        iterations=ITERATIONS,
    )
    print_table("[TEST delete one by pk(id) + restore] sqlalchemy", del_sa, iter=ITERATIONS)

    del_repo = await run_benchmark_create_or_update(
        DELETE__repo_delete,
        target_ids,
        iterations=ITERATIONS,
    )
    print_table("[TEST delete one by pk(id) + restore] baserepo", del_repo, iter=ITERATIONS)

    del_sqlm = await run_benchmark_create_or_update(
        DELETE__sqlmodel,
        target_ids,
        iterations=ITERATIONS,
    )
    print_table("[TEST delete one by pk(id) + restore] sqlmodel", del_sqlm, iter=ITERATIONS)