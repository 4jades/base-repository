from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Awaitable, Callable

import pytest
import statistics
import time
from pydantic import BaseModel
from sqlmodel import SQLModel, Field
from sqlalchemy import select

from base_repository.base_filter import BaseRepoFilter
from base_repository.repository.base_repo import BaseRepository
from tests.perf.perf_reporter import record_table
from ..fakes import FakeAsyncSession, FakeResult
from ..models import Item, Category, Result
from ..schemas import ResultStrictSchema


ROW_VALUES = [10, 50, 100, 200, 500, 1000, 5000]
ITERATIONS = 50

# -------------------------------------------------------------------
# 공통 Filter / Repo
# -------------------------------------------------------------------
@dataclass
class ResultFilter(BaseRepoFilter):
    id: int | None = None
    tenant_id: int | None = None
    checkup_id: int | None = None


class ResultStrictRepo(BaseRepository[Result]):
    filter_class = ResultFilter
    mapping_schema = ResultStrictSchema


# -------------------------------------------------------------------
# Fake Session / Fake Rows
# -------------------------------------------------------------------
class BenchmarkAsyncSession(FakeAsyncSession):
    async def execute(self, stmt: Any) -> FakeResult:
        # 항상 동일한 FakeResult 반환
        return self._script[0]


class DMLOnlySession(FakeAsyncSession):
    """
    UPDATE 계열 벤치용 세션:
    - execute() 에서 FakeResult만 돌려주고, script 소진 검사를 하지 않는다.
    """
    def __init__(self) -> None:
        super().__init__(script=[])

    async def execute(self, stmt: Any) -> FakeResult:  # type: ignore[override]
        return FakeResult(rows=[])


def build_result_rows(n: int) -> list[Result]:
    rows: list[Result] = []
    for i in range(n):
        item = Item(id=i, name=f"item-{i}")
        category = Category(id=i, title=f"category-{i}")
        result = Result(
            id=i,
            item_id=item.id,
            sub_category_id=category.id,
            result_value=str(i),
            is_abnormal=(i % 2 == 0),
            tenant_id=1,
            checkup_id=1,
        )
        result.item = item
        result.sub_category = category
        rows.append(result)
    return rows


# SQLModel: Result와 동일한 필드 구조를 가진 테이블 모델
class ResultSQLModel(SQLModel, table=True):
    """
    SQLModel 스타일 비교용 테이블 모델.
    - 실제 DB는 안 붙지만, SQLAlchemy에서 select(ResultSQLModel)이 가능하려면
      table=True로 매핑된 모델이어야 한다.
    """
    __tablename__ = "result_sqlmodel_bench"

    id: int | None = Field(default=None, primary_key=True)
    item_id: int = Field()
    sub_category_id: int = Field()
    result_value: str = Field()
    is_abnormal: bool = Field()
    tenant_id: int = Field()
    checkup_id: int = Field()


def build_sqlmodel_rows(n: int) -> list[ResultSQLModel]:
    rows: list[ResultSQLModel] = []
    for i in range(n):
        rows.append(
            ResultSQLModel(
                id=i,
                item_id=i,
                sub_category_id=i,
                result_value=str(i),
                is_abnormal=(i % 2 == 0),
                tenant_id=1,
                checkup_id=1,
            )
        )
    return rows


# -------------------------------------------------------------------
# 캐시: result rows / sqlmodel rows / FakeResult
# -------------------------------------------------------------------
@lru_cache(maxsize=None)
def cached_result_rows(n: int) -> list[Result]:
    return build_result_rows(n)


@lru_cache(maxsize=None)
def cached_sqlmodel_rows(n: int) -> list[ResultSQLModel]:
    return build_sqlmodel_rows(n)


@lru_cache(maxsize=None)
def cached_fake_result_orm(n: int) -> FakeResult:
    return FakeResult(rows=cached_result_rows(n))


@lru_cache(maxsize=None)
def cached_fake_result_sqlmodel(n: int) -> FakeResult:
    return FakeResult(rows=cached_sqlmodel_rows(n))


# -------------------------------------------------------------------
# create_many / create_from_model 용 스키마 & payload 캐시
# -------------------------------------------------------------------
class ResultCreateSchema(BaseModel):
    item_id: int
    sub_category_id: int
    result_value: str
    is_abnormal: bool
    tenant_id: int
    checkup_id: int


@lru_cache(maxsize=None)
def cached_create_payloads_dict(n: int) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for i in range(n):
        payloads.append(
            {
                "item_id": i,
                "sub_category_id": i,
                "result_value": str(i),
                "is_abnormal": (i % 2 == 0),
                "tenant_id": 1,
                "checkup_id": 1,
            }
        )
    return payloads


@lru_cache(maxsize=None)
def cached_create_payloads_schema(n: int) -> list[ResultCreateSchema]:
    payloads: list[ResultCreateSchema] = []
    for i in range(n):
        payloads.append(
            ResultCreateSchema(
                item_id=i,
                sub_category_id=i,
                result_value=str(i),
                is_abnormal=(i % 2 == 0),
                tenant_id=1,
                checkup_id=1,
            )
        )
    return payloads


@lru_cache(maxsize=None)
def cached_create_models(n: int) -> list[Result]:
    # create_from_model / update_from_model 시나리오용 ORM 인스턴스
    return build_result_rows(n)


# -------------------------------------------------------------------
# UPDATE 용 payload 캐시
# -------------------------------------------------------------------
@lru_cache(maxsize=None)
def cached_update_payloads_dict(n: int) -> list[dict[str, Any]]:
    """
    각 id에 대해 변경할 필드 payload
    """
    payloads: list[dict[str, Any]] = []
    for i in range(n):
        payloads.append(
            {
                "result_value": f"updated-{i}",
                "is_abnormal": bool(i % 2),
            }
        )
    return payloads


# -------------------------------------------------------------------
# 전역 SELECT 문 캐싱
# -------------------------------------------------------------------
SELECT_RESULT = (
    select(Result)
    .order_by(Result.id.asc())
    .limit(50)
    .offset(0)
)

SELECT_RESULT_SQLMODEL = (
    select(ResultSQLModel)
    .order_by(ResultSQLModel.id.asc())
    .limit(50)
    .offset(0)
)


# -------------------------------------------------------------------
# 공통 벤치 실행 / 출력
# -------------------------------------------------------------------
async def run_benchmark(
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



def print_table(title: str, rows: dict[int, dict[str, float]], iter: int) -> None:
    print()
    print(f"=== {title} ===")
    print(f"{'ROW':>6} | {'AVG(ms)':>10} | {'P95(ms)':>10} | {'P99(ms)':>10}")
    print("-" * 46)
    for row, metrics in rows.items():
        print(
            f"{row:>6} | "
            f"{metrics['avg']:>10.4f} | "
            f"{metrics['p95']:>10.4f} | "
            f"{metrics['p99']:>10.4f}"
        )

    record_table(
        suite="cpu",
        source="tests/perf/perf_cpu_only.py",
        scenario=title,
        key_label="ROW",
        metrics=rows,
        iter=iter
    )

# -------------------------------------------------------------------
# 시나리오: GET_LIST (여러 rows 조회)
# -------------------------------------------------------------------
async def GET_LIST__bench_sa_pipeline(n: int) -> float:
    """
    SQLAlchemy + Pydantic 파이프라인
    """
    fake_result = cached_fake_result_orm(n)
    session = BenchmarkAsyncSession(script=[fake_result])
    stmt = SELECT_RESULT

    t0 = time.perf_counter()
    res = await session.execute(stmt)
    rows = list(res.scalars())
    _ = [
        ResultStrictSchema.model_validate(row, from_attributes=True)
        for row in rows
    ]
    t1 = time.perf_counter()

    return t1 - t0


async def GET_LIST__bench_sqlmodel_pipeline(n: int) -> float:
    """
    SQLModel 파이프라인
    """
    fake_result = cached_fake_result_sqlmodel(n)
    session = BenchmarkAsyncSession(script=[fake_result])
    stmt = SELECT_RESULT_SQLMODEL

    t0 = time.perf_counter()
    res = await session.execute(stmt)
    rows = list(res.scalars())
    _ = [
        ResultSQLModel.model_validate(row, from_attributes=True)
        for row in rows
    ]
    t1 = time.perf_counter()

    return t1 - t0


async def GET_LIST__bench_repo_pipeline(n: int) -> float:
    """
    BaseRepository.get_list 파이프라인 (도메인 변환 ON)
    """
    fake_result = cached_fake_result_orm(n)
    session = BenchmarkAsyncSession(script=[fake_result])
    repo = ResultStrictRepo(session=session, default_convert_domain=True)

    t0 = time.perf_counter()
    _ = await repo.get_list(
        order_by=[Result.id.asc()],
        page=1,
        size=50,
        convert_domain=True,
    )
    t1 = time.perf_counter()

    return t1 - t0


# -------------------------------------------------------------------
# 시나리오: SCHEMA_CONVERT (ORM → 스키마 단순 변환)
# -------------------------------------------------------------------
async def SCHEMA_CONVERT__pydantic(n: int) -> float:
    """
    ORM → Pydantic(ResultStrictSchema)
    """
    rows = cached_result_rows(n)

    t0 = time.perf_counter()
    for row in rows:
        ResultStrictSchema.model_validate(row, from_attributes=True)
    t1 = time.perf_counter()

    return t1 - t0


async def SCHEMA_CONVERT__sqlmodel(n: int) -> float:
    """
    ORM(SQLModel 인스턴스) → SQLModel(ResultSQLModel)
    """
    rows = cached_sqlmodel_rows(n)

    t0 = time.perf_counter()
    for row in rows:
        ResultSQLModel.model_validate(row, from_attributes=True)
    t1 = time.perf_counter()

    return t1 - t0


async def SCHEMA_CONVERT__baserepo(n: int) -> float:
    """
    ORM → BaseRepo._convert (mapping_schema 사용)
    """
    rows = cached_result_rows(n)
    fake_session = FakeAsyncSession()
    repo = ResultStrictRepo(session=fake_session, default_convert_domain=True)

    t0 = time.perf_counter()
    for row in rows:
        repo._convert(row, convert_domain=True)
    t1 = time.perf_counter()

    return t1 - t0


# -------------------------------------------------------------------
# 시나리오: CREATE_MANY (dict, schema 입력)
# -------------------------------------------------------------------
async def CREATE_MANY__sa_from_dict(n: int) -> float:
    """
    SQLAlchemy:
    dict 리스트 → ORM(Result) 리스트 → add_all + flush
    (BaseRepo.create_many(dict) 와 동일한 입력 조건)
    """
    session = FakeAsyncSession()
    payloads = cached_create_payloads_dict(n)

    t0 = time.perf_counter()
    objs = [Result(**p) for p in payloads]
    session.add_all(objs)
    await session.flush()
    t1 = time.perf_counter()

    return t1 - t0


async def CREATE_MANY__repo_from_dict(n: int) -> float:
    """
    BaseRepo.create_many(dict 입력)
    """
    session = FakeAsyncSession()
    repo = ResultStrictRepo(session=session, default_convert_domain=False)
    payloads = cached_create_payloads_dict(n)

    t0 = time.perf_counter()
    await repo.create_many(
        payloads,
        session=session,
        convert_domain=False,
    )
    t1 = time.perf_counter()

    return t1 - t0


async def CREATE_MANY__sa_from_schema(n: int) -> float:
    """
    SQLAlchemy:
    Pydantic 스키마 리스트 → dict → ORM(Result) → add_all + flush
    (BaseRepo.create_many(schema) 와 동일한 입력 조건)
    """
    session = FakeAsyncSession()
    payloads = cached_create_payloads_schema(n)

    t0 = time.perf_counter()
    objs = [
        Result(**p.model_dump(exclude_unset=True))
        for p in payloads
    ]
    session.add_all(objs)
    await session.flush()
    t1 = time.perf_counter()

    return t1 - t0


async def CREATE_MANY__repo_from_schema(n: int) -> float:
    """
    BaseRepo.create_many(Pydantic 스키마 입력)
    """
    session = FakeAsyncSession()
    repo = ResultStrictRepo(session=session, default_convert_domain=False)
    payloads = cached_create_payloads_schema(n)

    t0 = time.perf_counter()
    await repo.create_many(
        payloads,
        session=session,
        convert_domain=False,
    )
    t1 = time.perf_counter()

    return t1 - t0


# -------------------------------------------------------------------
# 시나리오: CREATE_FROM_MODEL (이미 ORM 인스턴스를 가진 경우)
# -------------------------------------------------------------------
async def CREATE_FROM_MODEL__sa(n: int) -> float:
    """
    SQLAlchemy:
    - 이미 생성된 ORM(Result) 인스턴스를 n개 가지고 있다고 가정
    - 각 row 에 대해 add + flush
    (BaseRepo.create_from_model 과 flush 패턴을 맞춤)
    """
    session = FakeAsyncSession()
    objs = cached_create_models(n)

    t0 = time.perf_counter()
    for obj in objs:
        session.add(obj)
        await session.flush()
    t1 = time.perf_counter()

    return t1 - t0


async def CREATE_FROM_MODEL__repo(n: int) -> float:
    """
    BaseRepo.create_from_model(ORM 입력)
    """
    session = FakeAsyncSession()
    repo = ResultStrictRepo(session=session, default_convert_domain=False)
    objs = cached_create_models(n)

    t0 = time.perf_counter()
    for obj in objs:
        await repo.create_from_model(
            obj,
            session=session,
            convert_domain=False,
        )
    t1 = time.perf_counter()

    return t1 - t0


# -------------------------------------------------------------------
# 시나리오: UPDATE (plain / from_model)
# -------------------------------------------------------------------
async def UPDATE__sa_plain(n: int) -> float:
    """
    SQLAlchemy:
    - 각 id에 대해 dict payload로 UPDATE 문 실행
    - BaseRepo.update 와 동일하게 dict 기반 payload를 사용
    """
    session = DMLOnlySession()
    payloads = cached_update_payloads_dict(n)

    t0 = time.perf_counter()
    for i in range(n):
        stmt = (
            Result.__table__.update()
            .where(Result.id == i)
            .values(**payloads[i])
        )
        await session.execute(stmt)
    t1 = time.perf_counter()

    return t1 - t0


async def UPDATE__repo_update(n: int) -> float:
    """
    BaseRepo.update(dict 입력)
    """
    session = DMLOnlySession()
    repo = ResultStrictRepo(session=session, default_convert_domain=False)
    payloads = cached_update_payloads_dict(n)

    t0 = time.perf_counter()
    for i in range(n):
        flt = ResultFilter(id=i)
        await repo.update(
            flt,
            update=payloads[i],
            session=session,
        )
    t1 = time.perf_counter()

    return t1 - t0


async def UPDATE_FROM_MODEL__sa(n: int) -> float:
    """
    SQLAlchemy + dirty checking:
    - 이미 세션이 추적한다고 가정하고, 객체에 setattr 후 flush
    - BaseRepo.update_from_model 과 동일한 패턴
    """
    session = DMLOnlySession()
    bases = list(cached_create_models(n))
    payloads = cached_update_payloads_dict(n)

    t0 = time.perf_counter()
    for i in range(n):
        base = bases[i]
        for k, v in payloads[i].items():
            setattr(base, k, v)
        await session.flush()
    t1 = time.perf_counter()

    return t1 - t0


async def UPDATE_FROM_MODEL__repo(n: int) -> float:
    """
    BaseRepo.update_from_model(ORM + dict 입력)
    """
    session = DMLOnlySession()
    repo = ResultStrictRepo(session=session, default_convert_domain=False)
    bases = list(cached_create_models(n))
    payloads = cached_update_payloads_dict(n)

    t0 = time.perf_counter()
    for i in range(n):
        base = bases[i]
        await repo.update_from_model(
            base,
            update=payloads[i],
            session=session,
            convert_domain=False,
        )
    t1 = time.perf_counter()

    return t1 - t0


# -------------------------------------------------------------------
# BENCH 시나리오 모음
# -------------------------------------------------------------------
BENCH_SCENARIOS: dict[str, Callable[[int], Awaitable[float]]] = {
    "[TEST fetch multiple rows scenario] - sqlalchemy": GET_LIST__bench_sa_pipeline,
    "[TEST fetch multiple rows scenario] - baserepo": GET_LIST__bench_repo_pipeline,
    "[TEST convert model to schema scenario] - pydantic": SCHEMA_CONVERT__pydantic,
    "[TEST convert model to schema scenario] - sqlmodel": SCHEMA_CONVERT__sqlmodel,
    "[TEST convert model to schema scenario] - baserepo": SCHEMA_CONVERT__baserepo,
    "[TEST bulk create from dict scenario] - sqlalchemy": CREATE_MANY__sa_from_dict,
    "[TEST bulk create from dict scenario] - baserepo": CREATE_MANY__repo_from_dict,
    "[TEST bulk create from schema scenario] - sqlalchemy": CREATE_MANY__sa_from_schema,
    "[TEST bulk create from schema scenario] - baserepo": CREATE_MANY__repo_from_schema,
    "[TEST bulk create from model scenario] - sqlalchemy": CREATE_FROM_MODEL__sa,
    "[TEST bulk create from model scenario] - baserepo": CREATE_FROM_MODEL__repo,
    "[TEST bulk update from dict scenario] - sqlalchemy": UPDATE__sa_plain,
    "[TEST bulk update from dict scenario] - baserepo": UPDATE__repo_update,
    "[TEST bulk update from model scenario] - sqlalchemy": UPDATE_FROM_MODEL__sa,
    "[TEST bulk update from model scenario] - baserepo": UPDATE_FROM_MODEL__repo,
}


# -------------------------------------------------------------------
# pytest 엔트리포인트
# -------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.perf_cpu
async def test_performance_suite() -> None:

    for title, scenario in BENCH_SCENARIOS.items():
        results = await run_benchmark(scenario, ROW_VALUES, iterations=ITERATIONS)
        print_table(title, results, iter=ITERATIONS)
