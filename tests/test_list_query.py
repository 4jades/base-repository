from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

import base_repository.query.list_query as lq_mod
from base_repository.base_filter import BaseRepoFilter
from base_repository.query.list_query import ListQuery, PagingMode

from .fakes import FakeAsyncSession, FakeResult
from .models import Result


# Dummy filter passed into where()
@dataclass
class RFilter(BaseRepoFilter):
    tenant_id: int | None = None


def test_where_only_once_raises() -> None:
    """
    < where() can only be called once >
    1. Create a ListQuery and call where() once.
    2. Call where() a second time.
    3. Assert ValueError is raised.
    """
    # 1
    q = ListQuery(Result)
    q.where(RFilter(tenant_id=1))

    # 2
    # 3
    with pytest.raises(ValueError):
        q.where(RFilter(tenant_id=2))


def test_with_cursor_requires_non_empty_order_by_and_limit_for_build() -> None:
    """
    < Cursor mode requires a non-empty order_by and a limit at build time >
    1. Calling with_cursor() without order_by should raise.
    2. Calling with_cursor() with order_by([]) should raise.
    3. Building cursor mode without limit should raise.
    4. A valid cursor flow (order_by -> with_cursor -> limit) should build without raising.
    """
    # 1
    q = ListQuery(Result)
    with pytest.raises(ValueError):
        q.with_cursor()

    # 2
    q_empty_ob = ListQuery(Result).order_by([])
    with pytest.raises(ValueError):
        q_empty_ob.with_cursor()

    # 3
    q_no_limit = ListQuery(Result).order_by([Result.id.asc()]).with_cursor({})
    with pytest.raises(ValueError):
        from base_repository.query.list_query import _build_list_query

        _ = _build_list_query(q_no_limit)

    # 4
    q_ok = ListQuery(Result).order_by([Result.id.asc()]).with_cursor().limit(10)
    from base_repository.query.converter import query_to_stmt

    _ = query_to_stmt(q_ok)


def test_order_by_after_cursor_forbidden() -> None:
    """
    < order_by() is forbidden after entering cursor mode >
    1. Enter cursor mode by calling with_cursor().
    2. Attempt to call order_by() again.
    3. Assert ValueError is raised.
    """
    # 1
    q = ListQuery(Result).order_by([Result.id.asc()]).with_cursor({}).limit(10)

    # 2
    # 3
    with pytest.raises(ValueError):
        q.order_by([Result.id.asc()])


def test_cursor_and_offset_mutually_exclusive() -> None:
    """
    < Cursor mode and offset mode are mutually exclusive >
    1. Enter cursor mode, then attempt paging(page, size) and assert ValueError.
    2. Enter offset mode, then attempt with_cursor() and assert ValueError.
    """
    # 1
    q = ListQuery(Result).order_by([Result.id.asc()]).with_cursor({})
    with pytest.raises(ValueError):
        q.paging(page=1, size=10)

    # 2
    q2 = ListQuery(Result).paging(page=1, size=10)
    with pytest.raises(ValueError):
        q2.with_cursor()


def test_limit_and_paging_validations() -> None:
    """
    < Validate limit() and paging() constraints >
    1. limit(size) must be >= 1.
    2. paging(page) is validated at build time (page must be >= 1).
    3. paging(size) is validated when calling paging() (size must be >= 1).
    4. limit() cannot be used after entering offset mode via paging().
    5. paging() cannot be called twice.
    """
    # 1
    q = ListQuery(Result).order_by([Result.id.asc()])
    with pytest.raises(ValueError):
        q.limit(0)
    with pytest.raises(ValueError):
        q.limit(-1)

    # 2
    from base_repository.query.converter import _build_list_query

    with pytest.raises(ValueError):
        _build_list_query(
            ListQuery(Result)
            .order_by([Result.id.asc()])
            .paging(page=0, size=10)
        )

    # 3
    with pytest.raises(ValueError):
        ListQuery(Result).paging(page=1, size=0)

    # 4
    q_offset = ListQuery(Result).paging(page=1, size=10)
    with pytest.raises(ValueError):
        q_offset.limit(10)

    # 5
    q_twice = ListQuery(Result).order_by([Result.id.asc()]).paging(page=1, size=10)
    with pytest.raises(ValueError):
        q_twice.paging(page=2, size=10)


def test_build_calls_keysetstrategy_apply(monkeypatch) -> None:
    """
    < _build_list_query calls KeysetStrategy.apply in cursor mode >
    1. Monkeypatch KeysetStrategy.apply to record that it was called.
    2. Build a cursor-mode query.
    3. Build the list query and assert KeysetStrategy.apply was invoked.
    """
    # 1
    called: dict[str, Any] = {}

    def fake_keyset_apply(stmt, *, order_cols, cursor, size):
        called["ok"] = True
        return stmt

    monkeypatch.setattr(lq_mod.KeysetStrategy, "apply", staticmethod(fake_keyset_apply))

    # 2
    from base_repository.query.list_query import _build_list_query

    q = (
        ListQuery(Result)
        .order_by([Result.id.asc()])
        .with_cursor({})
        .limit(5)
    )

    # 3
    _ = _build_list_query(q)
    assert called.get("ok") is True


def test_build_calls_offsetstrategy_apply(monkeypatch) -> None:
    """
    < _build_list_query calls OffsetStrategy.apply in offset mode >
    1. Monkeypatch OffsetStrategy.apply to capture page and size.
    2. Build an offset-mode query.
    3. Build the list query and assert apply received the expected values.
    """
    # 1
    called: dict[str, Any] = {}

    def fake_offset_apply(stmt, *, page, size):
        called["page"] = page
        called["size"] = size
        return stmt

    monkeypatch.setattr(lq_mod.OffsetStrategy, "apply", staticmethod(fake_offset_apply))

    # 2
    from base_repository.query.list_query import _build_list_query

    q = ListQuery(Result).order_by([Result.id.asc()]).paging(page=3, size=10)

    # 3
    _ = _build_list_query(q)
    assert called.get("page") == 3 and called.get("size") == 10


def test_sealed_blocks_all_mutations_after_build() -> None:
    """
    < After build, the query is sealed and rejects any further mutations >
    1. Build an offset-mode query.
    2. Call _build_list_query(q) to seal it.
    3. Assert all mutating methods raise RuntimeError.
    """
    # 1
    from base_repository.query.list_query import _build_list_query

    q = ListQuery(Result).order_by([Result.id.asc()]).paging(page=1, size=10)

    # 2
    _ = _build_list_query(q)

    # 3
    with pytest.raises(RuntimeError):
        q.where(RFilter(tenant_id=1))
    with pytest.raises(RuntimeError):
        q.order_by([Result.id.asc()])
    with pytest.raises(RuntimeError):
        q.paging(page=2, size=10)
    with pytest.raises(RuntimeError):
        q.with_cursor({})
    with pytest.raises(RuntimeError):
        q.limit(5)


def test_valid_offset_flow_executes_and_seals() -> None:
    """
    < A valid offset-mode flow builds, executes, and seals the query >
    1. Build a query: where -> order_by -> paging.
    2. Build a statement and execute it.
    3. Assert further mutation raises RuntimeError.
    """
    # 1
    from base_repository.query.list_query import _build_list_query

    q = (
        ListQuery(Result)
        .where(RFilter(tenant_id=1))
        .order_by([Result.id.asc()])
        .paging(page=1, size=2)
    )

    # 2
    stmt = _build_list_query(q)

    s = FakeAsyncSession(script=[FakeResult([])])
    import asyncio

    asyncio.run(s.execute(stmt))

    # 3
    with pytest.raises(RuntimeError):
        q.limit(1)


def test_mode_transitions_flags() -> None:
    """
    < Mode transition flags are set correctly >
    1. Cursor mode: order_by -> with_cursor -> limit sets mode/cursor/cursor_size.
    2. Offset mode: order_by -> paging sets mode/page/offset_size.
    """
    # 1
    q = ListQuery(Result).order_by([Result.id.asc()]).with_cursor({}).limit(10)
    assert q.mode is PagingMode.CURSOR
    assert q.cursor == {}
    assert q.cursor_size == 10

    # 2
    q2 = ListQuery(Result).order_by([Result.id.asc()]).paging(page=2, size=5)
    assert q2.mode is PagingMode.OFFSET
    assert q2.page == 2 and q2.offset_size == 5


def test_where_none_is_noop() -> None:
    """
    < where(None) is a no-op and returns self >
    1. Call where(None).
    2. Assert the returned object is the same query instance.
    3. Assert the filter remains None.
    """
    # 1
    q = ListQuery(Result)
    returned = q.where(None)

    # 2
    assert returned is q

    # 3
    assert q.filter is None


def test_cursor_property_initial_none() -> None:
    """
    < cursor property is None before calling with_cursor() >
    1. Create a ListQuery without calling with_cursor().
    2. Assert cursor is None.
    """
    # 1
    q = ListQuery(Result)

    # 2
    assert q.cursor is None


def test_apply_paging_cursor_mode_missing_cursor() -> None:
    """
    < _apply_paging raises when mode=CURSOR but cursor is None >
    1. Force q._mode = CURSOR with q._cursor = None and q._cursor_size set.
    2. Prepare a statement and valid order_cols.
    3. Assert _apply_paging raises ValueError with the expected message.
    """
    # 1
    from base_repository.query.list_query import _apply_paging, _compute_order_cols
    from sqlalchemy import select

    q = ListQuery(Result)
    q._mode = PagingMode.CURSOR
    q._cursor = None
    q._cursor_size = 10

    # 2
    stmt = select(Result)
    order_cols = _compute_order_cols(ListQuery(Result).order_by([Result.id.asc()]))

    # 3
    with pytest.raises(ValueError, match="Cursor mode requires with_cursor"):
        _apply_paging(stmt, q, order_cols)


def test_apply_paging_offset_mode_missing_page_or_size() -> None:
    """
    < _apply_paging raises when mode=OFFSET but page/size is missing >
    1. Force q._mode = OFFSET with q._page/_offset_size = None.
    2. Prepare a statement and valid order_cols.
    3. Assert _apply_paging raises ValueError with the expected message.
    """
    # 1
    from base_repository.query.list_query import _apply_paging, _compute_order_cols
    from sqlalchemy import select

    q = ListQuery(Result)
    q._mode = PagingMode.OFFSET
    q._page = None
    q._offset_size = None

    # 2
    stmt = select(Result)
    order_cols = _compute_order_cols(ListQuery(Result).order_by([Result.id.asc()]))

    # 3
    with pytest.raises(ValueError, match="Offset mode requires paging"):
        _apply_paging(stmt, q, order_cols)
