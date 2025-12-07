from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from base_repository.session_provider import SessionProvider


class PerfDBKind(StrEnum):
    MYSQL = "mysql"
    POSTGRES = "postgres"
    SQLITE = "sqlite"




@dataclass(frozen=True)
class PerfDBSettings:
    kind: PerfDBKind
    dsn: str
    echo: bool = False

    @staticmethod
    def from_env() -> "PerfDBSettings":
        """
        < 환경 변수로 perf DB 설정을 로드합니다 >
        1. PERF_DB_KIND 를 읽습니다. 기본값은 mysql 입니다.
        2. PERF_DB_DSN 이 있으면 그대로 사용합니다.
        3. 없으면 kind에 따라 기본 DSN을 생성합니다.
        """
        kind_raw = (os.getenv("PERF_DB_KIND") or "mysql").strip().lower()
        kind = PerfDBKind(kind_raw)

        echo = (os.getenv("PERF_DB_ECHO") or "").strip().lower() in {"1", "true", "yes", "y"}

        dsn_override = (os.getenv("PERF_DB_DSN") or "").strip()
        if dsn_override:
            return PerfDBSettings(kind=kind, dsn=dsn_override, echo=echo)

        if kind == PerfDBKind.MYSQL:
            return PerfDBSettings(kind=kind, dsn=DEFAULT_MYSQL_DSN, echo=echo)

        if kind == PerfDBKind.POSTGRES:
            return PerfDBSettings(kind=kind, dsn=DEFAULT_POSTGRES_DSN, echo=echo)

        sqlite_path = (os.getenv("PERF_SQLITE_PATH") or DEFAULT_SQLITE_PATH).strip()
        return PerfDBSettings(kind=kind, dsn=f"sqlite+aiosqlite:///{sqlite_path}", echo=echo)




DEFAULT_MYSQL_DSN: Final[str] = "mysql+aiomysql://perf_user:perf_pass@127.0.0.1:3307/perf_db"
DEFAULT_POSTGRES_DSN: Final[str] = "postgresql+asyncpg://perf_user:perf_pass@127.0.0.1:5433/perf_db"
DEFAULT_SQLITE_PATH: Final[str] = "tests/perf/sqlite/perf.db"


_current_settings: PerfDBSettings | None = None

_perf_engine: AsyncEngine | None = None
_perf_session_maker: async_sessionmaker[AsyncSession] | None = None

_cached_provider: SessionProvider | None = None




class DefaultSessionProvider(SessionProvider):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self._session_maker = session_maker

    def get_session(self) -> AsyncSession:
        return self._session_maker()




class PerfSessionProviderProxy(SessionProvider):
    """
    < 기존 코드 호환을 위한 Proxy Provider 입니다 >
    1. 테스트 코드가 perf_session_provider 변수를 직접 import 하더라도 None 이 되지 않습니다.
    2. 실제 Provider 는 get_perf_session_provider() 호출 시점에 lazy 로 생성됩니다.
    """
    def get_session(self) -> AsyncSession:
        return get_perf_session_provider().get_session()




def _build_connect_args(settings: PerfDBSettings) -> dict:
    """
    < DB 종류별 connect_args 를 구성합니다 >
    1. mysql: local_infile 및 client_flag 를 켭니다.
    2. postgres: 기본값 사용합니다.
    3. sqlite: check_same_thread 를 False로 둡니다.
    """
    if settings.kind == PerfDBKind.MYSQL:
        from pymysql.constants import CLIENT  # type: ignore[import-untyped]

        return {
            "client_flag": CLIENT.MULTI_STATEMENTS | CLIENT.LOCAL_FILES,
            "local_infile": True,
        }

    if settings.kind == PerfDBKind.SQLITE:
        return {"check_same_thread": False}

    return {}




def create_perf_engine(settings: PerfDBSettings) -> AsyncEngine:
    """
    < perf DB용 AsyncEngine 를 생성합니다 >
    1. URL은 settings.dsn 을 사용합니다.
    2. pytest-asyncio strict 를 고려해 풀을 끄기 위해 NullPool 을 사용합니다.
    3. connect_args 는 DB 종류별로 다르게 적용합니다.
    """
    connect_args = _build_connect_args(settings)

    return create_async_engine(
        settings.dsn,
        echo=settings.echo,
        pool_pre_ping=True,
        poolclass=NullPool,
        connect_args=connect_args,
    )




def create_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    < perf DB용 AsyncSession 팩토리를 생성합니다 >
    1. engine 을 bind 합니다.
    2. expire_on_commit 은 False 로 둡니다.
    """
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )




def configure_perf_db(*, kind: str | None = None, dsn: str | None = None, echo: bool | None = None) -> None:
    """
    < 런타임에 perf DB 설정을 주입하고 단일 톤을 초기화합니다 >
    1. kind, dsn, echo 를 받으면 현재 설정을 갱신합니다.
    2. 엔진, 세션 메이커, provider 캐시를 None 으로 리셋합니다.
    3. 다음 get_perf_engine / get_perf_session_provider 호출 시 새 설정으로 재생성됩니다.
    """
    global _current_settings, _perf_engine, _perf_session_maker, _cached_provider

    base = _current_settings or PerfDBSettings.from_env()

    new_kind = base.kind if kind is None else PerfDBKind(kind.strip().lower())
    new_echo = base.echo if echo is None else bool(echo)

    if dsn is not None:
        new_dsn = dsn.strip()
    else:
        if new_kind == PerfDBKind.MYSQL:
            new_dsn = DEFAULT_MYSQL_DSN
        elif new_kind == PerfDBKind.POSTGRES:
            new_dsn = DEFAULT_POSTGRES_DSN
        else:
            sqlite_path = (os.getenv("PERF_SQLITE_PATH") or DEFAULT_SQLITE_PATH).strip()
            new_dsn = f"sqlite+aiosqlite:///{sqlite_path}"

    _current_settings = PerfDBSettings(kind=new_kind, dsn=new_dsn, echo=new_echo)

    _perf_engine = None
    _perf_session_maker = None
    _cached_provider = None




def get_perf_settings() -> PerfDBSettings:
    """
    < 현재 perf DB 설정을 반환합니다 >
    1. 아직 설정이 없으면 env 기반으로 로드합니다.
    """
    global _current_settings
    if _current_settings is None:
        _current_settings = PerfDBSettings.from_env()
    return _current_settings




def get_perf_engine() -> AsyncEngine:
    """
    < perf DB 전용 AsyncEngine 을 반환합니다 >
    1. 최초 호출이면 설정을 읽고 엔진을 생성합니다.
    2. 이후에는 캐시된 엔진을 반환합니다.
    """
    global _perf_engine
    if _perf_engine is None:
        settings = get_perf_settings()
        _perf_engine = create_perf_engine(settings)
    return _perf_engine




def get_perf_session_provider() -> SessionProvider:
    """
    < perf DB 전용 SessionProvider 를 반환합니다 >
    1. provider 캐시가 있으면 즉시 반환합니다.
    2. engine 이 없으면 생성합니다.
    3. session_maker 가 없으면 생성합니다.
    4. provider 를 생성하고 캐시합니다.
    """
    global _perf_session_maker, _cached_provider

    if _cached_provider is not None:
        return _cached_provider

    engine = get_perf_engine()

    if _perf_session_maker is None:
        _perf_session_maker = create_session_maker(engine)

    _cached_provider = DefaultSessionProvider(_perf_session_maker)
    return _cached_provider




# 외부에서 import 해도 None 이 되지 않도록 Proxy 객체를 노출합니다.
perf_session_provider: SessionProvider = PerfSessionProviderProxy()




async def dispose_perf_engine() -> None:
    """
    < perf AsyncEngine 를 명시적으로 dispose 합니다 >
    1. 엔진이 있으면 await engine.dispose() 를 호출합니다.
    2. 캐시를 초기화합니다.
    """
    global _perf_engine, _perf_session_maker, _cached_provider

    if _perf_engine is not None:
        await _perf_engine.dispose()

    _perf_engine = None
    _perf_session_maker = None
    _cached_provider = None
