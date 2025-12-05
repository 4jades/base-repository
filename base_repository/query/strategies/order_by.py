"""
< Normalize various SQLAlchemy ORDER BY inputs into safe ColumnElement items >
1. Accept user-facing order_by inputs (str / Enum / ORM attribute / asc,desc expression / ColumnElement).
2. Validate that each input can be mapped to the given model, and that it refers to the same table + same column
   (to prevent ordering by other models, aliased tables, raw SQL, or functions).
3. Convert inputs into a list of ColumnElement items that can be passed to `select(...).order_by(*cols)`.
4. If the input is empty, use the model's PK columns (including composite PK) as the default ordering.
5. Remove duplicates by base column identity (ASC/DESC does not matter); keep the first occurrence.

< Supported inputs >
- str: model column key (e.g. "id")
- Enum: Enum member whose value is a str (e.g. UserOrder.ID.value == "id")
- InstrumentedAttribute: Model.id
- UnaryExpression: Model.id.asc(), Model.id.desc()
- ColumnElement: labels/aliases/expressions are allowed ONLY if they pass the strict
  "same table" and "same column" checks.

< Rejected (safety / correctness) >
- Columns from other models
- Columns bound to aliased tables (different `table` object)
- TextClause / FunctionElement based ordering
"""
from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import Any

from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import ColumnElement, TextClause, UnaryExpression
from sqlalchemy.sql.functions import FunctionElement

from repo_types import TModel
from sa_helper import sa_mapper


class OrderByStrategy:
    """
    < Order-by input normalization strategy >

    1. Normalizes user-provided order_by inputs into SQLAlchemy ColumnElement objects.
    2. Enforces that the inputs refer to columns on the given model only.
    3. Strictly checks "same table" + "same column" to prevent alias/foreign-model/sql injection-like ordering.
    4. Returns a list of ColumnElement items ready for `order_by(*cols)`.
    """

    @staticmethod
    def apply(model: type[TModel], order_items: Sequence[Any] | None) -> list[ColumnElement[Any]]:
        """
        < Normalize ordering criteria >
        1. Reject a single string passed by mistake (order_items must be a Sequence).
        2. Normalize and validate inputs via `_normalize_and_validate()`.
        3. If empty after normalization, build default ordering from the model PK columns.
        4. Deduplicate by base column identity (ASC/DESC ignored); keep the first occurrence.

        Parameters
        ----------
        model : type[TModel]
            SQLAlchemy ORM model class.
        order_items : Sequence[Any] | None
            Sequence of ordering inputs (or None). Supported input types:
            - str (column key)
            - Enum (value is str)
            - InstrumentedAttribute (e.g. Model.id)
            - UnaryExpression (e.g. Model.id.asc()/desc())
            - ColumnElement (must pass the strict same-column validation)

        Returns
        -------
        list[ColumnElement[Any]]
            Validated and normalized ORDER BY columns.

        Raises
        ------
        TypeError
            If `order_items` is passed as a single string.
        ValueError
            - If an input cannot be mapped to the model columns
            - If it refers to another model / aliased table
            - If it is FunctionElement/TextClause based
            - If the model has no PK for default ordering
        """
        if isinstance(order_items, str):
            raise TypeError("order_items must be a Sequence, not a single string.")

        cols: list[Any] = list(order_items or [])
        cols = OrderByStrategy._normalize_and_validate(model, cols)

        # If no ordering is provided, use PK columns as the default (supports composite PK).
        if not cols:
            pks = list(sa_mapper(model).primary_key)
            if not pks:
                raise ValueError("Cannot build a default ordering. The model must have a primary key.")
            cols.extend(pks)

        # Deduplicate by base column identity (ASC/DESC ignored). First occurrence wins.
        seen: set[str] = set()
        uniq: list[ColumnElement[Any]] = []
        for c in cols:
            base = OrderByStrategy._base_key(c)
            if base in seen:
                continue
            seen.add(base)
            uniq.append(c)
        return uniq

    @staticmethod
    def _normalize_and_validate(model: type[TModel], cols: list[Any]) -> list[ColumnElement[Any]]:
        """
        < Normalize each input to ColumnElement and validate against the model >
        1. Build:
           - `valid_keys`: allowed column keys from `mapper.column_attrs`
           - `valid_expr_map`: key -> expected ColumnElement expression
        2. For each input:
           - str / Enum(value=str): map to the expected model column expression
           - InstrumentedAttribute: must belong to `model`, then map to expected expression
           - UnaryExpression (asc/desc):
               a) if inner is InstrumentedAttribute: keep the UnaryExpression (preserve direction)
               b) if inner is ColumnElement: must match expected table+column, keep UnaryExpression
           - ColumnElement:
               a) key/name must map to a valid model column key
               b) must pass same-table + same-column checks
               c) return the expected model expression (aliases/labels collapse to canonical expression)
        3. Explicitly reject FunctionElement/TextClause and unsupported types.

        Returns
        -------
        list[ColumnElement[Any]]
            Normalized ORDER BY columns.

        Raises
        ------
        ValueError
            If an input is unsupported or fails model/table/column validation.
        """
        mapper = sa_mapper(model)
        valid_map = {c.key: getattr(model, c.key) for c in mapper.column_attrs}
        valid_keys = set(valid_map.keys())
        valid_expr_map = {k: v.expression for k, v in valid_map.items()}

        out: list[ColumnElement[Any]] = []

        for item in cols:
            # 1) String column key
            if isinstance(item, str):
                if item not in valid_keys:
                    raise ValueError(f"Model {model.__name__} does not have a field '{item}'.")
                out.append(valid_expr_map[item])
                continue

            # 2) Enum (only when value is str)
            if isinstance(item, Enum) and isinstance(item.value, str):
                name = item.value
                if name not in valid_keys:
                    raise ValueError(f"Model {model.__name__} does not have a field '{name}'.")
                out.append(valid_expr_map[name])
                continue

            # 3) Unary expressions (asc()/desc(), etc.)
            if isinstance(item, UnaryExpression):
                inner = item.element

                # Reject function/text-based ordering.
                if isinstance(inner, FunctionElement | TextClause):
                    raise ValueError(f"Unsupported order_by input type: {item!r}")

                # InstrumentedAttribute: must belong to the same model
                if isinstance(inner, InstrumentedAttribute):
                    cls = getattr(inner, "class_", None)
                    if cls is not model:
                        raise ValueError(
                            f"{inner} belongs to another model ({getattr(cls, '__name__', 'Unknown')})."
                        )
                    key_or_name = inner.key
                    if key_or_name not in valid_keys:
                        raise ValueError(f"Model {model.__name__} does not have a field '{key_or_name}'.")
                    out.append(item)  # preserve direction
                    continue

                # ColumnElement: strict same-table + same-column validation
                if isinstance(inner, ColumnElement):
                    key_or_name = getattr(inner, "key", getattr(inner, "name", None))
                    if key_or_name is None or key_or_name not in valid_keys:
                        raise ValueError(f"Model {model.__name__} does not have a field '{key_or_name}'.")
                    expected = valid_expr_map[str(key_or_name)]
                    if not OrderByStrategy._same_table(inner, expected):
                        raise ValueError(f"Model {model.__name__} does not have a field '{key_or_name}'.")
                    if not OrderByStrategy._same_column(inner, expected):
                        raise ValueError(f"Model {model.__name__} does not have a field '{key_or_name}'.")
                    out.append(item)  # preserve direction
                    continue

                raise ValueError(f"Unsupported order_by input type: {item!r}")

            # 4) ORM column attribute
            if isinstance(item, InstrumentedAttribute):
                cls = getattr(item, "class_", None)
                if cls is not model:
                    raise ValueError(
                        f"'{item}' belongs to another model ({getattr(cls, '__name__', 'Unknown')})."
                    )
                key_or_name = item.key
                if key_or_name not in valid_keys:
                    raise ValueError(f"Model {model.__name__} does not have a field '{key_or_name}'.")
                out.append(valid_expr_map[key_or_name])
                continue

            # 5) ColumnElement (labels/aliases/expressions): must pass strict identity checks
            if isinstance(item, ColumnElement):
                key_or_name = getattr(item, "key", getattr(item, "name", None))
                if key_or_name is None or key_or_name not in valid_keys:
                    raise ValueError(f"Unsupported order_by input type: {item!r}")
                expected = valid_expr_map[str(key_or_name)]
                if not OrderByStrategy._same_table(item, expected):
                    raise ValueError(f"Model {model.__name__} does not have a field '{key_or_name}'.")
                if not OrderByStrategy._same_column(item, expected):
                    raise ValueError(f"Model {model.__name__} does not have a field '{key_or_name}'.")
                out.append(expected)  # collapse to canonical expression
                continue

            # 6) Function/Text: explicitly rejected
            if isinstance(item, FunctionElement | TextClause):
                raise ValueError(f"Unsupported order_by input type: {item!r}")

            # 7) Unsupported
            raise ValueError(f"Unsupported order_by input type: {item!r}")

        return out

    @staticmethod
    def _same_table(a: Any, b: Any) -> bool:
        """
        Check whether two column expressions belong to the same table object.
        Columns produced by `aliased()` typically carry a different `table` object and will return False.
        """
        ta = getattr(a, "table", None)
        tb = getattr(b, "table", None)
        return ta is not None and tb is not None and ta is tb

    @staticmethod
    def _same_column(a: Any, b: Any) -> bool:
        """
        Strictly determine whether two expressions refer to the same underlying DB column.

        Order of checks:
        1) If `a.compare(b)` is True => same
        2) If `b` is in `a.proxy_set` => same (labels/aliases)
        3) Recursively follow `a.element` / `a.original`
        4) Otherwise => False (simple key/name comparison is intentionally avoided)
        """
        try:
            cmp = getattr(a, "compare", None)
            if callable(cmp) and cmp(b):
                return True
        except Exception:
            pass

        a_proxy = getattr(a, "proxy_set", None)
        if a_proxy is not None and b in a_proxy:
            return True

        for attr in ("element", "original"):
            if hasattr(a, attr):
                try:
                    if OrderByStrategy._same_column(getattr(a, attr), b):
                        return True
                except RecursionError:
                    break

        return False

    @staticmethod
    def _base_key(col: ColumnElement[Any]) -> str:
        """
        Compute a base identity key for deduplication.
        ASC/DESC direction is ignored, so the same column is kept only once.
        """
        if isinstance(col, UnaryExpression):
            inner = col.element
            return getattr(inner, "key", getattr(inner, "name", repr(inner)))
        return getattr(col, "key", getattr(col, "name", repr(col)))

    @staticmethod
    def is_desc(col: ColumnElement[Any]) -> bool:
        """
        Return True if the given unary ordering expression is DESC.
        """
        return isinstance(col, UnaryExpression) and col.modifier is operators.desc_op
