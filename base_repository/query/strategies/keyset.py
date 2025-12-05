from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import ClauseElement, Select, and_, or_, tuple_
from sqlalchemy.sql.elements import ColumnElement, UnaryExpression

from query.strategies.order_by import OrderByStrategy
from repo_types import TModel


class KeysetStrategy:
    """
    <Keyset Pagination Strategy>

    Builds dynamic `WHERE` conditions for keyset pagination based on ORDER BY columns
    and cursor values.

    Compared to OFFSET pagination, it is more stable and resilient to data changes.

    Current behavior:
    - If ALL orderings are ASC:
      - single column: simple `>` comparison
      - multi column: tuple comparison
    - If DESC is present (mixed or all DESC):
      - builds an OR-ladder (seek) condition using `>` for ASC and `<` for DESC per column
    """

    @staticmethod
    def apply(
        stmt: Select[tuple[TModel]],
        *,
        order_cols: Sequence[ColumnElement[Any]],
        cursor: dict[str, Any] | None,
        size: int,
    ) -> Select[tuple[TModel]]:
        """
        <Build WHERE clause for keyset pagination>

        1. Validate order_cols and size
        2. First page (no cursor) -> apply LIMIT only
        3. Validate cursor keys and order against order_cols
        4. Validate and cast cursor values based on column python_type when available
        5. Determine ASC/DESC directions
        6. Build WHERE clause:
           - All ASC -> tuple comparison or simple comparison
           - DESC present -> OR-ladder (seek) condition
        """
        # 1) Validate order_cols and size
        if not order_cols:
            raise ValueError("keyset pagination requires order_cols.")
        if size < 1:
            raise ValueError("size must be >= 1.")

        # 2) First page (cursor is None or empty dict)
        if cursor is None or len(cursor) == 0:
            return stmt.limit(size)

        # 3) Validate cursor keys
        col_keys = [KeysetStrategy._col_key(c) for c in order_cols]
        cursor_keys = list(cursor.keys())

        # Key set must match exactly
        if set(cursor_keys) != set(col_keys):
            raise ValueError(f"cursor keys mismatch. required={col_keys}, got={cursor_keys}")

        # Order must match as well
        if cursor_keys != col_keys:
            raise ValueError(f"cursor key order must match order_cols. required={col_keys}, got={cursor_keys}")

        # 4) Validate values and cast to column python_type when possible
        values: list[Any] = []
        stripped = KeysetStrategy._strip_unary(order_cols)
        if len(stripped) != len(col_keys):
            raise ValueError("order_cols length does not match extracted key length.")

        for i, key in enumerate(col_keys):
            v = cursor[key]
            if v is None:
                raise ValueError(f"NULL is not allowed in cursor values. key={key}")

            # Validate/cast using column python_type if available
            expected_py = getattr(getattr(stripped[i], "type", None), "python_type", None)
            if expected_py is not None and not isinstance(v, expected_py):
                try:
                    v = expected_py(v)
                except Exception as e:
                    raise TypeError(f"cursor['{key}'] is not {expected_py.__name__}.") from e
            values.append(v)

        # 5) Determine direction flags (True = DESC)
        dirs = [OrderByStrategy.is_desc(c) for c in order_cols]

        # 6) Build conditions
        # All ASC: tuple comparison or simple comparison
        if not any(dirs):
            if len(stripped) == 1:
                cond = stripped[0] > values[0]
                return stmt.where(cond).limit(size)
            cond = tuple_(*stripped) > tuple_(*values)
            return stmt.where(cond).limit(size)

        # DESC present (mixed or all DESC): OR-ladder seek condition
        or_conds = []
        for i in range(len(stripped)):
            and_parts = []
            # Fix previous columns with ==
            for j in range(i):
                and_parts.append(stripped[j] == values[j])
            # Current column compares by direction
            if dirs[i]:  # DESC
                and_parts.append(stripped[i] < values[i])
            else:  # ASC
                and_parts.append(stripped[i] > values[i])
            or_conds.append(and_(*and_parts))

        seek = or_(*or_conds)
        return stmt.where(seek).limit(size)

    @staticmethod
    def _col_key(col: ClauseElement) -> str:
        """
        <Extract column key/name>

        - For UnaryExpression (asc()/desc()), unwrap the inner element
        - For aliased/labeled columns, prefer `.key`, then `.name`, otherwise fallback to repr
        """
        if isinstance(col, UnaryExpression):
            col = col.element
        return getattr(col, "key", getattr(col, "name", repr(col)))

    @staticmethod
    def _strip_unary(cols: Sequence[ColumnElement[Any]]) -> list[ColumnElement[Any]]:
        base: list[ColumnElement[Any]] = []
        for c in cols:
            if isinstance(c, UnaryExpression):
                base.append(cast(ColumnElement[Any], c.element))
            else:
                base.append(c)
        return base
