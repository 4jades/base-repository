from abc import ABC, abstractmethod
from typing import Any

class BaseMapper(ABC):
    """
    Mapping interface between ORM objects and schema objects (Pydantic schemas).
    """

    @abstractmethod
    def to_schema(self, orm_object: Any) -> Any:
        """Converts an ORM object into a schema object."""
        raise NotImplementedError()

    @abstractmethod
    def to_orm(self, schema_object: Any) -> Any:
        """Converts a schema object into an ORM object."""
        raise NotImplementedError()
