import pytest
import asyncio
import pytest_asyncio

from sqlalchemy.ext.asyncio import AsyncEngine

from tests.perf.seed.bulk_seed_loader import bulk_seed_load
from tests.perf.seed.generate_seed_csv import ensure_seed_csv
from tests.perf.perf_db_crud import ensure_perf_tables, validate_perf_schema_consistency

from .db_config import get_perf_engine


def pytest_configure(config):
    """
    perf_db 테스트가 아닌 경우,
    아래 DB 관련 fixture들이 등록되지 않도록 한다.
    seed랑 스키마, model이랑 같지않으면 에러를 발생시킨다.
    """
    config.addinivalue_line("markers", "perf_db: DB performance test")
    # perf_db 옵션이 없으면 skip 모드로 전환
    config._perf_db_enabled = bool(config.getoption("-m") and "perf_db" in config.getoption("-m"))
    validate_perf_schema_consistency()

def pytest_collection_modifyitems(config, items):
    pass


# ================================
# perf_db일 때만 등록할 fixture들
# ================================
def _perf_db_enabled(config):
    return getattr(config, "_perf_db_enabled", False)


@pytest.fixture(scope="session")
def perf_engine(pytestconfig) -> AsyncEngine:
    if not _perf_db_enabled(pytestconfig):
        pytest.skip("perf_db 마커가 없으므로 perf_engine 미사용")
    return get_perf_engine()


@pytest.fixture(scope="session")
def event_loop(pytestconfig) -> asyncio.AbstractEventLoop:  # type: ignore
    if not _perf_db_enabled(pytestconfig):
        pytest.skip("perf_db 마커가 없으므로 event_loop 미사용")
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def initial_seed(pytestconfig) -> None:
    if not _perf_db_enabled(pytestconfig):
        return  # perf_cpu에서는 아예 시드 로딩 안함
    ensure_seed_csv()
    await ensure_perf_tables()
    await bulk_seed_load()
