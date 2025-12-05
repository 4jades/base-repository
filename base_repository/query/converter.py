from __future__ import annotations

from sqlalchemy import Select

from query.list_query import ListQuery, _build_list_query
from repo_types import QueryOrStmt, TModel


def query_to_stmt(
    q_or_stmt: QueryOrStmt[TModel],
) -> Select[tuple[TModel]]:
    # If it's already a SQLAlchemy statement, return as-is.

    if isinstance(q_or_stmt, ListQuery):
        return _build_list_query(q_or_stmt)

    # TODO: implement later when needed
    # if isinstance(q_or_stmt, GetQuery):
    #     return build_get_query(q_or_stmt)

    # if isinstance(q_or_stmt, CountQuery):
    #     return build_count_query(q_or_stmt)

    # if isinstance(q_or_stmt, ExistsQuery):
    #     return build_exists_query(q_or_stmt)

    # if isinstance(q_or_stmt, UpdateQuery):
    #     return build_update_query(q_or_stmt)

    # if isinstance(q_or_stmt, DeleteQuery):
    #     return build_delete_query(q_or_stmt)

    raise TypeError(f"Unsupported query/statement type: {type(q_or_stmt)}")
