from __future__ import annotations

from sqlalchemy import Select

from base_repository.repo_types import TModel


class OffsetStrategy:
    @staticmethod
    def apply(stmt: Select[tuple[TModel]], *, page: int, size: int) -> Select[tuple[TModel]]:
        if page < 1:
            raise ValueError("page must be >= 1.")
        if size < 1:
            raise ValueError("size must be >= 1.")
        offset = (page - 1) * size
        return stmt.offset(offset).limit(size)