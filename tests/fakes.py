from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class FakeResult:
    """SQLAlchemy Result test double: provide scalars().all()/first(), scalar_one(), rowcount"""

    def __init__(self, rows: Iterable[Any] | None = None, *, count: int | None = None, rowcount: int | None = None):
        self._rows: list[Any] = list(rows or [])
        self._count: int | None = count
        self.rowcount: int | None = rowcount

    def scalars(self) -> FakeResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> int:
        assert self._count is not None, "need to inject scalar_one() response"
        return self._count

    # joinedload(컬렉션) 대비용 - 필요 시 사용
    def unique(self) -> FakeResult:
        return self

    def __iter__(self):
        return iter(self._rows)


class FakeAsyncSession:
    """
    AsyncSession test double:
    - execute(stmt): returns pre-injected FakeResult objects in sequence
    - add/add_all/flush: records method calls for verification
    """

    def __init__(self, script: list[FakeResult] | None = None):
        self._script = script or []
        self._i = 0
        self.added: list[Any] = []
        self.added_all: list[Any] = []
        self.flushed: bool = False

    async def execute(self, stmt: Any) -> FakeResult:
        assert self._i < len(self._script), "FakeAsyncSession script exhausted."
        res = self._script[self._i]
        self._i += 1
        return res

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def add_all(self, objs: Iterable[Any]) -> None:
        self.added_all.extend(list(objs))

    async def flush(self) -> None:
        self.flushed = True
