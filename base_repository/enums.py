from enum import Enum

from sqlalchemy import Delete, Insert, Select, Update


class StatementType(str, Enum):
    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"

    def __str__(self):
        return self.value

    @classmethod
    def from_stmt(cls, stmt: object) -> "StatementType":
        if isinstance(stmt, Select):
            return cls.SELECT
        if isinstance(stmt, Insert):
            return cls.INSERT
        if isinstance(stmt, Update):
            return cls.UPDATE
        if isinstance(stmt, Delete):
            return cls.DELETE
        raise TypeError(f"Unsupported statement type: {type(stmt).__name__}")
