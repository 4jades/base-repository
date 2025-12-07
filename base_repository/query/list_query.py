from __future__ import annotations

from collections.abc import Sequence
from enum import Enum, auto
from typing import Annotated, Any, Generic

from sqlalchemy import Select, select
from sqlalchemy.sql.elements import ColumnElement
from typing_extensions import Doc

from base_filter import BaseRepoFilter
from query.strategies.keyset import KeysetStrategy
from query.strategies.offset import OffsetStrategy
from query.strategies.order_by import OrderByStrategy
from repo_types import TModel


class PagingMode(Enum):
    """
    An enum that represents ListQuery paging modes.

    - NONE   : no paging
    - OFFSET : offset-based paging via page/size
    - CURSOR : keyset/seek paging via cursor + limit
    """

    NONE = auto()
    OFFSET = auto()
    CURSOR = auto()


class ListQuery(Generic[TModel]):
    """
    A lightweight DSL for read-only queries.

    This is a **pure state object** used to compose WHERE / ORDER BY / PAGING.
    Actual execution is performed by a higher layer (e.g., BaseRepository.execute or query_to_stmt).

    Design principles
    -----------------
    - WHERE:
        - Uses a single BaseRepoFilter instance.
        - Combined conditions should be expressed inside BaseRepoFilter.
        - `where()` can be called at most once.
    - ORDER:
        - `order_by()` must be called before entering CURSOR mode (= `with_cursor`).
        - Inputs are normalized by OrderByStrategy, and only model-column-based ordering is allowed.
    - PAGING:
        - OFFSET: enter via `paging(page, size)` (page/size-based offset paging)
        - CURSOR: keyset paging via `with_cursor(cursor)` + `limit(size)`
        - OFFSET and CURSOR are mutually exclusive.

    Typical usage
    -------------
    Repository chaining:

    >>> q = (
    ...     repo.list(flt=UserFilter(name="A"))
    ...         .order_by([User.id.asc()])
    ...         .paging(page=1, size=20)
    ... )
    >>> rows = await repo.execute(q)

    Or cursor-based:

    >>> q = (
    ...     repo.list()
    ...         .order_by([User.id.asc()])
    ...         .with_cursor({"id": 123})
    ...         .limit(20)
    ... )
    >>> rows = await repo.execute(q)
    """

    def __init__(self, model: type[TModel], flt: BaseRepoFilter | None = None) -> None:
        """
        Create a ListQuery instance.

        Parameters
        ----------
        model:
            Target SQLAlchemy ORM model class.
            This is used by WHERE/ORDER/PAGING strategies to access column metadata.
        flt:
            Initial WHERE filter (optional).
            - If None, the query starts without a WHERE condition.
            - If provided, it behaves as if `where()` was called once.
        """
        self.model: type[TModel] = model

        self._filter: BaseRepoFilter | None = flt
        self._order_items: Sequence[ColumnElement[Any]] | None = None

        self._mode: PagingMode = PagingMode.NONE
        self._cursor: dict[str, Any] | None = None
        self._cursor_size: int | None = None

        self._page: int | None = None
        self._offset_size: int | None = None
        self._sealed: bool = False


    def _ensure_mutable(self) -> None:
        """
        Check whether the query is sealed (no longer mutable).

        After a ListQuery is converted into an actual Select via `_build_list_query()`,
        it must not be modified. This method guards against further mutations.

        Raises
        ------
        RuntimeError
            If you try to mutate an already sealed ListQuery.
        """
        if self._sealed:
            raise RuntimeError("This query has already been used. Create a new ListQuery.")


    def where(self, flt: BaseRepoFilter | None) -> ListQuery[TModel]:
        """
        Set the WHERE condition.

        Parameters
        ----------
        flt:
            A BaseRepoFilter instance. It generates WHERE criteria by mapping
            dataclass fields to model columns.
            If None, this method is a no-op and returns self.

        Constraints
        -----------
        - `where()` can be called at most once.
          If you need combined conditions, compose them inside BaseRepoFilter.

        Returns
        -------
        ListQuery[TModel]
            Returns self to support method chaining.

        Raises
        ------
        ValueError
            If `where()` is called a second time after a filter is already set.
        RuntimeError
            If called while sealed.
        """
        self._ensure_mutable()
        if flt is None:
            return self
        if self._filter is not None:
            raise ValueError("where() can be called only once. Combine conditions in BaseRepoFilter.")
        self._filter = flt
        return self


    def order_by(self, items: Sequence[ColumnElement[Any]]) -> ListQuery[TModel]:
        """
        Define the ORDER BY clause.

        Parameters
        ----------
        items:
            Ordering input sequence.
            Allowed input types / validation / normalization are performed by OrderByStrategy (at build time).
            Typically supports forms such as:

            - str: "id", "name" (model column key)
            - Enum.value: an Enum whose value is a string
            - model attributes: User.id, User.name
            - ordering expressions: User.name.asc(), User.name.desc()
            - ColumnElement: User.name.expression

        Constraints
        -----------
        - Cannot be called after entering CURSOR mode (after `with_cursor()`).
          Cursor paging depends on the ordering keys, so changing them after entering the mode is not allowed.
        """
        self._ensure_mutable()
        if self._mode is PagingMode.CURSOR:
            raise ValueError("In cursor mode, order_by() must be called before setting the cursor.")
        self._order_items = items
        return self


    def with_cursor(self, cursor: dict[str, Any] | None = None) -> ListQuery[TModel]:
        """
        Switch to CURSOR (keyset) paging mode.

        Parameters
        ----------
        cursor:
            A cursor dict representing the last row of the previous page.
            - None or {} is treated as the first page.
            - Internally, None is normalized to {}. (q.cursor becomes {})
            - Validation and WHERE construction are performed by KeysetStrategy.
            - The key set and order must match the columns specified by `order_by`.
        """
        self._ensure_mutable()

        if self._mode is PagingMode.OFFSET:
            raise ValueError("Offset paging and cursor paging cannot be used together.")

        if not self._order_items:
            raise ValueError("Cursor paging requires order_by().")

        self._cursor = {} if cursor is None else cursor
        self._mode = PagingMode.CURSOR
        return self


    def limit(self, size: int) -> ListQuery[TModel]:
        """
        Set the page size for CURSOR paging.

        Parameters
        ----------
        size:
            Max number of rows to fetch. Must be >= 1.

        Constraints
        -----------
        - Cannot be used together with OFFSET mode.
        - Typically used with CURSOR mode (`with_cursor`), and consumed by KeysetStrategy.apply().

        Returns
        -------
        ListQuery[TModel]
            Returns self to support method chaining.

        Raises
        ------
        ValueError
            - If size <= 0.
            - If called while already in OFFSET mode.
        RuntimeError
            If called while sealed.
        """
        self._ensure_mutable()
        if size <= 0:
            raise ValueError("limit(size) must be >= 1.")
        if self._mode is PagingMode.OFFSET:
            raise ValueError("Offset paging and cursor paging cannot be used together.")
        self._cursor_size = size
        return self


    def paging(self, *, page: int, size: int) -> ListQuery[TModel]:
        """
        Switch to OFFSET (page, size) paging mode.

        Parameters
        ----------
        page:
            Page number. Typically expected to be >= 1.
            (Additional validation may be performed by OffsetStrategy.apply().)
        size:
            Page size (must be >= 1).
        """
        self._ensure_mutable()
        if self._mode is PagingMode.CURSOR or self._cursor is not None:
            raise ValueError("paging(page, size) cannot be used in cursor mode.")
        if self._mode is PagingMode.OFFSET and (self._page is not None or self._offset_size is not None):
            raise ValueError("paging() can be called only once.")
        if size <= 0:
            raise ValueError("size must be >= 1.")
        self._page = page
        self._offset_size = size
        self._mode = PagingMode.OFFSET
        return self


    @property
    def filter(self) -> Annotated[BaseRepoFilter | None, Doc("The current BaseRepoFilter (or None if unset).")]:
        return self._filter

    @property
    def order_items(self) -> Annotated[
        Sequence[ColumnElement[Any]] | None,
        Doc("The user-provided ORDER BY items. They are normalized by OrderByStrategy."),
    ]:
        return self._order_items

    @property
    def cursor(self) -> Annotated[dict[str, Any] | None, Doc("Cursor dictionary used in CURSOR paging. None before call with_cursor(), first page {}.")]:
        return self._cursor

    @property
    def mode(self) -> Annotated[PagingMode, Doc("Current paging mode (NONE / OFFSET / CURSOR).")]:
        return self._mode

    @property
    def cursor_size(self) -> Annotated[int | None, Doc("The limit value for CURSOR paging (or None if unset).")]:
        return self._cursor_size

    @property
    def page(self) -> Annotated[int | None, Doc("The page number for OFFSET paging (or None if unset).")]:
        return self._page

    @property
    def offset_size(self) -> Annotated[int | None, Doc("The page size for OFFSET paging (or None if unset).")]:
        return self._offset_size


def _apply_where(stmt: Select[tuple[TModel]], q: ListQuery[TModel]) -> Select[tuple[TModel]]:
    """
    Apply WHERE criteria based on the BaseRepoFilter stored in ListQuery.

    Parameters
    ----------
    stmt:
        The base Select statement.
    q:
        The ListQuery instance holding the WHERE filter.

    Returns
    -------
    Select
        The Select with WHERE criteria applied. If no filter/criteria exists, returns stmt unchanged.
    """
    if q.filter is None:
        return stmt
    crit = q.filter.where_criteria(q.model)
    if crit:
        stmt = stmt.where(*crit)
    return stmt


def _compute_order_cols(q: ListQuery[TModel]) -> Sequence[ColumnElement[Any]]:
    """
    Compute the ordering columns from ListQuery.order_items.

    Input is normalized by OrderByStrategy. If no input is provided,
    the model's primary key is used as a default ordering.

    Parameters
    ----------
    q:
        The ListQuery instance holding ORDER BY information.

    Returns
    -------
    Sequence[ColumnElement[Any]]
        ColumnElement sequence to be used for ordering.
    """
    return OrderByStrategy.apply(q.model, q.order_items)


def _apply_order(stmt: Select[tuple[TModel]], order_cols: Sequence[ColumnElement[Any]]) -> Select[tuple[TModel]]:
    """
    Apply computed ORDER BY columns to a Select statement.

    Parameters
    ----------
    stmt:
        The base Select statement.
    order_cols:
        ColumnElement sequence to apply as ORDER BY.

    Returns
    -------
    Select
        The Select with ORDER BY applied.
    """
    return stmt.order_by(*order_cols)


def _apply_paging(
    stmt: Select[tuple[TModel]],
    q: ListQuery[TModel],
    order_cols: Sequence[ColumnElement[Any]],
) -> Select[tuple[TModel]]:
    """
    Apply OFFSET or CURSOR paging depending on ListQuery.mode.

    Parameters
    ----------
    stmt:
        The base Select statement (WHERE/ORDER may already be applied).
    q:
        The ListQuery instance holding paging info (mode, cursor, page, size, etc.).
    order_cols:
        The ordering columns used for ORDER BY.
        In CURSOR mode, these columns are used by KeysetStrategy as comparison keys.

    Returns
    -------
    Select
        The Select with LIMIT/OFFSET or keyset WHERE criteria applied.

    Raises
    ------
    ValueError
        - If CURSOR mode but cursor or cursor_size is missing.
        - If OFFSET mode but page or offset_size is missing.
    """
    if q.mode is PagingMode.CURSOR:
        if q.cursor is None:
            raise ValueError("Cursor mode requires with_cursor(cursor).")
        if q.cursor_size is None:
            raise ValueError("Cursor mode requires limit(size).")
        return KeysetStrategy.apply(
            stmt,
            order_cols=order_cols,
            cursor=q.cursor,
            size=q.cursor_size,
        )

    if q.mode is PagingMode.OFFSET:
        if q.page is None or q.offset_size is None:
            raise ValueError("Offset mode requires paging(page, size).")
        return OffsetStrategy.apply(stmt, page=q.page, size=q.offset_size)

    # PagingMode.NONE: no paging
    return stmt


def _build_list_query(q: ListQuery[TModel]) -> Select[tuple[TModel]]:
    """
    Convert a ListQuery into an actual SQLAlchemy Select statement.

    Conversion order
    ----------------
    1. Create a base Select via `select(q.model)`
    2. Apply WHERE via `_apply_where`
    3. Compute order columns via `_compute_order_cols`
    4. Apply ORDER BY via `_apply_order`
    5. Apply OFFSET or CURSOR paging via `_apply_paging`
    6. Seal the query (q._sealed = True) so it can no longer be modified

    Parameters
    ----------
    q:
        The target ListQuery instance to convert.

    Returns
    -------
    Select
        The final Select with WHERE / ORDER BY / paging applied.

    Notes
    -----
    - This function is intended for internal use (e.g., query.converter).
      External code typically reaches it through higher-level APIs such as
      `BaseRepository.execute` or `query_to_stmt`.
    """
    stmt = select(q.model)
    stmt = _apply_where(stmt, q)
    order_cols = _compute_order_cols(q)
    stmt = _apply_order(stmt, order_cols)
    stmt = _apply_paging(stmt, q, order_cols)
    q._sealed = True
    return stmt
